package com.role_sync.workspace.models;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;
import java.util.UUID;

/**
 * One change a platform super admin made through the admin console (plans, workspace plans,
 * suspensions and support tickets). Written in the same transaction as the change; labels are
 * copied in so the trail still reads correctly after renames.
 */
@Entity
@Table(name = "platform_admin_events", indexes = {
        @Index(name = "ix_platform_admin_events_created", columnList = "created_at")
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PlatformAdminEvent {

    public static final String WORKSPACE_PLAN_CHANGED = "WORKSPACE_PLAN_CHANGED";
    public static final String WORKSPACE_SUSPENDED = "WORKSPACE_SUSPENDED";
    public static final String WORKSPACE_REACTIVATED = "WORKSPACE_REACTIVATED";
    public static final String PLAN_CREATED = "PLAN_CREATED";
    public static final String PLAN_UPDATED = "PLAN_UPDATED";
    public static final String PLAN_MADE_DEFAULT = "PLAN_MADE_DEFAULT";
    public static final String PLAN_ARCHIVED = "PLAN_ARCHIVED";
    public static final String PLAN_RESTORED = "PLAN_RESTORED";
    public static final String SUPPORT_TICKET_REPLIED = "SUPPORT_TICKET_REPLIED";
    public static final String SUPPORT_TICKET_STATUS_CHANGED = "SUPPORT_TICKET_STATUS_CHANGED";

    public static final String TARGET_WORKSPACE = "workspace";
    public static final String TARGET_PLAN = "plan";
    public static final String TARGET_SUPPORT_TICKET = "support_ticket";

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "event_id")
    private UUID eventId;

    @Column(name = "actor_user_id", nullable = false)
    private UUID actorUserId;

    @Column(name = "actor_email", length = 320)
    private String actorEmail;

    @Column(name = "action", length = 40, nullable = false)
    private String action;

    @Column(name = "target_type", length = 20, nullable = false)
    private String targetType;

    @Column(name = "target_id", length = 100)
    private String targetId;

    @Column(name = "target_label", length = 200)
    private String targetLabel;

    @Column(name = "summary", length = 500, nullable = false)
    private String summary;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        if (createdAt == null) {
            createdAt = LocalDateTime.now();
        }
    }
}
