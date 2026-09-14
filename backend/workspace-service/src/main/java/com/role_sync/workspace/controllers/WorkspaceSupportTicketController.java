package com.role_sync.workspace.controllers;

import com.role_sync.workspace.dto.SupportTicketMessageRequest;
import com.role_sync.workspace.dto.SupportTicketRequest;
import com.role_sync.workspace.dto.SupportTicketResponse;
import com.role_sync.workspace.services.SupportTicketService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.UUID;

/**
 * The Support Desk: workspace members file tickets with the RoleSync team and follow the
 * answers. Identity comes from the gateway's verified {@code X-User-Id} header; the service
 * checks workspace membership and who may see which ticket.
 */
@RestController
@RequestMapping("/api/v1/workspaces")
@RequiredArgsConstructor
public class WorkspaceSupportTicketController {

    private final SupportTicketService supportTickets;

    @PostMapping("/{workspaceId}/support-tickets")
    public Mono<ResponseEntity<SupportTicketResponse>> create(
            @PathVariable UUID workspaceId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader,
            @Valid @RequestBody SupportTicketRequest request) {
        UUID authUserId = resolveAuthUserId(userIdHeader, authUserIdHeader);
        return supportTickets.create(workspaceId, authUserId, request)
                .map(ticket -> ResponseEntity.status(HttpStatus.CREATED).body(ticket));
    }

    /** The caller's tickets; with {@code everyone=true} a workspace owner/admin gets the whole workspace's. */
    @GetMapping("/{workspaceId}/support-tickets")
    public Flux<SupportTicketResponse> list(
            @PathVariable UUID workspaceId,
            @RequestParam(value = "everyone", defaultValue = "false") boolean everyone,
            @RequestParam(value = "limit", defaultValue = "50") int limit,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        UUID authUserId = resolveAuthUserId(userIdHeader, authUserIdHeader);
        return supportTickets.list(workspaceId, authUserId, everyone, limit);
    }

    @GetMapping("/{workspaceId}/support-tickets/{ticketId}")
    public Mono<SupportTicketResponse> get(
            @PathVariable UUID workspaceId,
            @PathVariable UUID ticketId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        UUID authUserId = resolveAuthUserId(userIdHeader, authUserIdHeader);
        return supportTickets.get(workspaceId, ticketId, authUserId);
    }

    @PostMapping("/{workspaceId}/support-tickets/{ticketId}/messages")
    public Mono<SupportTicketResponse> reply(
            @PathVariable UUID workspaceId,
            @PathVariable UUID ticketId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader,
            @Valid @RequestBody SupportTicketMessageRequest request) {
        UUID authUserId = resolveAuthUserId(userIdHeader, authUserIdHeader);
        return supportTickets.reply(workspaceId, ticketId, authUserId, request);
    }

    static UUID resolveAuthUserId(String userIdHeader, String authUserIdHeader) {
        String idStr = userIdHeader != null ? userIdHeader : authUserIdHeader;
        if (idStr == null || idStr.isBlank()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,
                    "Missing user identification header (X-User-Id or X-Auth-User-Id)");
        }
        try {
            return UUID.fromString(idStr);
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Invalid UUID format in user identification header");
        }
    }
}
