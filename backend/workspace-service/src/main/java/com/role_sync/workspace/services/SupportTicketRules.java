package com.role_sync.workspace.services;

import com.role_sync.workspace.models.SupportTicket;
import com.role_sync.workspace.services.WorkspaceAuthorizationService.CallerContext;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.time.LocalDateTime;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

/**
 * The rules of a support ticket's life: who may read it, who may write to it, and how a reply
 * or a status change from the RoleSync team moves it along. Pure, so they are unit-tested
 * without a database.
 */
public final class SupportTicketRules {

    public static final Set<String> STATUSES = Set.of(
            SupportTicket.OPEN, SupportTicket.IN_PROGRESS, SupportTicket.RESOLVED, SupportTicket.CLOSED);

    /** Statuses in which the ticket is still the team's to deal with. */
    public static final Set<String> ACTIVE_STATUSES = Set.of(SupportTicket.OPEN, SupportTicket.IN_PROGRESS);

    private SupportTicketRules() {
    }

    /** The status in canonical form, or 400 for one that doesn't exist. */
    public static String normalizeStatus(String status) {
        String normalized = status == null ? "" : status.trim().toUpperCase(Locale.ROOT);
        if (!STATUSES.contains(normalized)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "status must be OPEN, IN_PROGRESS, RESOLVED or CLOSED");
        }
        return normalized;
    }

    /** The reporter sees their own tickets; the workspace's owner and admins see every ticket of the workspace. */
    public static boolean canView(CallerContext caller, UUID reporterProfileId) {
        return caller.isAdmin() || caller.profileId().equals(reporterProfileId);
    }

    /** Nobody from the workspace can write to a closed ticket; they open a new one instead. */
    public static boolean canReporterReply(String status) {
        return !SupportTicket.CLOSED.equals(status);
    }

    /** A reporter writing back on a resolved ticket reopens it; otherwise the status stays. */
    public static String statusAfterReporterReply(String status) {
        return SupportTicket.RESOLVED.equals(status) ? SupportTicket.OPEN : status;
    }

    /** The team's first answer moves a new ticket to in-progress; otherwise the status stays. */
    public static String statusAfterSupportReply(String status) {
        return SupportTicket.OPEN.equals(status) ? SupportTicket.IN_PROGRESS : status;
    }

    /** When the ticket counts as closed: set on entering RESOLVED/CLOSED, cleared on reopening, kept otherwise. */
    public static LocalDateTime closedAt(String previous, String next, LocalDateTime existing, LocalDateTime now) {
        boolean wasDone = !ACTIVE_STATUSES.contains(previous);
        boolean isDone = !ACTIVE_STATUSES.contains(next);
        if (!isDone) {
            return null;
        }
        return wasDone && existing != null ? existing : now;
    }
}
