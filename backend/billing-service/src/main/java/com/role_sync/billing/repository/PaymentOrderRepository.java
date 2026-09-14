package com.role_sync.billing.repository;

import com.role_sync.billing.models.PaymentOrder;
import org.springframework.data.jpa.repository.JpaRepository;

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

	/**
	 * Scoped to the caller as well as the workspace. Until billing verifies
	 * workspace membership against workspace-service, scoping by user is what stops
	 * one member reading another workspace purchase history.
	 */
	List<PaymentOrder> findTop50ByAccountIdAndUserIdOrderByCreatedAtDesc(UUID accountId, UUID userId);
}
