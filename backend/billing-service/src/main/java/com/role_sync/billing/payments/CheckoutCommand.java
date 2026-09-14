package com.role_sync.billing.payments;

import java.util.UUID;

/**
 * Everything a provider needs to open a hosted checkout.
 *
 * <p>The amount comes from our own configuration, never from the HTTP request,
 * so a caller cannot choose what it pays.
 */
public record CheckoutCommand(
		UUID orderId,
		UUID accountId,
		UUID userId,
		String packageCode,
		String packageName,
		long credits,
		long amountMinor,
		String currency,
		String idempotencyKey,
		String successUrl,
		String cancelUrl
) {
}
