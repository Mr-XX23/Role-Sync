package com.rolesync.authservice.services.userlogin;

import com.rolesync.authservice.exceptions.BadRequestException;
import com.rolesync.authservice.exceptions.ForbiddenException;
import com.rolesync.authservice.exceptions.UnauthorizedException;
import com.rolesync.authservice.models.AuthUserCredentials;
import com.rolesync.authservice.repository.UserRepository;
import com.rolesync.authservice.services.AccountLockoutService;
import com.rolesync.authservice.services.AuthSecurityEventService;
import com.rolesync.authservice.services.CookiesService;
import com.rolesync.authservice.services.JwtService;
import com.rolesync.authservice.services.TokenService;
import com.rolesync.authservice.services.user.PasswordPolicy;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.UUID;

/**
 * A signed-in user replaces their password, including the temporary one a workspace admin
 * emailed them. Every other session is signed out; this one gets fresh tokens.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class ChangePassword {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final TokenService tokenService;
    private final CookiesService cookiesService;
    private final AccountLockoutService accountLockoutService;
    private final AuthSecurityEventService securityEventService;

    @Transactional
    public void changePassword(String accessToken, String currentPassword, String newPassword,
                               HttpServletRequest request, HttpServletResponse response) {
        AuthUserCredentials user = userRepository.findById(userIdFrom(accessToken))
                .orElseThrow(() -> new UnauthorizedException("Your session has ended. Sign in again."));

        if (user.getLoginType() == AuthUserCredentials.LoginType.THIRD_PARTY) {
            throw new BadRequestException("Your account signs in with Google, so it has no password to change.");
        }

        // Wrong current passwords count towards the same lockout as failed sign-ins.
        String lockoutKey = user.getEmail() != null && !user.getEmail().isBlank() ? user.getEmail() : user.getPhoneNumber();
        if (lockoutKey != null && accountLockoutService.isAccountLocked(lockoutKey)) {
            throw new ForbiddenException(String.format(
                    "Too many incorrect passwords. Try again in %d minutes.",
                    accountLockoutService.getMinutesUntilUnlock(lockoutKey)));
        }
        if (!passwordEncoder.matches(currentPassword, user.getPasswordHash())) {
            if (lockoutKey != null) {
                accountLockoutService.recordFailedAttempt(lockoutKey);
            }
            securityEventService.logSecurityEvent(user, "PASSWORD_CHANGE_FAILED", "Incorrect current password", request);
            throw new BadRequestException(user.requiresPasswordChange()
                    ? "The temporary password is incorrect. Use the one from your invitation email."
                    : "Your current password is incorrect.");
        }

        String problem = PasswordPolicy.problemWith(newPassword);
        if (problem != null) {
            throw new BadRequestException(problem);
        }
        if (passwordEncoder.matches(newPassword, user.getPasswordHash())) {
            throw new BadRequestException("Choose a new password that's different from your current one.");
        }

        user.setPasswordHash(passwordEncoder.encode(newPassword));
        user.setMustChangePassword(false);
        user.setTemporaryPasswordExpiresAt(null);
        user.setUpdatedAt(LocalDateTime.now());
        userRepository.save(user);
        if (lockoutKey != null) {
            accountLockoutService.resetFailedAttempts(lockoutKey);
        }

        tokenService.revokeAllUserTokens(user.getAuthUserId());
        String newAccessToken = jwtService.generateAccessToken(user);
        String newRefreshToken = jwtService.generateRefreshToken(user);
        UUID sessionId = UUID.randomUUID();
        tokenService.saveAccessToken(user.getAuthUserId(), newAccessToken, sessionId);
        tokenService.saveRefreshToken(user.getAuthUserId(), newRefreshToken, sessionId);
        cookiesService.setAccessTokenCookie(response, newAccessToken);
        cookiesService.setRefreshTokenCookie(response, newRefreshToken);

        securityEventService.logSecurityEvent(user, "PASSWORD_CHANGED", "Password changed; other sessions signed out", request);
        log.info("Password changed for user {}", user.getAuthUserId());
    }

    private UUID userIdFrom(String accessToken) {
        try {
            return UUID.fromString(jwtService.extractUserId(accessToken));
        } catch (RuntimeException e) {
            throw new UnauthorizedException("Your session has ended. Sign in again.");
        }
    }
}
