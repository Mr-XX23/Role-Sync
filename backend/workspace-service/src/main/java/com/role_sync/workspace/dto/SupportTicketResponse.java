package com.role_sync.workspace.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

/** A support ticket as the Support Desk shows it. {@code messages} is only filled for one ticket, not in lists. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SupportTicketResponse {

    private UUID ticketId;

    private UUID workspaceId;

    private String subject;

    private String description;

    /** OPEN, IN_PROGRESS, RESOLVED or CLOSED. */
    private String status;

    private Reporter reporter;

    /** Replies on the ticket (the description itself is not one). */
    private int messageCount;

    private LocalDateTime lastMessageAt;

    /** true when the RoleSync team wrote last. */
    private boolean lastMessageFromSupport;

    /** false once the ticket is closed. */
    private boolean canReply;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;

    private LocalDateTime closedAt;

    private List<SupportTicketMessageResponse> messages;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Reporter {

        private UUID profileId;

        private String name;

        /** true: the person asking is the caller. */
        private boolean mine;
    }
}
