package com.role_sync.workspace.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.UUID;

/** One reply on a support ticket as the Support Desk shows it. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SupportTicketMessageResponse {

    private UUID messageId;

    private String authorName;

    /** true: written by the RoleSync team. */
    private boolean fromSupport;

    /** true: written by the person asking. */
    private boolean mine;

    private String body;

    private LocalDateTime createdAt;
}
