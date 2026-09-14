package com.role_sync.billing.controllers;

import com.role_sync.billing.dto.PaymentOrderResponse;
import com.role_sync.billing.models.PaymentOrder;
import com.role_sync.billing.repository.PaymentOrderRepository;
import com.role_sync.billing.utils.CallerIdentity;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.UUID;

/**
 * Purchase history and order status.
 *
 * <p>The dashboard polls a single order after the buyer returns from the gateway,
 * because the redirect itself proves nothing; only the webhook settles an order.
 */
@RestController
@RequestMapping("/api/v1/billing")
public class PaymentOrderController {

	private final PaymentOrderRepository orders;

	public PaymentOrderController(PaymentOrderRepository orders) {
		this.orders = orders;
	}

	@GetMapping("/orders/{orderId}")
	public ResponseEntity<PaymentOrderResponse> get(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@PathVariable UUID orderId) {

		UUID userId = CallerIdentity.requireUserId(userIdHeader);

		PaymentOrder order = orders.findById(orderId)
				.orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Order not found"));

		// Deliberately a 404 rather than a 403, so this cannot be used to discover
		// which order ids exist.
		if (!order.getUserId().equals(userId)) {
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Order not found");
		}

		return ResponseEntity.ok(PaymentOrderResponse.from(order));
	}

	@GetMapping("/orders")
	public ResponseEntity<List<PaymentOrderResponse>> list(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
			@RequestParam(value = "workspaceId", required = false) UUID workspaceId) {

		UUID userId = CallerIdentity.requireUserId(userIdHeader);
		UUID accountId = CallerIdentity.requireWorkspaceId(tenantHeader, workspaceId);

		List<PaymentOrderResponse> result =
				orders.findTop50ByAccountIdAndUserIdOrderByCreatedAtDesc(accountId, userId).stream()
						.map(PaymentOrderResponse::from)
						.toList();

		return ResponseEntity.ok(result);
	}
}
