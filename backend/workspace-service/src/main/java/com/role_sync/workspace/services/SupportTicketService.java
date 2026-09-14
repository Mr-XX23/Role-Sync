package com.role_sync.workspace.services;

import com.role_sync.workspace.dto.SupportTicketMessageRequest;
import com.role_sync.workspace.dto.SupportTicketRequest;
import com.role_sync.workspace.dto.SupportTicketResponse;
import com.role_sync.workspace.dto.admin.AdminPage;
import com.role_sync.workspace.dto.admin.AdminSupportTicket;
import com.role_sync.workspace.dto.admin.AdminSupportTicketDetail;
import com.role_sync.workspace.dto.admin.AdminSupportTicketStats;
import com.role_sync.workspace.dto.admin.SupportTicketStatusRequest;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.UUID;

/**
 * Support tickets: filed and followed from a workspace's Support Desk, answered and managed by
 * platform super admins from the Super Admin Console.
 */
public interface SupportTicketService {

    // --- Support Desk (workspace members) ---

    Mono<SupportTicketResponse> create(UUID workspaceId, UUID authUserId, SupportTicketRequest request);

    /**
     * The caller's own tickets in the workspace, newest first; with {@code everyone}, a workspace
     * owner or admin gets every ticket of the workspace instead.
     */
    Flux<SupportTicketResponse> list(UUID workspaceId, UUID authUserId, boolean everyone, int limit);

    Mono<SupportTicketResponse> get(UUID workspaceId, UUID ticketId, UUID authUserId);

    Mono<SupportTicketResponse> reply(UUID workspaceId, UUID ticketId, UUID authUserId, SupportTicketMessageRequest request);

    // --- Super Admin Console (platform super admins) ---

    Mono<AdminPage<AdminSupportTicket>> adminList(UUID actorUserId, String text, String status, UUID workspaceId,
                                                  boolean awaitingSupport, int page, int size);

    Mono<AdminSupportTicketStats> adminStats(UUID actorUserId);

    Mono<AdminSupportTicketDetail> adminGet(UUID actorUserId, UUID ticketId);

    Mono<AdminSupportTicketDetail> adminReply(UUID actorUserId, UUID ticketId, SupportTicketMessageRequest request);

    Mono<AdminSupportTicketDetail> adminSetStatus(UUID actorUserId, UUID ticketId, SupportTicketStatusRequest request);
}
