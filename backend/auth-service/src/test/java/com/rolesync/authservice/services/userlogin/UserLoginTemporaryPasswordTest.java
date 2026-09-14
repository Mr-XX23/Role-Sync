package com.rolesync.authservice.services.userlogin;

import com.rolesync.authservice.dto.loginregistration.LoginResponse;
import com.rolesync.authservice.exceptions.ForbiddenException;
import com.rolesync.authservice.models.AuthUserCredentials;
import com.rolesync.authservice.models.Role;
import com.rolesync.authservice.repository.UserRepository;
import com.rolesync.authservice.services.AccountLockoutService;
import com.rolesync.authservice.services.CookiesService;
import com.rolesync.authservice.services.JwtService;
import com.rolesync.authservice.services.TokenService;
import com.rolesync.authservice.services.user.PasswordPolicy;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
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

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class UserLoginTemporaryPasswordTest {

    private static final String TEMPORARY = PasswordPolicy.generateTemporary();

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
    private LoginUtilities loginUtilities;
    @Mock
    private AccountLockoutService lockoutService;
    @Mock
    private HttpServletRequest request;
    @Mock
    private HttpServletResponse response;

    private UserLogin userLogin;
    private AuthUserCredentials user;

    @BeforeEach
    void setUp() {
        userLogin = new UserLogin(userRepository, encoder, jwtService, tokenService, cookiesService, loginUtilities, lockoutService);
        user = AuthUserCredentials.builder()
                .authUserId(UUID.randomUUID()).email("jane@acme.com").username("Jane").role(Role.SALESMAN)
                .loginType(AuthUserCredentials.LoginType.EMAIL).status(AuthUserCredentials.Status.ACTIVE)
                .isEmailVerified(true).passwordHash(encoder.encode(TEMPORARY)).mustChangePassword(true).build();
        when(userRepository.findByEmailOrPhoneNumber("jane@acme.com", "jane@acme.com")).thenReturn(Optional.of(user));
        when(jwtService.generateAccessToken(any())).thenReturn("access");
        when(jwtService.generateRefreshToken(any())).thenReturn("refresh");
    }

    @Test
    void anExpiredTemporaryPasswordNoLongerSignsIn() {
        user.setTemporaryPasswordExpiresAt(LocalDateTime.now().minusMinutes(1));

        ForbiddenException refused = assertThrows(ForbiddenException.class,
                () -> userLogin.loginUsers("jane@acme.com", TEMPORARY, response, request));

        assertTrue(refused.getMessage().contains("expired"));
        verify(tokenService, never()).saveAccessToken(any(), any(), any());
    }

    @Test
    void aValidTemporaryPasswordSignsInAndAsksForANewPassword() {
        user.setTemporaryPasswordExpiresAt(LocalDateTime.now().plusDays(2));

        LoginResponse login = userLogin.loginUsers("jane@acme.com", TEMPORARY, response, request);

        assertTrue(login.isMustChangePassword());
    }
}
