package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** One support ticket with its description and conversation, for the admin console's drawer. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminSupportTicketDetail {

    private AdminSupportTicket ticket;

    private String description;

    private List<Message> messages;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Message {

        @JsonProperty("message_id")
        private UUID messageId;

        @JsonProperty("author_auth_user_id")
        private UUID authorAuthUserId;

        @JsonProperty("author_name")
        private String authorName;

        @JsonProperty("from_support")
        private boolean fromSupport;

        private String body;

        @JsonProperty("created_at")
        private Instant createdAt;
    }
}
