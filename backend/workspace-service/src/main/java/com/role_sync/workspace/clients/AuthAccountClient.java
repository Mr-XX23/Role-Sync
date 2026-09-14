package com.role_sync.workspace.clients;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.Exceptions;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeoutException;

/**
 * auth-service's internal account API: sign-in accounts for the people workspace admins add.
 * Blocking calls, for use inside the service's {@code boundedElastic} callables.
 */
@Slf4j
@Component
public class AuthAccountClient {

    static final String TOKEN_HEADER = "X-Internal-Token";

    private static final Duration QUICK = Duration.ofSeconds(10);
    // auth-service waits up to 20 seconds for the mail server before answering.
    private static final Duration WITH_EMAIL = Duration.ofSeconds(30);

    /** A sign-in account as auth-service describes it. No secrets. */
    public record Account(UUID authUserId, String email, String username, String status, boolean emailVerified,
                          boolean mustChangePassword, LocalDateTime temporaryPasswordExpiresAt,
                          LocalDateTime lastLoginAt, LocalDateTime createdAt, UUID provisionedBy, Boolean created) {

        public boolean wasCreated() {
            return Boolean.TRUE.equals(created);
        }

        /** Its password is still a temporary one that nobody has signed in with. */
        public boolean awaitingFirstSignIn() {
            return mustChangePassword && lastLoginAt == null;
        }
    }

    /** SENT, FAILED or PENDING (the mail server hadn't answered yet). */
    public record EmailOutcome(String status, String message, LocalDateTime temporaryPasswordExpiresAt) {
        public static EmailOutcome failed(String message) {
            return new EmailOutcome("FAILED", message, null);
        }
    }

    private record ProvisionBody(String email, String fullName, UUID invitedByUserId) {
    }

    private record EmailBody(String workspaceName, String invitedByName, String roleName, boolean resend) {
    }

    private record LookupBody(List<UUID> authUserIds) {
    }

    private final WebClient webClient;
    private final String token;

    public AuthAccountClient(@Value("${auth-service.internal-url:http://auth-service:8082}") String baseUrl,
                             @Value("${internal.service-token:}") String token) {
        // Spring Boot 4 only auto-configures WebClient.Builder with the separate webclient starter.
        this.webClient = WebClient.builder()
                .baseUrl(baseUrl)
                .codecs(codecs -> codecs.defaultCodecs().maxInMemorySize(4 * 1024 * 1024))
                .build();
        this.token = token == null ? "" : token.trim();
        if (this.token.isEmpty()) {
            log.warn("INTERNAL_SERVICE_TOKEN is not set: adding users through User Management is disabled");
        }
    }

    /** The account for this email, created (verified, with no usable password yet) if there is none. */
    public Account provision(String email, String fullName, UUID invitedByUserId) {
        return post("/internal/v1/accounts/provision", new ProvisionBody(email, fullName, invitedByUserId),
                new ParameterizedTypeReference<Account>() { }, QUICK);
    }

    /** Sets a new temporary password and emails the sign-in details. */
    public EmailOutcome issueTemporaryPassword(UUID authUserId, String workspaceName, String invitedByName, boolean resend) {
        return post("/internal/v1/accounts/" + authUserId + "/temporary-password",
                new EmailBody(workspaceName, invitedByName, null, resend),
                new ParameterizedTypeReference<EmailOutcome>() { }, WITH_EMAIL);
    }

    /** Tells an existing account holder they were added to the workspace. */
    public EmailOutcome sendWorkspaceAccessEmail(UUID authUserId, String workspaceName, String invitedByName, String roleName) {
        return post("/internal/v1/accounts/" + authUserId + "/workspace-access-email",
                new EmailBody(workspaceName, invitedByName, roleName, false),
                new ParameterizedTypeReference<EmailOutcome>() { }, WITH_EMAIL);
    }

    /** Accounts by auth user id; ids auth-service doesn't know are left out. */
    public Map<UUID, Account> lookup(Collection<UUID> authUserIds) {
        if (authUserIds.isEmpty()) {
            return Map.of();
        }
        List<Account> accounts = post("/internal/v1/accounts/lookup", new LookupBody(List.copyOf(authUserIds)),
                new ParameterizedTypeReference<List<Account>>() { }, QUICK);
        Map<UUID, Account> byId = new LinkedHashMap<>();
        if (accounts != null) {
            accounts.forEach(account -> byId.put(account.authUserId(), account));
        }
        return byId;
    }

    private <T> T post(String path, Object body, ParameterizedTypeReference<T> type, Duration timeout) {
        if (token.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "User management isn't set up yet: INTERNAL_SERVICE_TOKEN is missing on the server.");
        }
        try {
            return webClient.post()
                    .uri(path)
                    .header(TOKEN_HEADER, token)
                    .bodyValue(body)
                    .retrieve()
                    .onStatus(HttpStatusCode::isError, AuthAccountClient::toError)
                    .bodyToMono(type)
                    .timeout(timeout)
                    .block();
        } catch (RuntimeException e) {
            Throwable cause = Exceptions.unwrap(e);
            if (cause instanceof ResponseStatusException status) {
                throw status;
            }
            if (cause instanceof TimeoutException) {
                log.error("auth-service did not answer {} within {}", path, timeout);
                throw new ResponseStatusException(HttpStatus.GATEWAY_TIMEOUT,
                        "The account service took too long to answer. Try again in a moment.");
            }
            if (cause instanceof WebClientRequestException) {
                log.error("auth-service unreachable for {}: {}", path, cause.getMessage());
            } else {
                log.error("auth-service call {} failed", path, cause);
            }
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "The account service is unavailable right now. Try again in a moment.");
        }
    }

    private static Mono<? extends Throwable> toError(ClientResponse response) {
        HttpStatusCode status = response.statusCode();
        return response.bodyToMono(new ParameterizedTypeReference<Map<String, Object>>() { })
                .onErrorReturn(Map.of())
                .defaultIfEmpty(Map.of())
                .map(body -> {
                    Object message = body.get("message");
                    if (status.value() == 401 || status.value() == 503) {
                        log.error("auth-service refused the internal call ({}): {} - check INTERNAL_SERVICE_TOKEN on both services",
                                status.value(), message);
                        return new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                                "User management isn't set up correctly: the account service rejected this server's credentials.");
                    }
                    if (status.is4xxClientError()) {
                        return new ResponseStatusException(status,
                                message == null ? "The account service refused the request" : message.toString());
                    }
                    log.error("auth-service failed ({}): {}", status.value(), message);
                    return new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                            "The account service had a problem. Try again in a moment.");
                });
    }
}
