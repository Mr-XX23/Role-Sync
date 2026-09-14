package com.role_sync.workspace.repository;

import com.role_sync.workspace.models.SupportTicketMessage;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface SupportTicketMessageRepository extends JpaRepository<SupportTicketMessage, UUID> {

    /** The conversation on a ticket, oldest first. */
    List<SupportTicketMessage> findByTicketTicketIdOrderByCreatedAtAscMessageIdAsc(UUID ticketId);
}
