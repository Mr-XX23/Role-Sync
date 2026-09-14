package com.role_sync.workspace.controllers;

import com.role_sync.workspace.dto.SupportTicketMessageRequest;
import com.role_sync.workspace.dto.admin.AdminPage;
import com.role_sync.workspace.dto.admin.AdminSupportTicket;
import com.role_sync.workspace.dto.admin.AdminSupportTicketDetail;
import com.role_sync.workspace.dto.admin.AdminSupportTicketStats;
import com.role_sync.workspace.dto.admin.SupportTicketStatusRequest;
import com.role_sync.workspace.services.SupportTicketService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

import java.util.UUID;

/**
 * The Super Admin Console's support ticket queue. Every call checks with auth-service that the
 * caller (the gateway's verified {@code X-User-Id}) is a platform super admin.
 */
@RestController
@RequestMapping("/api/v1/workspaces/admin/support-tickets")
@RequiredArgsConstructor
public class AdminSupportTicketController {

    private final SupportTicketService supportTickets;

    @GetMapping
    public Mono<AdminPage<AdminSupportTicket>> list(
            @RequestParam(value = "q", required = false) String text,
            @RequestParam(value = "status", required = false) String status,
            @RequestParam(value = "workspace_id", required = false) UUID workspaceId,
            @RequestParam(value = "awaiting", defaultValue = "false") boolean awaitingSupport,
            @RequestParam(value = "page", defaultValue = "0") int page,
            @RequestParam(value = "size", defaultValue = "25") int size,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        UUID actor = WorkspaceSupportTicketController.resolveAuthUserId(userIdHeader, authUserIdHeader);
        return supportTickets.adminList(actor, text, status, workspaceId, awaitingSupport, page, size);
    }

    @GetMapping("/stats")
    public Mono<AdminSupportTicketStats> stats(
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        UUID actor = WorkspaceSupportTicketController.resolveAuthUserId(userIdHeader, authUserIdHeader);
        return supportTickets.adminStats(actor);
    }

    @GetMapping("/{ticketId}")
    public Mono<AdminSupportTicketDetail> get(
            @PathVariable UUID ticketId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        UUID actor = WorkspaceSupportTicketController.resolveAuthUserId(userIdHeader, authUserIdHeader);
        return supportTickets.adminGet(actor, ticketId);
    }

    @PostMapping("/{ticketId}/messages")
    public Mono<AdminSupportTicketDetail> reply(
            @PathVariable UUID ticketId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader,
            @Valid @RequestBody SupportTicketMessageRequest request) {
        UUID actor = WorkspaceSupportTicketController.resolveAuthUserId(userIdHeader, authUserIdHeader);
        return supportTickets.adminReply(actor, ticketId, request);
    }

    @PutMapping("/{ticketId}/status")
    public Mono<AdminSupportTicketDetail> setStatus(
            @PathVariable UUID ticketId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader,
            @Valid @RequestBody SupportTicketStatusRequest request) {
        UUID actor = WorkspaceSupportTicketController.resolveAuthUserId(userIdHeader, authUserIdHeader);
        return supportTickets.adminSetStatus(actor, ticketId, request);
    }
}
