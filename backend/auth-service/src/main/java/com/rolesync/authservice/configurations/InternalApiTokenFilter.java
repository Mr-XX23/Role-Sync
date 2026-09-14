package com.rolesync.authservice.configurations;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * Guards the service-to-service API under {@code /internal/}. The gateway never routes these
 * paths and the service port is not published, but creating verified accounts and issuing
 * passwords is sensitive enough that callers must also present the shared
 * {@code X-Internal-Token}. With no token configured the internal API is switched off.
 */
@Slf4j
public class InternalApiTokenFilter extends OncePerRequestFilter {

    public static final String PATH_PREFIX = "/internal/";
    public static final String TOKEN_HEADER = "X-Internal-Token";

    private final byte[] expectedToken;

    public InternalApiTokenFilter(String expectedToken) {
        this.expectedToken = expectedToken == null || expectedToken.isBlank()
                ? new byte[0]
                : expectedToken.trim().getBytes(StandardCharsets.UTF_8);
        if (this.expectedToken.length == 0) {
            log.warn("INTERNAL_SERVICE_TOKEN is not set: the internal user API (/internal/**) is disabled");
        }
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith(PATH_PREFIX);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        if (expectedToken.length == 0) {
            reject(response, HttpServletResponse.SC_SERVICE_UNAVAILABLE, "The internal API is not configured");
            return;
        }
        String presented = request.getHeader(TOKEN_HEADER);
        if (presented == null || !MessageDigest.isEqual(expectedToken, presented.trim().getBytes(StandardCharsets.UTF_8))) {
            log.warn("Rejected internal API call to {} from {}: missing or wrong service token",
                    request.getRequestURI(), request.getRemoteAddr());
            reject(response, HttpServletResponse.SC_UNAUTHORIZED, "Invalid internal service token");
            return;
        }
        filterChain.doFilter(request, response);
    }

    private static void reject(HttpServletResponse response, int status, String message) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write("{\"message\":\"" + message + "\",\"status\":\"" + status + "\"}");
    }
}
