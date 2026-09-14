package com.role_sync.workspace.repository;

import com.role_sync.workspace.models.SupportTicket;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface SupportTicketRepository extends JpaRepository<SupportTicket, UUID> {

    @Query("SELECT t FROM SupportTicket t JOIN FETCH t.workspace JOIN FETCH t.reporter WHERE t.ticketId = :ticketId")
    Optional<SupportTicket> findWithWorkspaceAndReporter(@Param("ticketId") UUID ticketId);

    /** Every ticket of a workspace, newest first (for its owner and admins). */
    @Query("SELECT t FROM SupportTicket t JOIN FETCH t.reporter WHERE t.workspace.workspaceId = :workspaceId " +
           "ORDER BY t.createdAt DESC, t.ticketId DESC")
    List<SupportTicket> findByWorkspace(@Param("workspaceId") UUID workspaceId, Pageable page);

    /** The tickets one person reported in a workspace, newest first. */
    @Query("SELECT t FROM SupportTicket t JOIN FETCH t.reporter WHERE t.workspace.workspaceId = :workspaceId " +
           "AND t.reporter.profileId = :profileId ORDER BY t.createdAt DESC, t.ticketId DESC")
    List<SupportTicket> findByWorkspaceAndReporter(@Param("workspaceId") UUID workspaceId,
                                                   @Param("profileId") UUID profileId, Pageable page);

    // --- The platform admin console ---

    /** Rows of (status, tickets in that status). */
    @Query("SELECT t.status, COUNT(t) FROM SupportTicket t GROUP BY t.status")
    List<Object[]> countByStatus();

    @Query("SELECT COUNT(t) FROM SupportTicket t WHERE t.createdAt >= :since")
    long countCreatedSince(@Param("since") LocalDateTime since);

    /** Tickets in the given statuses where the reporter wrote last, so the team owes an answer. */
    @Query("SELECT COUNT(t) FROM SupportTicket t WHERE t.status IN :statuses AND t.lastMessageFromSupport = false")
    long countAwaitingSupport(@Param("statuses") Collection<String> statuses);
}
