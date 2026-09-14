package com.role_sync.billing.controllers;

import com.role_sync.billing.dto.PaymentOrderResponse;
import com.role_sync.billing.models.PaymentOrder;
import com.role_sync.billing.repository.PaymentOrderRepository;
import com.role_sync.billing.security.WorkspaceMembershipGuard;
import com.role_sync.billing.services.BillingException;
import com.role_sync.billing.services.OrderReconciler;
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
 * Purchase history and order status. The success page polls one order after the buyer returns
 * from Stripe. The redirect itself proves nothing: a pending order is settled by the webhook, or by
 * {@link OrderReconciler} asking Stripe directly when the webhook hasn't arrived.
 */
@RestController
@RequestMapping("/api/v1/billing")
public class PaymentOrderController {

	private final PaymentOrderRepository orders;
	private final WorkspaceMembershipGuard membership;
	private final OrderReconciler reconciler;

	public PaymentOrderController(PaymentOrderRepository orders, WorkspaceMembershipGuard membership,
	                              OrderReconciler reconciler) {
		this.orders = orders;
		this.membership = membership;
		this.reconciler = reconciler;
	}

	@GetMapping("/orders/{orderId}")
	public ResponseEntity<PaymentOrderResponse> get(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@PathVariable UUID orderId) {

		UUID userId = CallerIdentity.requireUserId(userIdHeader);
		PaymentOrder order = orders.findById(orderId)
				.orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Order not found"));

		// Only members of the buying workspace may see it; everyone else gets the same 404 as a
		// missing order, so order ids can't be probed.
		try {
			membership.requireMember(userId, order.getAccountId());
		}
		catch (BillingException notMember) {
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Order not found");
		}
		return ResponseEntity.ok(PaymentOrderResponse.from(reconciler.refresh(order)));
	}

	@GetMapping("/orders")
	public ResponseEntity<List<PaymentOrderResponse>> list(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
			@RequestParam(value = "workspaceId", required = false) UUID workspaceId) {

		UUID userId = CallerIdentity.requireUserId(userIdHeader);
		UUID accountId = CallerIdentity.requireWorkspaceId(tenantHeader, workspaceId);
		membership.requireMember(userId, accountId);

		return ResponseEntity.ok(orders.findTop50ByAccountIdOrderByCreatedAtDesc(accountId).stream()
				.map(PaymentOrderResponse::from)
				.toList());
	}
}
