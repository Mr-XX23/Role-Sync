package com.role_sync.billing.security;

import com.role_sync.billing.clients.WorkspaceDirectoryClient;
import com.role_sync.billing.services.BillingException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Only members of a workspace may see its credits or buy credits for it.
 *
 * <p>Memberships are cached briefly per user. A miss refreshes once before refusing, so someone
 * added to a workspace a moment ago is not turned away by a stale cache.
 */
@Component
public class WorkspaceMembershipGuard {

	private static final Duration TTL = Duration.ofSeconds(30);
	private static final int MAX_CACHED = 5_000;

	private record Cached(Map<UUID, String> memberships, Instant expiresAt) {
	}

	private final WorkspaceDirectoryClient directory;
	private final Map<UUID, Cached> cache = new ConcurrentHashMap<>();

	public WorkspaceMembershipGuard(WorkspaceDirectoryClient directory) {
		this.directory = directory;
	}

	/** @return the caller's role in the workspace */
	public String requireMember(UUID userId, UUID workspaceId) {
		String role = lookup(userId, false).get(workspaceId);
		if (role == null && !lookup(userId, false).containsKey(workspaceId)) {
			Map<UUID, String> fresh = lookup(userId, true);
			if (!fresh.containsKey(workspaceId)) {
				throw new BillingException(HttpStatus.FORBIDDEN, BillingException.NOT_A_MEMBER,
						"You are not a member of this workspace.");
			}
			role = fresh.get(workspaceId);
		}
		return role;
	}

	/** Whether the user is the workspace's OWNER. Refreshes once on a miss, like {@link #requireMember}. */
	public boolean isOwner(UUID userId, UUID workspaceId) {
		Map<UUID, String> memberships = lookup(userId, false);
		if (!memberships.containsKey(workspaceId)) {
			memberships = lookup(userId, true);
		}
		return "OWNER".equalsIgnoreCase(memberships.get(workspaceId));
	}

	private Map<UUID, String> lookup(UUID userId, boolean fresh) {
		Instant now = Instant.now();
		Cached cached = cache.get(userId);
		if (fresh || cached == null || !cached.expiresAt().isAfter(now)) {
			cached = new Cached(directory.memberships(userId), now.plus(TTL));
			if (cache.size() >= MAX_CACHED) {
				cache.entrySet().removeIf(entry -> !entry.getValue().expiresAt().isAfter(now));
			}
			cache.put(userId, cached);
		}
		return cached.memberships();
	}
}
