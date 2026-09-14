package com.role_sync.billing.dto;

import com.role_sync.billing.models.PaymentOrder;
import com.role_sync.billing.models.PaymentProviderKey;
import com.role_sync.billing.models.PaymentStatus;

import java.time.Instant;
import java.util.UUID;

/** An order as returned to the dashboard. */
public record PaymentOrderResponse(
		UUID orderId,
		UUID workspaceId,
		UUID userId,
		String packageCode,
		long credits,
		long amountMinor,
		String currency,
		PaymentProviderKey provider,
		PaymentStatus status,
		String checkoutUrl,
		String failureReason,
		Instant paidAt,
		Instant createdAt
) {

	public static PaymentOrderResponse from(PaymentOrder order) {
		return new PaymentOrderResponse(
				order.getId(),
				order.getAccountId(),
				order.getUserId(),
				order.getPackageCode(),
				order.getCredits(),
				order.getAmountMinor(),
				order.getCurrency(),
				order.getProvider(),
				order.getStatus(),
				order.getCheckoutUrl(),
				order.getFailureReason(),
				order.getPaidAt(),
				order.getCreatedAt());
	}
}
