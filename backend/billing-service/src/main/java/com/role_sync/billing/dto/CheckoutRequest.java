package com.role_sync.billing.dto;

import com.role_sync.billing.models.PaymentProviderKey;
import jakarta.validation.constraints.NotBlank;

import java.util.UUID;

/**
 * Request to buy a credit package.
 *
 * <p>Note what is absent: there is no amount and no credit count. Those come from
 * server-side configuration, so the price cannot be set by the caller.
 *
 * @param packageCode which configured package to buy
 * @param workspaceId workspace to credit; ignored when X-Tenant-Id is supplied
 * @param provider    gateway to use; defaults to STRIPE
 */
public record CheckoutRequest(
		@NotBlank(message = "packageCode is required") String packageCode,
		UUID workspaceId,
		PaymentProviderKey provider
) {

	public PaymentProviderKey providerOrDefault() {
		return provider == null ? PaymentProviderKey.STRIPE : provider;
	}
}
