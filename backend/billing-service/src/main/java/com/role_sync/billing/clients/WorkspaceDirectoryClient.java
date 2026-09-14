package com.role_sync.billing.clients;

import com.role_sync.billing.configurations.BillingProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.server.ResponseStatusException;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * The workspaces a user belongs to, from workspace-service — the same source data-pipeline uses for
 * its membership checks.
 */
@Component
public class WorkspaceDirectoryClient {

	private static final Logger log = LoggerFactory.getLogger(WorkspaceDirectoryClient.class);

	private final RestClient client;

	public WorkspaceDirectoryClient(BillingProperties properties) {
		SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
		factory.setConnectTimeout(2_000);
		factory.setReadTimeout(3_000);
		this.client = RestClient.builder()
				.baseUrl(properties.getWorkspaceServiceUrl())
				.requestFactory(factory)
				.build();
	}

	/** Active memberships as workspace id → role. A user with no workspace profile yet has none. */
	public Map<UUID, String> memberships(UUID userId) {
		try {
			List<Map<String, Object>> items = client.get()
					.uri("/api/v1/workspaces")
					.header("X-User-Id", userId.toString())
					.retrieve()
					.body(new ParameterizedTypeReference<>() {
					});
			Map<UUID, String> result = new HashMap<>();
			if (items == null) {
				return result;
			}
			for (Map<String, Object> item : items) {
				if (Boolean.FALSE.equals(item.get("isActive"))) {
					continue;
				}
				try {
					result.put(UUID.fromString(String.valueOf(item.get("workspaceId"))),
							item.get("role") == null ? null : String.valueOf(item.get("role")));
				}
				catch (IllegalArgumentException ignored) {
					// Skip malformed rows rather than failing the whole check.
				}
			}
			return result;
		}
		catch (HttpClientErrorException.NotFound noProfile) {
			return Map.of();
		}
		catch (RestClientException ex) {
			log.error("workspace-service membership lookup failed for {}: {}", userId, ex.getMessage());
			throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "Could not verify workspace access. Try again.");
		}
	}
}
