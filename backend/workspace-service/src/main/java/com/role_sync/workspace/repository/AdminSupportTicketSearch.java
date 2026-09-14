package com.role_sync.workspace.repository;

import com.role_sync.workspace.models.SupportTicket;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.TypedQuery;
import org.springframework.stereotype.Repository;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * The platform admin console's support ticket queue: optional filters, most recently active first,
 * one page at a time. Only the filters that are set become JPQL clauses.
 */
@Repository
public class AdminSupportTicketSearch {

    @PersistenceContext
    private EntityManager entityManager;

    /**
     * @param text            case-insensitive substring of the subject, the workspace name or the reporter's name; null for any
     * @param status          one ticket status; null for all
     * @param workspaceId     tickets of this workspace; null for any
     * @param awaitingSupport true: only open/in-progress tickets where the reporter wrote last
     */
    public record Criteria(String text, String status, UUID workspaceId, boolean awaitingSupport) {
    }

    public record Result(List<SupportTicket> tickets, long total) {
    }

    /** One page of matching tickets with their workspace and reporter loaded, and how many match in all. */
    public Result search(Criteria criteria, int page, int size) {
        StringBuilder where = new StringBuilder(" WHERE 1 = 1");
        Map<String, Object> parameters = new LinkedHashMap<>();
        if (criteria.text() != null && !criteria.text().isBlank()) {
            where.append(" AND (LOWER(t.subject) LIKE :text ESCAPE '!'")
                    .append(" OR LOWER(w.name) LIKE :text ESCAPE '!'")
                    .append(" OR LOWER(COALESCE(r.displayName, '')) LIKE :text ESCAPE '!'")
                    .append(" OR LOWER(CONCAT(COALESCE(r.firstName, ''), ' ', COALESCE(r.lastName, ''))) LIKE :text ESCAPE '!')");
            parameters.put("text", AdminWorkspaceSearch.likePattern(criteria.text()));
        }
        if (criteria.status() != null && !criteria.status().isBlank()) {
            where.append(" AND t.status = :status");
            parameters.put("status", criteria.status());
        }
        if (criteria.workspaceId() != null) {
            where.append(" AND w.workspaceId = :workspaceId");
            parameters.put("workspaceId", criteria.workspaceId());
        }
        if (criteria.awaitingSupport()) {
            where.append(" AND t.lastMessageFromSupport = false AND t.status IN ('")
                    .append(SupportTicket.OPEN).append("', '").append(SupportTicket.IN_PROGRESS).append("')");
        }

        TypedQuery<Long> count = entityManager.createQuery(
                "SELECT COUNT(t) FROM SupportTicket t JOIN t.workspace w JOIN t.reporter r" + where, Long.class);
        TypedQuery<SupportTicket> rows = entityManager.createQuery(
                "SELECT t FROM SupportTicket t JOIN FETCH t.workspace w JOIN FETCH t.reporter r" + where
                        + " ORDER BY t.updatedAt DESC, t.ticketId DESC",
                SupportTicket.class);
        parameters.forEach((name, value) -> {
            count.setParameter(name, value);
            rows.setParameter(name, value);
        });
        long total = count.getSingleResult();
        if (total == 0) {
            return new Result(List.of(), 0);
        }
        rows.setFirstResult((int) Math.min((long) page * size, Integer.MAX_VALUE));
        rows.setMaxResults(size);
        return new Result(rows.getResultList(), total);
    }
}
