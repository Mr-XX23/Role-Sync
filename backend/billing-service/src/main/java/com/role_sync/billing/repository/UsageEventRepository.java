package com.role_sync.billing.repository;

import com.role_sync.billing.models.UsageEvent;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public interface UsageEventRepository extends JpaRepository<UsageEvent, UUID> {

	boolean existsByIdempotencyKey(String idempotencyKey);

	/** Rows of [category, millicredits, costUsd] for one workspace since {@code from}. */
	@Query("""
			select u.category, coalesce(sum(u.millicredits), 0), coalesce(sum(u.costUsd), 0)
			from UsageEvent u
			where u.workspaceId = :workspaceId and u.createdAt >= :from
			group by u.category
			""")
	List<Object[]> sumByCategoryForWorkspace(@Param("workspaceId") UUID workspaceId, @Param("from") Instant from);

	/** Rows of [category, millicredits, costUsd] across all workspaces since {@code from}. */
	@Query("""
			select u.category, coalesce(sum(u.millicredits), 0), coalesce(sum(u.costUsd), 0)
			from UsageEvent u
			where u.createdAt >= :from and (:workspaceId is null or u.workspaceId = :workspaceId)
			group by u.category
			""")
	List<Object[]> sumByCategory(@Param("from") Instant from, @Param("workspaceId") UUID workspaceId);

	/** Rows of [operation, category, count, millicredits, costUsd]. */
	@Query("""
			select u.operation, u.category, count(u), coalesce(sum(u.millicredits), 0), coalesce(sum(u.costUsd), 0)
			from UsageEvent u
			where u.createdAt >= :from and (:workspaceId is null or u.workspaceId = :workspaceId)
			group by u.operation, u.category
			order by coalesce(sum(u.millicredits), 0) desc
			""")
	List<Object[]> sumByOperation(@Param("from") Instant from, @Param("workspaceId") UUID workspaceId);

	/** Rows of [model, count, inputTokens, cachedInputTokens, outputTokens, millicredits, costUsd]. */
	@Query("""
			select u.model, count(u), coalesce(sum(u.inputTokens), 0), coalesce(sum(u.cachedInputTokens), 0),
			       coalesce(sum(u.outputTokens), 0), coalesce(sum(u.millicredits), 0), coalesce(sum(u.costUsd), 0)
			from UsageEvent u
			where u.createdAt >= :from and u.model is not null and (:workspaceId is null or u.workspaceId = :workspaceId)
			group by u.model
			order by coalesce(sum(u.costUsd), 0) desc
			""")
	List<Object[]> sumByModel(@Param("from") Instant from, @Param("workspaceId") UUID workspaceId);

	/** Rows of [workspaceId, millicredits, costUsd], biggest first. */
	@Query("""
			select u.workspaceId, coalesce(sum(u.millicredits), 0), coalesce(sum(u.costUsd), 0)
			from UsageEvent u
			where u.createdAt >= :from
			group by u.workspaceId
			order by coalesce(sum(u.millicredits), 0) desc
			""")
	List<Object[]> topWorkspaces(@Param("from") Instant from, Pageable pageable);

	/** Individual events in a window, used to build a per-day series without database-specific date SQL. */
	@Query("select u.createdAt, u.millicredits, u.costUsd from UsageEvent u where u.createdAt >= :from")
	List<Object[]> pointsSince(@Param("from") Instant from);

	@Query("select coalesce(sum(u.costUsd), 0) from UsageEvent u where u.createdAt >= :from")
	java.math.BigDecimal sumCostSince(@Param("from") Instant from);
}
