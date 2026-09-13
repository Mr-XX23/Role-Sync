package com.role_sync.workspace.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MemberActivityResponse {

    @JsonProperty("event_id")
    private UUID eventId;

    /** MEMBER_ADDED, ROLE_CHANGED, MEMBER_DEACTIVATED, MEMBER_REACTIVATED, MEMBER_REMOVED or INVITE_RESENT. */
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
    private LocalDateTime createdAt;
}
