package com.role_sync.billing.repository;

import com.role_sync.billing.models.PaymentEvent;
import com.role_sync.billing.models.PaymentProviderKey;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface PaymentEventRepository extends JpaRepository<PaymentEvent, UUID> {

	/** Webhook replay guard: providers retry, we must only act once. */
	boolean existsByProviderAndProviderEventId(PaymentProviderKey provider, String providerEventId);
}
