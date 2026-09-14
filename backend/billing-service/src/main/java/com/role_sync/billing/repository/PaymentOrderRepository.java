package com.role_sync.billing.repository;

import com.role_sync.billing.models.PaymentOrder;
import com.role_sync.billing.models.PaymentStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface PaymentOrderRepository extends JpaRepository<PaymentOrder, UUID> {

	/** Makes repeated checkout attempts with the same key return the same order. */
	Optional<PaymentOrder> findByIdempotencyKey(String idempotencyKey);

	/** Resolves the order a provider checkout webhook refers to. */
	Optional<PaymentOrder> findByProviderRef(String providerRef);

	/** Resolves the order a provider payment or refund webhook refers to. */
	Optional<PaymentOrder> findByProviderPaymentRef(String providerPaymentRef);

	List<PaymentOrder> findTop50ByAccountIdOrderByCreatedAtDesc(UUID accountId);

	Page<PaymentOrder> findAllByOrderByCreatedAtDesc(Pageable pageable);

	Page<PaymentOrder> findByStatusOrderByCreatedAtDesc(PaymentStatus status, Pageable pageable);

	/** Rows of [currency, amountMinor, payments] for settled orders since {@code from}. */
	@Query("""
			select o.currency, coalesce(sum(o.amountMinor), 0), count(o)
			from PaymentOrder o
			where o.status = com.role_sync.billing.models.PaymentStatus.SUCCEEDED and o.paidAt >= :from
			group by o.currency
			""")
	List<Object[]> revenueSince(@Param("from") Instant from);
}
