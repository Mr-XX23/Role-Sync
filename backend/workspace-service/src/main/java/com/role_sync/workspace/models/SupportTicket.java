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
 * A support request a workspace member sent to the RoleSync team from the Support Desk. The
 * team answers and moves it through its statuses from the Super Admin Console; the reporter (and
 * the workspace's owner/admins) follow it from the Support Desk.
 */
@Entity
@Table(name = "support_tickets", indexes = {
        @Index(name = "ix_support_tickets_workspace", columnList = "workspace_id, created_at"),
        @Index(name = "ix_support_tickets_reporter", columnList = "reporter_profile_id, created_at"),
        @Index(name = "ix_support_tickets_status", columnList = "status, updated_at")
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SupportTicket {

    /** New, nobody from the team has answered yet (or the reporter wrote again after it was resolved). */
    public static final String OPEN = "OPEN";
    /** The team has answered and is on it. */
    public static final String IN_PROGRESS = "IN_PROGRESS";
    /** The team considers it answered; the reporter can still write back, which reopens it. */
    public static final String RESOLVED = "RESOLVED";
    /** Final: nobody can write to it any more. */
    public static final String CLOSED = "CLOSED";

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "ticket_id")
    private UUID ticketId;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "workspace_id", nullable = false)
    private Workspace workspace;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "reporter_profile_id", nullable = false)
    private WorkspaceProfile reporter;

    /** The reporter's sign-in account, so the console can show their email without a join. */
    @Column(name = "reporter_auth_user_id", nullable = false)
    private UUID reporterAuthUserId;

    @Column(name = "subject", length = 200, nullable = false)
    private String subject;

    @Column(name = "description", columnDefinition = "TEXT", nullable = false)
    private String description;

    @Column(name = "status", length = 20, nullable = false)
    private String status;

    /** Replies on the ticket (the description itself is not one). */
    @Column(name = "message_count", nullable = false)
    @Builder.Default
    private int messageCount = 0;

    @Column(name = "last_message_at")
    private LocalDateTime lastMessageAt;

    /** true when the RoleSync team wrote last; false while the reporter is waiting for an answer. */
    @Column(name = "last_message_from_support", nullable = false)
    @Builder.Default
    private boolean lastMessageFromSupport = false;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    /** When it was last resolved or closed; cleared when it is reopened. */
    @Column(name = "closed_at")
    private LocalDateTime closedAt;

    @Version
    @Column(name = "version")
    private Long version;

    @PrePersist
    protected void onCreate() {
        LocalDateTime now = LocalDateTime.now();
        if (createdAt == null) {
            createdAt = now;
        }
        updatedAt = now;
        if (status == null) {
            status = OPEN;
        }
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }
}
