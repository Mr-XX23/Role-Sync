package com.role_sync.billing.controllers;

import com.role_sync.billing.models.PaymentProviderKey;
import com.role_sync.billing.payments.PaymentProvider;
import com.role_sync.billing.payments.PaymentProviderException;
import com.role_sync.billing.payments.PaymentProviderRegistry;
import com.role_sync.billing.payments.WebhookOutcome;
import com.role_sync.billing.services.PaymentFulfillmentService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * Stripe webhook receiver.
 *
 * <p>This endpoint is unauthenticated by design: Stripe has no session cookie, so
 * the gateway must treat this path as public and the request is authenticated by
 * its HMAC signature instead. Add {@code /api/v1/billing/webhooks/} to
 * GATEWAY_PUBLIC_PATHS or every callback is rejected with a 401.
 *
 * <p>The body is taken as a raw String because the signature covers the exact
 * bytes Stripe sent. Binding to a DTO would re-serialise it and break verification.
 */
@RestController
@RequestMapping("/api/v1/billing/webhooks")
public class StripeWebhookController {

	private static final Logger log = LoggerFactory.getLogger(StripeWebhookController.class);

	private final PaymentProviderRegistry registry;
	private final PaymentFulfillmentService fulfillment;

	public StripeWebhookController(PaymentProviderRegistry registry, PaymentFulfillmentService fulfillment) {
		this.registry = registry;
		this.fulfillment = fulfillment;
	}

	@PostMapping("/stripe")
	public ResponseEntity<Map<String, String>> stripe(
			@RequestHeader(value = "Stripe-Signature", required = false) String signature,
			@RequestBody String payload) {

		PaymentProvider provider = registry.find(PaymentProviderKey.STRIPE)
				.orElseThrow(() -> new IllegalStateException("Stripe provider is not registered"));

		final WebhookOutcome outcome;
		try {
			outcome = provider.parseWebhook(payload, signature);
		}
		catch (PaymentProviderException ex) {
			// A signature that does not verify is never worth retrying, so answer 400.
			log.warn("Rejected Stripe webhook: {}", ex.getMessage());
			return ResponseEntity.badRequest().body(Map.of("error", "signature verification failed"));
		}

		try {
			String result = fulfillment.process(PaymentProviderKey.STRIPE, outcome);
			return ResponseEntity.ok(Map.of("received", "true", "result", result));
		}
		catch (RuntimeException ex) {
			// Answer 5xx so Stripe retries; the event id keeps the retry safe.
			log.error("Failed to process Stripe event {}: {}", outcome.providerEventId(), ex.getMessage(), ex);
			return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
					.body(Map.of("error", "processing failed"));
		}
	}
}
