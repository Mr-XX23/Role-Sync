package com.role_sync.workspace.services;

import com.role_sync.workspace.clients.AuthAccountClient;
import com.role_sync.workspace.clients.AuthAccountClient.PlatformAccess;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Lets only platform super admins through to this service's Super Admin Console endpoints.
 * auth-service is the only place that decides who is one (an email allowlist, never a stored
 * role), so every check asks it over the internal API; the answer is kept for a short while so
 * paging through a list doesn't ask once per page. The caller's identity comes from the gateway's
 * verified {@code X-User-Id} header, like every other endpoint of this service.
 */
@Component
@Slf4j
public class PlatformAdminGuard {

    public static final String NOT_SIGNED_IN = "Your session has ended. Sign in again.";
    public static final String NOT_SUPER_ADMIN = "Only platform super admins can do this.";

    private static final Duration DEFAULT_TTL = Duration.ofSeconds(30);
    private static final int MAX_CACHED = 1000;

    /** The signed-in super admin: who they are for the audit log. */
    public record Actor(UUID authUserId, String email) {
    }

    private record Cached(boolean superAdmin, String email, Instant expiresAt) {
    }

    private final AuthAccountClient accounts;
    private final Duration ttl;
    private final Clock clock;
    private final Map<UUID, Cached> cache = new ConcurrentHashMap<>();

    /** The constructor Spring uses; the package-private one lets tests pin the TTL and clock. */
    @Autowired
    public PlatformAdminGuard(AuthAccountClient accounts) {
        this(accounts, DEFAULT_TTL, Clock.systemUTC());
    }

    PlatformAdminGuard(AuthAccountClient accounts, Duration ttl, Clock clock) {
        this.accounts = accounts;
        this.ttl = ttl;
        this.clock = clock;
    }

    /**
     * The platform super admin making this request.
     *
     * @throws ResponseStatusException 401 with no caller, 403 when the caller is not a platform
     *                                 super admin, 503/504 when auth-service can't be asked
     */
    public Actor requireSuperAdmin(UUID authUserId) {
        if (authUserId == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, NOT_SIGNED_IN);
        }
        Instant now = clock.instant();
        Cached cached = cache.get(authUserId);
        if (cached == null || !cached.expiresAt().isAfter(now)) {
            PlatformAccess access = accounts.platformAccess(authUserId);
            cached = new Cached(access != null && access.superAdmin(), access == null ? null : access.email(), now.plus(ttl));
            if (cache.size() >= MAX_CACHED) {
                cache.entrySet().removeIf(entry -> !entry.getValue().expiresAt().isAfter(now));
            }
            cache.put(authUserId, cached);
        }
        if (!cached.superAdmin()) {
            log.warn("Refused Super Admin Console call by account {}", authUserId);
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, NOT_SUPER_ADMIN);
        }
        return new Actor(authUserId, cached.email());
    }
}
