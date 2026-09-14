package com.role_sync.billing.controllers;

import com.role_sync.billing.dto.CheckoutRequest;
import com.role_sync.billing.dto.PaymentOrderResponse;
import com.role_sync.billing.models.PaymentOrder;
import com.role_sync.billing.services.CheckoutService;
import com.role_sync.billing.utils.CallerIdentity;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

/** Starts a credit purchase and hands back a hosted checkout URL. */
@RestController
@RequestMapping("/api/v1/billing")
public class CheckoutController {

	private final CheckoutService checkoutService;

	public CheckoutController(CheckoutService checkoutService) {
		this.checkoutService = checkoutService;
	}

	@PostMapping("/checkout")
	public ResponseEntity<PaymentOrderResponse> checkout(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
			@RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
			@Valid @RequestBody CheckoutRequest request) {

		UUID userId = CallerIdentity.requireUserId(userIdHeader);
		UUID workspaceId = CallerIdentity.requireWorkspaceId(tenantHeader, request.workspaceId());

		PaymentOrder order = checkoutService.start(
				userId,
				workspaceId,
				request.packageCode(),
				request.providerOrDefault(),
				idempotencyKey);

		return ResponseEntity.ok(PaymentOrderResponse.from(order));
	}
}
