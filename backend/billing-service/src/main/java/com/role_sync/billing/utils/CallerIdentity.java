package com.role_sync.billing.utils;

import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.util.UUID;

/**
 * Reads the identity the API gateway injected.
 *
 * <p>The gateway verifies the RS256 access-token cookie and strips any
 * client-supplied identity headers before injecting its own, so a present
 * X-User-Id is trustworthy. That holds only while this service is unreachable
 * from outside the docker network, which is why its port is not published.
 */
public final class CallerIdentity {

	private CallerIdentity() {
	}

	public static UUID requireUserId(String headerValue) {
		if (headerValue == null || headerValue.isBlank()) {
			throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Missing verified identity");
		}
		try {
			return UUID.fromString(headerValue.trim());
		}
		catch (IllegalArgumentException ex) {
			throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Identity header is not a valid user id");
		}
	}

	/** Prefers the platform X-Tenant-Id header, falling back to an explicit body field. */
	public static UUID requireWorkspaceId(String tenantHeader, UUID fromBody) {
		if (tenantHeader != null && !tenantHeader.isBlank()) {
			try {
				return UUID.fromString(tenantHeader.trim());
			}
			catch (IllegalArgumentException ex) {
				throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "X-Tenant-Id is not a valid workspace id");
			}
		}
		if (fromBody != null) {
			return fromBody;
		}
		throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
				"A workspace is required: send X-Tenant-Id or workspaceId");
	}
}
