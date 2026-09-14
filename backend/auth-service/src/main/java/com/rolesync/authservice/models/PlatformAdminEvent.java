package com.rolesync.authservice.models;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.UUID;

/**
 * One action a platform super admin took in the Super Admin Console (suspending a user, signing
 * them out...). Written in the same transaction as the change itself; never updated.
 */
@Entity
@Table(name = "platform_admin_events",
        indexes = @Index(name = "idx_platform_admin_events_created_at", columnList = "created_at"))
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PlatformAdminEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", columnDefinition = "UUID", updatable = false, nullable = false)
    private UUID id;

    @Column(name = "actor_user_id", columnDefinition = "UUID", updatable = false, nullable = false)
    private UUID actorUserId;

    @Column(name = "actor_email", length = 100, updatable = false)
    private String actorEmail;

    /** UPPER_SNAKE, e.g. USER_SUSPENDED. */
    @Column(name = "action", length = 40, updatable = false, nullable = false)
    private String action;

    /** What was acted on, e.g. "user". */
    @Column(name = "target_type", length = 32, updatable = false, nullable = false)
    private String targetType;

    @Column(name = "target_id", length = 100, updatable = false)
    private String targetId;

    /** A human label for the target at the time, e.g. the user's email. */
    @Column(name = "target_label", length = 255, updatable = false)
    private String targetLabel;

    /** One line for the console, e.g. "Suspended jane@acme.com: spam". */
    @Column(name = "summary", length = 500, updatable = false, nullable = false)
    private String summary;

    @Column(name = "created_at", updatable = false, nullable = false)
    private LocalDateTime createdAt;
}
