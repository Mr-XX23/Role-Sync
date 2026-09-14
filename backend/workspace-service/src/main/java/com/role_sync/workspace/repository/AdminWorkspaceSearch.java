package com.role_sync.workspace.repository;

import com.role_sync.workspace.models.Workspace;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.TypedQuery;
import org.springframework.stereotype.Repository;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

/**
 * The platform admin console's workspace list: optional filters, newest first, one page at a time.
 * Only the filters that are set become JPQL clauses (no null parameters, which PostgreSQL can't type).
 */
@Repository
public class AdminWorkspaceSearch {

    @PersistenceContext
    private EntityManager entityManager;

    /**
     * @param text              case-insensitive substring of the workspace name or its owner's name; null for any
     * @param active            true for active, false for suspended; null for both
     * @param planId            workspaces on this plan; null for any
     * @param includeUnassigned with {@code planId}: also workspaces with no plan (they are on the default plan)
     */
    public record Criteria(String text, Boolean active, UUID planId, boolean includeUnassigned) {
    }

    public record Result(List<Workspace> workspaces, long total) {
    }

    /** One page of matching workspaces with their owners loaded, and how many match in all. */
    public Result search(Criteria criteria, int page, int size) {
        StringBuilder where = new StringBuilder(" WHERE 1 = 1");
        Map<String, Object> parameters = new LinkedHashMap<>();
        if (criteria.text() != null && !criteria.text().isBlank()) {
            where.append(" AND (LOWER(w.name) LIKE :text ESCAPE '!'")
                    .append(" OR LOWER(COALESCE(o.displayName, '')) LIKE :text ESCAPE '!'")
                    .append(" OR LOWER(CONCAT(COALESCE(o.firstName, ''), ' ', COALESCE(o.lastName, ''))) LIKE :text ESCAPE '!')");
            parameters.put("text", likePattern(criteria.text()));
        }
        if (criteria.active() != null) {
            where.append(" AND w.isActive = :active");
            parameters.put("active", criteria.active());
        }
        if (criteria.planId() != null) {
            where.append(criteria.includeUnassigned() ? " AND (w.planId = :planId OR w.planId IS NULL)" : " AND w.planId = :planId");
            parameters.put("planId", criteria.planId());
        }

        TypedQuery<Long> count = entityManager.createQuery(
                "SELECT COUNT(w) FROM Workspace w JOIN w.owner o" + where, Long.class);
        TypedQuery<Workspace> rows = entityManager.createQuery(
                "SELECT w FROM Workspace w JOIN FETCH w.owner o" + where + " ORDER BY w.createdAt DESC, w.workspaceId DESC",
                Workspace.class);
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

    /** A LIKE pattern matching the text anywhere, with LIKE's own wildcards (and the escape character) taken literally. */
    static String likePattern(String text) {
        String escaped = text.trim().toLowerCase(Locale.ROOT)
                .replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");
        return "%" + escaped + "%";
    }
}
