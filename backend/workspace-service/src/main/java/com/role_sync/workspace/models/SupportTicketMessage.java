package com.role_sync.workspace.models;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;
import java.util.UUID;

/** One reply on a support ticket, from the reporter or from the RoleSync team. */
@Entity
@Table(name = "support_ticket_messages", indexes = {
        @Index(name = "ix_support_ticket_messages_ticket", columnList = "ticket_id, created_at")
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SupportTicketMessage {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "message_id")
    private UUID messageId;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "ticket_id", nullable = false)
    private SupportTicket ticket;

    @Column(name = "author_auth_user_id", nullable = false)
    private UUID authorAuthUserId;

    /** How the author is shown: the reporter's display name, or "RoleSync Support". */
    @Column(name = "author_name", length = 120, nullable = false)
    private String authorName;

    @Column(name = "from_support", nullable = false)
    @Builder.Default
    private boolean fromSupport = false;

    @Column(name = "body", columnDefinition = "TEXT", nullable = false)
    private String body;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        if (createdAt == null) {
            createdAt = LocalDateTime.now();
        }
    }
}
