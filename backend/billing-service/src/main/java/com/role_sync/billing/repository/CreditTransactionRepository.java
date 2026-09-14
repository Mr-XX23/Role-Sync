package com.role_sync.billing.repository;

import com.role_sync.billing.models.CreditTransaction;
import com.role_sync.billing.models.CreditTransactionType;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.UUID;

public interface CreditTransactionRepository extends JpaRepository<CreditTransaction, UUID> {

	boolean existsByIdempotencyKey(String idempotencyKey);

	List<CreditTransaction> findByWorkspaceIdOrderByCreatedAtDesc(UUID workspaceId, Pageable pageable);

	@Query("""
			select coalesce(sum(t.amountMillicredits), 0) from CreditTransaction t
			where t.type in :types and t.createdAt >= :from
			""")
	long sumByTypesSince(@Param("types") Collection<CreditTransactionType> types, @Param("from") Instant from);
}
