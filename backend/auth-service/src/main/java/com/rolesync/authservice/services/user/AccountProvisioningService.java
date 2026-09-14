package com.rolesync.authservice.services.user;

import com.rolesync.authservice.dto.email.EmailResponse;
import com.rolesync.authservice.dto.internal.AccountEmailRequest;
import com.rolesync.authservice.dto.internal.AccountSummary;
import com.rolesync.authservice.dto.internal.EmailOutcome;
import com.rolesync.authservice.dto.internal.ProvisionAccountRequest;
import com.rolesync.authservice.exceptions.BadRequestException;
import com.rolesync.authservice.exceptions.ConflictException;
import com.rolesync.authservice.exceptions.NotFoundException;
import com.rolesync.authservice.models.AuthUserCredentials;
import com.rolesync.authservice.models.Role;
import com.rolesync.authservice.repository.UserRepository;
import com.rolesync.authservice.services.AuthSecurityEventService;
import com.rolesync.authservice.services.EmailService;
import com.rolesync.authservice.services.TokenService;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.security.SecureRandom;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Base64;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

/**
 * Accounts that workspace admins create for their team (called by workspace-service through the
 * internal API). Such accounts are verified and active from the start, and their password is a
 * temporary one emailed to the person, who must replace it when they first sign in.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class AccountProvisioningService {

    /** How long an admin's request waits for the mail server before reporting the email as pending. */
    static final Duration EMAIL_WAIT = Duration.ofSeconds(20);
    static final int USERNAME_MAX_LENGTH = 20;
    private static final String USERNAME_ID_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    private static final Set<AuthUserCredentials.Status> BLOCKED =
            Set.of(AuthUserCredentials.Status.LOCKED, AuthUserCredentials.Status.SUSPENDED);

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final EmailService emailService;
    private final TokenService tokenService;
    private final AuthSecurityEventService securityEventService;
    private final PlatformTransactionManager transactionManager;

    private final SecureRandom random = new SecureRandom();

    @Value("${app.temporary-password.validity-days:7}")
    private int temporaryPasswordValidityDays = 7;

    /**
     * The account for this email, creating it when there is none. A created account is verified
     * and active, but its password is random and unknown to anyone until
     * {@link #issueTemporaryPassword} sends one.
     */
    public AccountSummary provision(ProvisionAccountRequest request, HttpServletRequest httpRequest) {
        String email = normalizeEmail(request.getEmail());
        if (!emailService.isDeliverableAddress(email)) {
            throw new BadRequestException("This email address can't receive email. Use a different address.");
        }
        String username = usernameFrom(request.getFullName(), email);

        AccountSummary result;
        try {
            result = inTransaction(() -> userRepository.findFirstByEmailIgnoreCaseOrderByCreatedAtAsc(email)
                    .map(existing -> withCreated(AccountSummary.of(existing), false))
                    .orElseGet(() -> withCreated(AccountSummary.of(createAccount(email, username, request.getInvitedByUserId())), true)));
        } catch (DataIntegrityViolationException e) {
            // Another request created an account for this email at the same moment: use that one.
            result = userRepository.findFirstByEmailIgnoreCaseOrderByCreatedAtAsc(email)
                    .map(existing -> withCreated(AccountSummary.of(existing), false))
                    .orElseThrow(() -> new BadRequestException("The account could not be created. Try again."));
        }

        if (Boolean.TRUE.equals(result.getCreated())) {
            log.info("Workspace admin {} created account {}", request.getInvitedByUserId(), result.getAuthUserId());
            userRepository.findById(result.getAuthUserId()).ifPresent(user -> securityEventService.logSecurityEvent(user,
                    "ADMIN_ACCOUNT_CREATED", "Account created by workspace admin " + request.getInvitedByUserId(), httpRequest));
        }
        return result;
    }

    /**
     * Gives the account a new temporary password and emails it. Only allowed while the person has
     * not chosen their own password, so an admin can never take over or lock out an account its
     * owner already uses. Signs out any session opened with an earlier temporary password.
     */
    public EmailOutcome issueTemporaryPassword(UUID authUserId, AccountEmailRequest context, HttpServletRequest httpRequest) {
        String temporaryPassword = PasswordPolicy.generateTemporary();
        LocalDateTime expiresAt = LocalDateTime.now().plusDays(Math.max(1, temporaryPasswordValidityDays));

        AuthUserCredentials user = inTransaction(() -> {
            AuthUserCredentials account = userRepository.findById(authUserId)
                    .orElseThrow(() -> new NotFoundException("Account not found"));
            if (!account.requiresPasswordChange()) {
                throw new ConflictException("This person has already chosen their own password, so new sign-in details "
                        + "can't be sent. They can reset their password from the sign-in page.");
            }
            if (BLOCKED.contains(account.getStatus())) {
                throw new ConflictException("This account is blocked, so sign-in details can't be sent.");
            }
            account.setPasswordHash(passwordEncoder.encode(temporaryPassword));
            account.setTemporaryPasswordExpiresAt(expiresAt);
            account.setUpdatedAt(LocalDateTime.now());
            AuthUserCredentials saved = userRepository.save(account);
            tokenService.revokeAllUserTokens(authUserId);
            return saved;
        });

        securityEventService.logSecurityEvent(user, "TEMP_PASSWORD_ISSUED",
                context != null && context.isResend() ? "Sign-in details resent by a workspace admin"
                        : "Sign-in details sent by a workspace admin", httpRequest);

        CompletableFuture<EmailResponse> sending = emailService.sendAccountInvitationEmail(
                user.getEmail(), user.getUsername(),
                context == null ? null : context.getWorkspaceName(),
                context == null ? null : context.getInvitedByName(),
                temporaryPassword, expiresAt, context != null && context.isResend(), authUserId);
        return awaitEmail(sending, EMAIL_WAIT, expiresAt);
    }

    /** Tells an existing account holder that an admin added them to a workspace. */
    public EmailOutcome sendWorkspaceAccessEmail(UUID authUserId, AccountEmailRequest context) {
        AuthUserCredentials user = userRepository.findById(authUserId)
                .orElseThrow(() -> new NotFoundException("Account not found"));
        CompletableFuture<EmailResponse> sending = emailService.sendWorkspaceAccessEmail(
                user.getEmail(), user.getUsername(),
                context == null ? null : context.getWorkspaceName(),
                context == null ? null : context.getInvitedByName(),
                context == null ? null : context.getRoleName(),
                authUserId);
        return awaitEmail(sending, EMAIL_WAIT, null);
    }

    public List<AccountSummary> lookup(List<UUID> authUserIds) {
        if (authUserIds == null || authUserIds.isEmpty()) {
            return List.of();
        }
        return userRepository.findAllById(new LinkedHashSet<>(authUserIds)).stream()
                .map(AccountSummary::of)
                .toList();
    }

    private AuthUserCredentials createAccount(String email, String username, UUID invitedBy) {
        LocalDateTime now = LocalDateTime.now();
        byte[] secret = new byte[32];
        random.nextBytes(secret);
        AuthUserCredentials user = AuthUserCredentials.builder()
                .usernameId(generateUniqueUsernameId())
                .username(username)
                .email(email)
                .phoneNumber(null)
                .role(Role.SALESMAN)
                .loginType(AuthUserCredentials.LoginType.EMAIL)
                .status(AuthUserCredentials.Status.ACTIVE)
                .isEmailVerified(true)
                .isPhoneVerified(false)
                .mfaEnabled(false)
                // Nobody knows this password: the person gets a temporary one by email next.
                .passwordHash(passwordEncoder.encode(Base64.getEncoder().encodeToString(secret)))
                .mustChangePassword(true)
                .provisionedBy(invitedBy)
                .createdAt(now)
                .updatedAt(now)
                .build();
        return userRepository.saveAndFlush(user);
    }

    static EmailOutcome awaitEmail(CompletableFuture<EmailResponse> sending, Duration wait, LocalDateTime expiresAt) {
        try {
            EmailResponse response = sending.get(wait.toMillis(), TimeUnit.MILLISECONDS);
            if (response != null && response.isSuccess()) {
                return EmailOutcome.builder().status(EmailOutcome.Status.SENT).message("Email sent")
                        .temporaryPasswordExpiresAt(expiresAt).build();
            }
            String reason = response == null || response.getMessage() == null ? "The email could not be sent" : response.getMessage();
            return EmailOutcome.builder().status(EmailOutcome.Status.FAILED).message(reason)
                    .temporaryPasswordExpiresAt(expiresAt).build();
        } catch (TimeoutException e) {
            return EmailOutcome.builder().status(EmailOutcome.Status.PENDING)
                    .message("The mail server is slow to respond; the email should arrive shortly")
                    .temporaryPasswordExpiresAt(expiresAt).build();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return EmailOutcome.builder().status(EmailOutcome.Status.PENDING)
                    .message("The email is still being sent").temporaryPasswordExpiresAt(expiresAt).build();
        } catch (ExecutionException e) {
            log.error("Account email failed", e.getCause());
            return EmailOutcome.builder().status(EmailOutcome.Status.FAILED).message("The email could not be sent")
                    .temporaryPasswordExpiresAt(expiresAt).build();
        }
    }

    static String normalizeEmail(String email) {
        String normalized = email == null ? "" : email.trim().toLowerCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new BadRequestException("Email is required");
        }
        return normalized;
    }

    /** The account's display name: the column holds at most 20 characters. */
    static String usernameFrom(String fullName, String email) {
        String name = fullName == null ? "" : fullName.replaceAll("\\p{Cntrl}", " ").replaceAll("\\s+", " ").trim();
        if (name.isEmpty() && email != null && email.contains("@")) {
            name = email.substring(0, email.indexOf('@'));
        }
        if (name.length() > USERNAME_MAX_LENGTH) {
            name = name.substring(0, USERNAME_MAX_LENGTH).trim();
        }
        return name.isEmpty() ? "User" : name;
    }

    private String generateUniqueUsernameId() {
        for (int attempt = 0; attempt < 10; attempt++) {
            StringBuilder candidate = new StringBuilder("MS_");
            for (int i = 0; i < 8; i++) {
                candidate.append(USERNAME_ID_CHARS.charAt(random.nextInt(USERNAME_ID_CHARS.length())));
            }
            if (!userRepository.existsByUsernameId(candidate.toString())) {
                return candidate.toString();
            }
        }
        throw new IllegalStateException("Could not generate a unique username id");
    }

    private static AccountSummary withCreated(AccountSummary summary, boolean created) {
        summary.setCreated(created);
        return summary;
    }

    private <T> T inTransaction(Supplier<T> work) {
        return new TransactionTemplate(transactionManager).execute(status -> work.get());
    }
}
