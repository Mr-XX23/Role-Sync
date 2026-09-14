package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

/** A member change a workspace admin made (User Management activity). */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminMemberEvent {

    @JsonProperty("event_id")
    private UUID eventId;

    private String action;

    @JsonProperty("actor_name")
    private String actorName;

    @JsonProperty("target_name")
    private String targetName;

    @JsonProperty("target_email")
    private String targetEmail;

    @JsonProperty("from_role")
    private String fromRole;

    @JsonProperty("to_role")
    private String toRole;

    @JsonProperty("created_at")
    private Instant createdAt;
}
