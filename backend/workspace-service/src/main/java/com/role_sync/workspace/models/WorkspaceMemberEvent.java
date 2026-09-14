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
 * One change an admin made to a workspace's members (User Management activity). Names and
 * emails are copied in, so the history still reads correctly after a member is removed.
 */
@Entity
@Table(name = "workspace_member_events", indexes = {
        @Index(name = "ix_workspace_member_events_workspace_time", columnList = "workspace_id, created_at")
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class WorkspaceMemberEvent {

    public static final String MEMBER_ADDED = "MEMBER_ADDED";
    public static final String ROLE_CHANGED = "ROLE_CHANGED";
    public static final String MEMBER_DEACTIVATED = "MEMBER_DEACTIVATED";
    public static final String MEMBER_REACTIVATED = "MEMBER_REACTIVATED";
    public static final String MEMBER_REMOVED = "MEMBER_REMOVED";
    public static final String INVITE_RESENT = "INVITE_RESENT";

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "event_id")
    private UUID eventId;

    @Column(name = "workspace_id", nullable = false)
    private UUID workspaceId;

    @Column(name = "action", length = 40, nullable = false)
    private String action;

    @Column(name = "actor_profile_id")
    private UUID actorProfileId;

    @Column(name = "actor_name", length = 150)
    private String actorName;

    @Column(name = "target_profile_id")
    private UUID targetProfileId;

    @Column(name = "target_name", length = 150)
    private String targetName;

    @Column(name = "target_email", length = 320)
    private String targetEmail;

    @Column(name = "from_role", length = 20)
    private String fromRole;

    @Column(name = "to_role", length = 20)
    private String toRole;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        if (createdAt == null) {
            createdAt = LocalDateTime.now();
        }
    }
}
