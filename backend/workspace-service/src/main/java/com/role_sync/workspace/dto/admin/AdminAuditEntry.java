package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

/** One entry of the admin audit trail; the same shape in every service. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminAuditEntry {

    private UUID id;

    /** Always "workspace" here. */
    private String service;

    @JsonProperty("actor_user_id")
    private UUID actorUserId;

    @JsonProperty("actor_email")
    private String actorEmail;

    private String action;

    @JsonProperty("target_type")
    private String targetType;

    @JsonProperty("target_id")
    private String targetId;

    @JsonProperty("target_label")
    private String targetLabel;

    private String summary;

    @JsonProperty("created_at")
    private Instant createdAt;
}
