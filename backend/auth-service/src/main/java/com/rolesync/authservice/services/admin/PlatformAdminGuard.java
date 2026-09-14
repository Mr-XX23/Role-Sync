package com.rolesync.authservice.services.admin;

import com.rolesync.authservice.dto.CookieUtil;
import com.rolesync.authservice.dto.internal.PlatformAccess;
import com.rolesync.authservice.exceptions.ForbiddenException;
import com.rolesync.authservice.exceptions.UnauthorizedException;
import com.rolesync.authservice.models.AuthUserCredentials;
import com.rolesync.authservice.repository.UserRepository;
import com.rolesync.authservice.services.JwtService;
import com.rolesync.authservice.services.TokenService;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

import java.util.UUID;

/**
 * Lets only platform super admins through to the Super Admin Console API. The caller is resolved
 * from the {@code access_token} cookie on every request, independently of the security filter
 * chain: the token must be a valid, unrevoked ACCESS token, and the account is loaded by its
 * {@code userId} claim (never by the display name in {@code sub}) and checked against
 * {@link PlatformAdminPolicy}.
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class PlatformAdminGuard {

    /** Every Super Admin Console endpoint of this service lives under this prefix. */
    public static final String PATH_PREFIX = "/api/v1/auth/admin/";
    public static final String NOT_SIGNED_IN = "Your session has ended. Sign in again.";
    public static final String NOT_SUPER_ADMIN = "Only platform super admins can do this.";

    private static final String ACCESS_TOKEN_COOKIE = "access_token";
    private static final String ACCESS_TOKEN_TYPE = "ACCESS";

    private final JwtService jwtService;
    private final TokenService tokenService;
    private final UserRepository userRepository;
    private final PlatformAdminPolicy policy;

    /**
     * The signed-in platform super admin making this request.
     *
     * @throws UnauthorizedException when there is no valid session (401)
     * @throws ForbiddenException when the signed-in account is not a platform super admin (403)
     */
    public AuthUserCredentials requireSuperAdmin(HttpServletRequest request) {
        AuthUserCredentials caller = signedInAccount(request);
        if (!policy.isSuperAdmin(caller)) {
            log.warn("Refused Super Admin Console call to {} by account {}", request.getRequestURI(), caller.getAuthUserId());
            throw new ForbiddenException(NOT_SUPER_ADMIN);
        }
        return caller;
    }

    /** The answer to other services' "is this account a platform super admin?" question. */
    public PlatformAccess accessFor(UUID authUserId) {
        AuthUserCredentials account = authUserId == null ? null : userRepository.findById(authUserId).orElse(null);
        return PlatformAccess.builder()
                .authUserId(authUserId)
                .superAdmin(policy.isSuperAdmin(account))
                .email(account == null ? null : account.getEmail())
                .build();
    }

    private AuthUserCredentials signedInAccount(HttpServletRequest request) {
        String token = CookieUtil.getCookieValue(request, ACCESS_TOKEN_COOKIE)
                .filter(value -> !value.isBlank())
                .orElseThrow(() -> new UnauthorizedException(NOT_SIGNED_IN));

        Jwt jwt;
        try {
            jwt = jwtService.validateAndDecodeToken(token);
        } catch (RuntimeException e) {
            throw new UnauthorizedException(NOT_SIGNED_IN);
        }
        // A refresh token in the access cookie is signed and unexpired too, but it is no session.
        if (!ACCESS_TOKEN_TYPE.equals(jwt.getClaimAsString("tokenType"))) {
            throw new UnauthorizedException(NOT_SIGNED_IN);
        }
        if (tokenService.isTokenRevoked(token)) {
            throw new UnauthorizedException(NOT_SIGNED_IN);
        }

        UUID userId;
        try {
            userId = UUID.fromString(jwt.getClaimAsString("userId"));
        } catch (RuntimeException e) {
            throw new UnauthorizedException(NOT_SIGNED_IN);
        }
        return userRepository.findById(userId).orElseThrow(() -> new UnauthorizedException(NOT_SIGNED_IN));
    }
}
