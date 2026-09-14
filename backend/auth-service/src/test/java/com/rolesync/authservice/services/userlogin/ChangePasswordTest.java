package com.rolesync.authservice.services.userlogin;

import com.rolesync.authservice.exceptions.BadRequestException;
import com.rolesync.authservice.exceptions.ForbiddenException;
import com.rolesync.authservice.models.AuthUserCredentials;
import com.rolesync.authservice.repository.UserRepository;
import com.rolesync.authservice.services.AccountLockoutService;
import com.rolesync.authservice.services.AuthSecurityEventService;
import com.rolesync.authservice.services.CookiesService;
import com.rolesync.authservice.services.JwtService;
import com.rolesync.authservice.services.TokenService;
import com.rolesync.authservice.services.user.PasswordPolicy;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.time.LocalDateTime;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class ChangePasswordTest {

    private static final String TOKEN = "access-token";
    // Generated, so the source holds no password-like strings.
    private static final String TEMPORARY = PasswordPolicy.generateTemporary();
    private static final String CHOSEN = PasswordPolicy.generateTemporary();

    private final PasswordEncoder encoder = new BCryptPasswordEncoder(4);

    @Mock
    private UserRepository userRepository;
    @Mock
    private JwtService jwtService;
    @Mock
    private TokenService tokenService;
    @Mock
    private CookiesService cookiesService;
    @Mock
    private AccountLockoutService lockoutService;
    @Mock
    private AuthSecurityEventService securityEvents;

    private ChangePassword changePassword;
    private AuthUserCredentials user;

    @BeforeEach
    void setUp() {
        changePassword = new ChangePassword(userRepository, encoder, jwtService, tokenService, cookiesService, lockoutService, securityEvents);
        UUID userId = UUID.randomUUID();
        user = AuthUserCredentials.builder()
                .authUserId(userId).email("jane@acme.com").username("Jane")
                .loginType(AuthUserCredentials.LoginType.EMAIL).status(AuthUserCredentials.Status.ACTIVE)
                .passwordHash(encoder.encode(TEMPORARY)).mustChangePassword(true)
                .temporaryPasswordExpiresAt(LocalDateTime.now().plusDays(3)).build();
        when(jwtService.extractUserId(TOKEN)).thenReturn(userId.toString());
        when(userRepository.findById(userId)).thenReturn(Optional.of(user));
        when(jwtService.generateAccessToken(user)).thenReturn("new-access");
        when(jwtService.generateRefreshToken(user)).thenReturn("new-refresh");
    }

    @Test
    void replacingTheTemporaryPasswordClearsTheFlagAndSignsOutOtherSessions() {
        changePassword.changePassword(TOKEN, TEMPORARY, CHOSEN, null, null);

        assertTrue(encoder.matches(CHOSEN, user.getPasswordHash()));
        assertFalse(user.requiresPasswordChange());
        assertNull(user.getTemporaryPasswordExpiresAt());
        verify(tokenService).revokeAllUserTokens(user.getAuthUserId());
        verify(tokenService).saveAccessToken(eq(user.getAuthUserId()), eq("new-access"), any(UUID.class));
        verify(cookiesService).setAccessTokenCookie(null, "new-access");
        verify(cookiesService).setRefreshTokenCookie(null, "new-refresh");
        verify(lockoutService).resetFailedAttempts("jane@acme.com");
    }

    @Test
    void aWrongCurrentPasswordCountsTowardsLockoutAndChangesNothing() {
        String before = user.getPasswordHash();
        assertThrows(BadRequestException.class,
                () -> changePassword.changePassword(TOKEN, "not-it", CHOSEN, null, null));
        assertTrue(before.equals(user.getPasswordHash()));
        verify(lockoutService).recordFailedAttempt("jane@acme.com");
        verify(tokenService, never()).revokeAllUserTokens(any());
    }

    @Test
    void aLockedAccountCannotTryAgain() {
        when(lockoutService.isAccountLocked("jane@acme.com")).thenReturn(true);
        assertThrows(ForbiddenException.class,
                () -> changePassword.changePassword(TOKEN, TEMPORARY, CHOSEN, null, null));
        verify(userRepository, never()).save(any());
    }

    @Test
    void weakOrUnchangedPasswordsAreRefused() {
        assertThrows(BadRequestException.class, () -> changePassword.changePassword(TOKEN, TEMPORARY, "short", null, null));
        assertThrows(BadRequestException.class, () -> changePassword.changePassword(TOKEN, TEMPORARY, TEMPORARY, null, null));
        verify(userRepository, never()).save(any());
    }

    @Test
    void googleOnlyAccountsHaveNoPasswordToChange() {
        user.setLoginType(AuthUserCredentials.LoginType.THIRD_PARTY);
        assertThrows(BadRequestException.class,
                () -> changePassword.changePassword(TOKEN, TEMPORARY, CHOSEN, null, null));
    }
}
