package com.role_sync.billing.security;

import com.role_sync.billing.configurations.BillingProperties;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * Service-to-service calls authenticate with the shared INTERNAL_SERVICE_TOKEN. The internal API
 * fails closed: with no token configured, nothing can charge or check credits through it.
 */
@Component
public class InternalTokenGuard {

	private final BillingProperties properties;

	public InternalTokenGuard(BillingProperties properties) {
		this.properties = properties;
	}

	public void require(String presented) {
		String expected = properties.getInternalToken();
		if (expected == null || expected.isBlank()) {
			throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "Internal billing API is not configured.");
		}
		if (presented == null || !MessageDigest.isEqual(
				expected.getBytes(StandardCharsets.UTF_8), presented.getBytes(StandardCharsets.UTF_8))) {
			throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid internal token.");
		}
	}
}
