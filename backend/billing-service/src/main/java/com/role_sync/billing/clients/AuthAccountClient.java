package com.role_sync.billing.clients;

import com.role_sync.billing.configurations.BillingProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.server.ResponseStatusException;

import java.util.UUID;

/** Asks auth-service whether an account is a platform super admin (an email allowlist it owns). */
@Component
public class AuthAccountClient {

	private static final Logger log = LoggerFactory.getLogger(AuthAccountClient.class);

	public record PlatformAccess(UUID authUserId, boolean superAdmin, String email) {
	}

	private final RestClient client;
	private final String token;

	public AuthAccountClient(BillingProperties properties) {
		SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
		factory.setConnectTimeout(2_000);
		factory.setReadTimeout(3_000);
		this.client = RestClient.builder()
				.baseUrl(properties.getAuthServiceUrl())
				.requestFactory(factory)
				.build();
		this.token = properties.getInternalToken();
	}

	public PlatformAccess platformAccess(UUID authUserId) {
		if (token == null || token.isBlank()) {
			throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
					"Super admin checks are unavailable: INTERNAL_SERVICE_TOKEN is not configured.");
		}
		try {
			return client.get()
					.uri("/internal/v1/accounts/{id}/platform-access", authUserId)
					.header("X-Internal-Token", token)
					.retrieve()
					.body(PlatformAccess.class);
		}
		catch (RestClientException ex) {
			log.error("auth-service platform-access check failed for {}: {}", authUserId, ex.getMessage());
			throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "Could not verify super admin access. Try again.");
		}
	}
}
