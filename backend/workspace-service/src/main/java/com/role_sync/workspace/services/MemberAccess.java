package com.role_sync.workspace.services;

import com.role_sync.workspace.services.WorkspaceAuthorizationService.CallerContext;
import com.role_sync.workspace.utils.SanitizationUtils;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.regex.Pattern;

/**
 * Who may manage whom in a workspace (User Management). OWNERs and ADMINs manage members, but
 * nobody changes their own membership or the owner's, and only the owner manages admins.
 * Membership itself is checked by {@link WorkspaceAuthorizationService}.
 */
public final class MemberAccess {

    public static final int EMAIL_MAX_LENGTH = 100;
    public static final int NAME_MAX_LENGTH = 50;
    public static final String INVITE_PENDING = "PENDING";
    public static final String INVITE_EXPIRED = "EXPIRED";

    // The same address check auth-service applies before it sends email.
    private static final Pattern EMAIL = Pattern.compile("^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$");

    private MemberAccess() {
    }

    /** Roles the caller may give someone: owners also manage admins, admins only members and viewers. */
    public static List<String> assignableRoles(CallerContext caller) {
        if (caller.isOwner()) {
            return List.of("ADMIN", "MEMBER", "VIEWER");
        }
        return caller.isAdmin() ? List.of("MEMBER", "VIEWER") : List.of();
    }

    /** Why the caller may not change this membership, or null when they may. */
    public static String refusalToManage(CallerContext caller, UUID targetProfileId, String targetRole, UUID ownerProfileId) {
        if (!caller.isAdmin()) {
            return "This action requires OWNER or ADMIN role in the workspace";
        }
        if (targetProfileId.equals(caller.profileId())) {
            return "You can't change your own membership";
        }
        if (targetProfileId.equals(ownerProfileId) || "OWNER".equals(targetRole)) {
            return "The workspace owner's membership can't be changed";
        }
        if ("ADMIN".equals(targetRole) && !caller.isOwner()) {
            return "Only the workspace owner can change an admin's membership";
        }
        return null;
    }

    public static boolean canManage(CallerContext caller, UUID targetProfileId, String targetRole, UUID ownerProfileId) {
        return refusalToManage(caller, targetProfileId, targetRole, ownerProfileId) == null;
    }

    public static void requireCanManage(CallerContext caller, UUID targetProfileId, String targetRole, UUID ownerProfileId) {
        String refusal = refusalToManage(caller, targetProfileId, targetRole, ownerProfileId);
        if (refusal != null) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, refusal);
        }
    }

    /** Trimmed and lower-cased, or 400 with a message people can act on. */
    public static String normalizeEmail(String email) {
        String normalized = email == null ? "" : email.trim().toLowerCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Enter the person's email address.");
        }
        if (normalized.length() > EMAIL_MAX_LENGTH) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Email addresses can be at most " + EMAIL_MAX_LENGTH + " characters.");
        }
        if (!EMAIL.matcher(normalized).matches()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Enter a valid email address.");
        }
        return normalized;
    }

    /** A first or last name: tags stripped, spaces collapsed; null when optional and blank. */
    public static String cleanName(String value, String label, boolean required) {
        String cleaned = SanitizationUtils.sanitizeText(value);
        cleaned = cleaned == null ? "" : cleaned.replaceAll("\\p{Cntrl}", " ").replaceAll("\\s+", " ").trim();
        if (cleaned.isEmpty()) {
            if (required) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Enter the person's " + label + ".");
            }
            return null;
        }
        if (cleaned.length() > NAME_MAX_LENGTH) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    capitalize(label) + " can be at most " + NAME_MAX_LENGTH + " characters.");
        }
        return cleaned;
    }

    /**
     * PENDING while the person still has the temporary password they were emailed, EXPIRED once it
     * stopped working, null when they have chosen their own password.
     */
    public static String inviteStatus(boolean mustChangePassword, LocalDateTime expiresAt, LocalDateTime now) {
        if (!mustChangePassword) {
            return null;
        }
        return expiresAt != null && !now.isBefore(expiresAt) ? INVITE_EXPIRED : INVITE_PENDING;
    }

    /**
     * Sign-in details may be resent to an active member whose details this workspace sent and who
     * hasn't chosen their own password yet.
     */
    public static boolean canResendInvite(boolean canManage, boolean active, boolean issuedHere, boolean mustChangePassword) {
        return canManage && active && issuedHere && mustChangePassword;
    }

    private static String capitalize(String value) {
        return value.isEmpty() ? value : Character.toUpperCase(value.charAt(0)) + value.substring(1);
    }
}
