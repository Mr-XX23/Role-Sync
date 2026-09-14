package com.rolesync.authservice.services.admin;

import com.rolesync.authservice.dto.admin.AdminPage;
import com.rolesync.authservice.dto.admin.AdminSecurityEvent;
import com.rolesync.authservice.dto.admin.AdminSignOutResponse;
import com.rolesync.authservice.dto.admin.AdminUserDetailResponse;
import com.rolesync.authservice.dto.admin.AdminUserResponse;
import com.rolesync.authservice.exceptions.BadRequestException;
import com.rolesync.authservice.exceptions.ConflictException;
import com.rolesync.authservice.exceptions.NotFoundException;
import com.rolesync.authservice.models.AuthUserCredentials;
import com.rolesync.authservice.models.AuthUserCredentials.LoginType;
import com.rolesync.authservice.models.AuthUserCredentials.Status;
import com.rolesync.authservice.repository.AuthSecurityEventRepository;
import com.rolesync.authservice.repository.TokenStoreRepository;
import com.rolesync.authservice.repository.UserRepository;
import com.rolesync.authservice.services.AccountLockoutService;
import com.rolesync.authservice.services.AuthSecurityEventService;
import com.rolesync.authservice.services.TokenService;
import jakarta.persistence.criteria.Predicate;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.stream.Stream;

/**
 * Sign-in accounts in the Super Admin Console: finding them and the few things a platform super
 * admin may do to one. Callers must have passed {@link PlatformAdminGuard}. Every change writes an
 * audit row in the same transaction.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class AdminUserService {

    static final int MAX_PAGE_SIZE = 100;
    static final String TARGET_USER = "user";
    static final String SUSPENDED_EVENT = "ACCOUNT_SUSPENDED";
    private static final char LIKE_ESCAPE = '\\';
    private static final Sort NEWEST_FIRST = Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("authUserId"));

    private final UserRepository userRepository;
    private final TokenStoreRepository tokenStoreRepository;
    private final AuthSecurityEventRepository securityEventRepository;
    private final TokenService tokenService;
    private final AccountLockoutService lockoutService;
    private final AuthSecurityEventService securityEventService;
    private final PlatformAdminPolicy policy;
    private final AdminAuditService audit;

    /**
     * Accounts matching the filters, newest first.
     *
     * @param q         part of the email, username or phone number (any case)
     * @param status    ACTIVE, INACTIVE, SUSPENDED or LOCKED
     * @param verified  "true" or "false": whether the email is verified
     * @param loginType EMAIL, PHONE, THIRD_PARTY or BOTH
     */
    @Transactional(readOnly = true)
    public AdminPage<AdminUserResponse> list(String q, String status, String verified, String loginType, int page, int size) {
        Specification<AuthUserCredentials> filters = filters(q, parseStatus(status), parseVerified(verified), parseLoginType(loginType));
        int pageSize = Math.clamp(size, 1, MAX_PAGE_SIZE);
        int pageNumber = Math.clamp(page, 0, Integer.MAX_VALUE / pageSize);
        return AdminPage.of(userRepository.findAll(filters, PageRequest.of(pageNumber, pageSize, NEWEST_FIRST)), this::toResponse);
    }

    @Transactional(readOnly = true)
    public AdminUserDetailResponse detail(UUID userId) {
        AuthUserCredentials user = findUser(userId);
        return AdminUserDetailResponse.builder()
                .user(toResponse(user))
                .activeSessions(tokenStoreRepository.countActiveSessions(userId, LocalDateTime.now()))
                .recentEvents(securityEventRepository.findTop20ByAuthUser_AuthUserIdOrderByEventTimeDesc(userId).stream()
                        .map(AdminSecurityEvent::of)
                        .toList())
                .build();
    }

    /** Blocks sign-in and ends every session of the account. */
    @Transactional
    public AdminUserResponse suspend(AuthUserCredentials admin, UUID userId, String reason, HttpServletRequest request) {
        AuthUserCredentials user = findUser(userId);
        if (isSelf(admin, user)) {
            throw new ConflictException("You can't suspend your own account.");
        }
        if (policy.isSuperAdmin(user)) {
            throw new ConflictException("Super admins are managed in server configuration.");
        }
        if (user.getStatus() == Status.SUSPENDED) {
            throw new ConflictException("This account is already suspended.");
        }

        user.setStatus(Status.SUSPENDED);
        user.setUpdatedAt(LocalDateTime.now());
        AuthUserCredentials saved = userRepository.save(user);
        tokenService.revokeAllUserTokens(userId);

        String label = labelOf(saved);
        String why = oneLine(reason);
        audit.record(admin, "USER_SUSPENDED", TARGET_USER, userId.toString(), label,
                why == null ? "Suspended " + label : "Suspended " + label + ": " + why);
        securityEventService.logSecurityEvent(saved, SUSPENDED_EVENT,
                "Suspended by platform admin " + labelOf(admin) + (why == null ? "" : ": " + why), request);
        log.info("Platform admin {} suspended account {}", admin.getAuthUserId(), userId);
        return toResponse(saved);
    }

    /** Lets a suspended or locked account sign in again. */
    @Transactional
    public AdminUserResponse reactivate(AuthUserCredentials admin, UUID userId) {
        AuthUserCredentials user = findUser(userId);
        Status previous = user.getStatus();
        if (previous != Status.SUSPENDED && previous != Status.LOCKED) {
            throw new ConflictException("Only suspended or locked accounts can be reactivated.");
        }

        user.setStatus(Status.ACTIVE);
        user.setUpdatedAt(LocalDateTime.now());
        AuthUserCredentials saved = userRepository.save(user);

        String label = labelOf(saved);
        audit.record(admin, "USER_REACTIVATED", TARGET_USER, userId.toString(), label,
                "Reactivated " + label + " (was " + previous.name().toLowerCase(Locale.ROOT) + ")");
        resetLockout(saved);
        log.info("Platform admin {} reactivated account {}", admin.getAuthUserId(), userId);
        return toResponse(saved);
    }

    /** Ends every session of the account; the person can sign in again. */
    @Transactional
    public AdminSignOutResponse signOut(AuthUserCredentials admin, UUID userId) {
        AuthUserCredentials user = findUser(userId);
        if (isSelf(admin, user)) {
            throw new ConflictException("You can't sign out your own account.");
        }

        long sessions = tokenStoreRepository.countActiveSessions(userId, LocalDateTime.now());
        tokenService.revokeAllUserTokens(userId);

        String label = labelOf(user);
        audit.record(admin, "USER_SIGNED_OUT", TARGET_USER, userId.toString(), label,
                "Signed out " + label + " (" + sessions + (sessions == 1 ? " session)" : " sessions)"));
        log.info("Platform admin {} signed out account {} ({} sessions)", admin.getAuthUserId(), userId, sessions);
        return AdminSignOutResponse.builder()
                .user(toResponse(user))
                .revokedSessions(sessions)
                .build();
    }

    /** Clears the failed sign-in counter that temporarily blocks sign-in. */
    @Transactional
    public AdminUserResponse unlock(AuthUserCredentials admin, UUID userId) {
        AuthUserCredentials user = findUser(userId);

        String label = labelOf(user);
        audit.record(admin, "USER_UNLOCKED", TARGET_USER, userId.toString(), label, "Unlocked sign-in for " + label);
        resetLockout(user);
        log.info("Platform admin {} cleared the sign-in lockout of account {}", admin.getAuthUserId(), userId);
        return toResponse(user);
    }

    private AuthUserCredentials findUser(UUID userId) {
        return userRepository.findById(userId).orElseThrow(() -> new NotFoundException("User not found."));
    }

    private AdminUserResponse toResponse(AuthUserCredentials user) {
        return AdminUserResponse.of(user, policy.isSuperAdmin(user),
                lockoutKeys(user).anyMatch(lockoutService::isAccountLocked));
    }

    private void resetLockout(AuthUserCredentials user) {
        lockoutKeys(user).forEach(lockoutService::resetFailedAttempts);
    }

    /** Failed sign-ins are counted per email and per phone number, whichever the person typed. */
    private static Stream<String> lockoutKeys(AuthUserCredentials user) {
        return Stream.of(user.getEmail(), user.getPhoneNumber()).filter(key -> key != null && !key.isBlank());
    }

    private static boolean isSelf(AuthUserCredentials admin, AuthUserCredentials user) {
        return admin.getAuthUserId() != null && admin.getAuthUserId().equals(user.getAuthUserId());
    }

    /** How the audit trail names an account: its email, else its phone number, else its display name. */
    static String labelOf(AuthUserCredentials user) {
        return Stream.of(user.getEmail(), user.getPhoneNumber(), user.getUsername())
                .filter(value -> value != null && !value.isBlank())
                .findFirst()
                .orElse(String.valueOf(user.getAuthUserId()));
    }

    /** The reason as one line for summaries; null when there is none. */
    static String oneLine(String text) {
        if (text == null) {
            return null;
        }
        String line = text.replaceAll("[\\s\\p{Cntrl}]+", " ").trim();
        return line.isEmpty() ? null : line;
    }

    static Specification<AuthUserCredentials> filters(String q, Status status, Boolean emailVerified, LoginType loginType) {
        String pattern = likePattern(q);
        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();
            if (pattern != null) {
                predicates.add(cb.or(
                        cb.like(cb.lower(root.get("email")), pattern, LIKE_ESCAPE),
                        cb.like(cb.lower(root.get("username")), pattern, LIKE_ESCAPE),
                        cb.like(cb.lower(root.get("phoneNumber")), pattern, LIKE_ESCAPE)));
            }
            if (status != null) {
                predicates.add(cb.equal(root.get("status"), status));
            }
            if (emailVerified != null) {
                predicates.add(cb.equal(root.get("isEmailVerified"), emailVerified));
            }
            if (loginType != null) {
                predicates.add(cb.equal(root.get("loginType"), loginType));
            }
            return cb.and(predicates.toArray(Predicate[]::new));
        };
    }

    /** "%text%" for a case-insensitive LIKE, with the user's own % and _ matched literally; null for no search. */
    static String likePattern(String q) {
        if (q == null || q.isBlank()) {
            return null;
        }
        String escaped = q.trim().toLowerCase(Locale.ROOT)
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_");
        return "%" + escaped + "%";
    }

    static Status parseStatus(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return Status.valueOf(value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException e) {
            throw new BadRequestException("status must be one of ACTIVE, INACTIVE, SUSPENDED or LOCKED.");
        }
    }

    static Boolean parseVerified(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return switch (value.trim().toLowerCase(Locale.ROOT)) {
            case "true" -> Boolean.TRUE;
            case "false" -> Boolean.FALSE;
            default -> throw new BadRequestException("verified must be true or false.");
        };
    }

    static LoginType parseLoginType(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return LoginType.valueOf(value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException e) {
            throw new BadRequestException("login_type must be one of EMAIL, PHONE, THIRD_PARTY or BOTH.");
        }
    }
}
