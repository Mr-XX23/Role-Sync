package com.role_sync.billing.security;

import com.role_sync.billing.clients.AuthAccountClient;
import com.role_sync.billing.clients.AuthAccountClient.PlatformAccess;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Lets only platform super admins use the billing admin endpoints. auth-service decides who is one
 * (an email allowlist, never a stored role); answers are cached briefly, the same as
 * workspace-service's guard.
 */
@Component
public class PlatformAdminGuard {

	private static final Logger log = LoggerFactory.getLogger(PlatformAdminGuard.class);
	private static final Duration TTL = Duration.ofSeconds(30);
	private static final int MAX_CACHED = 1_000;

	public record Actor(UUID authUserId, String email) {
	}

	private record Cached(boolean superAdmin, String email, Instant expiresAt) {
	}

	private final AuthAccountClient accounts;
	private final Map<UUID, Cached> cache = new ConcurrentHashMap<>();

	public PlatformAdminGuard(AuthAccountClient accounts) {
		this.accounts = accounts;
	}

	public Actor requireSuperAdmin(UUID authUserId) {
		if (authUserId == null) {
			throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Your session has ended. Sign in again.");
		}
		Instant now = Instant.now();
		Cached cached = cache.get(authUserId);
		if (cached == null || !cached.expiresAt().isAfter(now)) {
			PlatformAccess access = accounts.platformAccess(authUserId);
			cached = new Cached(access != null && access.superAdmin(), access == null ? null : access.email(), now.plus(TTL));
			if (cache.size() >= MAX_CACHED) {
				cache.entrySet().removeIf(entry -> !entry.getValue().expiresAt().isAfter(now));
			}
			cache.put(authUserId, cached);
		}
		if (!cached.superAdmin()) {
			log.warn("Refused billing admin call by account {}", authUserId);
			throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Only platform super admins can do this.");
		}
		return new Actor(authUserId, cached.email());
	}
}
