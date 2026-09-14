package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

/** A support ticket as the admin console's queue lists it. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminSupportTicket {

    @JsonProperty("ticket_id")
    private UUID ticketId;

    private String subject;

    /** OPEN, IN_PROGRESS, RESOLVED or CLOSED. */
    private String status;

    /** Replies on the ticket (the description itself is not one). */
    @JsonProperty("message_count")
    private int messageCount;

    @JsonProperty("last_message_at")
    private Instant lastMessageAt;

    /** false while the reporter is waiting for the team's answer. */
    @JsonProperty("last_message_from_support")
    private boolean lastMessageFromSupport;

    @JsonProperty("created_at")
    private Instant createdAt;

    @JsonProperty("updated_at")
    private Instant updatedAt;

    @JsonProperty("closed_at")
    private Instant closedAt;

    private Workspace workspace;

    private Reporter reporter;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Workspace {

        @JsonProperty("workspace_id")
        private UUID workspaceId;

        private String name;

        /** false: suspended. */
        @JsonProperty("is_active")
        private boolean active;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Reporter {

        @JsonProperty("profile_id")
        private UUID profileId;

        @JsonProperty("auth_user_id")
        private UUID authUserId;

        private String name;

        /** Null when the account service couldn't be asked. */
        private String email;
    }
}
