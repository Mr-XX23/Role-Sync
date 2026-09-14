package com.role_sync.billing.repository;

import com.role_sync.billing.models.CreditGrant;
import com.role_sync.billing.models.GrantStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface CreditGrantRepository extends JpaRepository<CreditGrant, UUID> {

	boolean existsByOrderId(UUID orderId);

	/** The credit ledger will drain these in the next slice. */
	List<CreditGrant> findTop200ByStatusOrderByCreatedAtAsc(GrantStatus status);
}
