package com.rolesync.authservice.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.rolesync.authservice.models.PlatformAdminEvent;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

/** One Super Admin Console action; the same shape in every service's audit list. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminAuditEntry {

    /** This service's name in audit entries. */
    public static final String SERVICE = "auth";

    private UUID id;

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
    private String createdAt;

    public static AdminAuditEntry of(PlatformAdminEvent event) {
        return AdminAuditEntry.builder()
                .id(event.getId())
                .service(SERVICE)
                .actorUserId(event.getActorUserId())
                .actorEmail(event.getActorEmail())
                .action(event.getAction())
                .targetType(event.getTargetType())
                .targetId(event.getTargetId())
                .targetLabel(event.getTargetLabel())
                .summary(event.getSummary())
                .createdAt(AdminTimestamps.utc(event.getCreatedAt()))
                .build();
    }
}
