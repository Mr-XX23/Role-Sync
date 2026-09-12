package com.role_sync.billing.payments.stripe;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.role_sync.billing.configurations.BillingProperties;
import com.role_sync.billing.models.PaymentProviderKey;
import com.role_sync.billing.payments.CheckoutCommand;
import com.role_sync.billing.payments.PaymentProvider;
import com.role_sync.billing.payments.PaymentProviderException;
import com.role_sync.billing.payments.ProviderCheckout;
import com.role_sync.billing.payments.WebhookOutcome;
import com.role_sync.billing.payments.WebhookResultKind;
import com.stripe.exception.StripeException;
import com.stripe.model.Event;
import com.stripe.model.checkout.Session;
import com.stripe.net.RequestOptions;
import com.stripe.net.Webhook;
import com.stripe.param.checkout.SessionCreateParams;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Stripe gateway, implemented with Stripe Checkout.
 *
 * <p>Checkout is a hosted page, so card details never reach our servers and we
 * stay out of PCI scope. We create the session with a dynamic price built from
 * our own configured package, rather than a Stripe Price object, so pricing stays
 * owned by this platform and not duplicated in the Stripe dashboard.
 */
@Component
public class StripePaymentProvider implements PaymentProvider {

	private static final Logger log = LoggerFactory.getLogger(StripePaymentProvider.class);

	static final String METADATA_ORDER_ID = "order_id";
	static final String METADATA_ACCOUNT_ID = "account_id";
	static final String METADATA_PACKAGE_CODE = "package_code";
	static final String METADATA_CREDITS = "credits";

	private final BillingProperties properties;
	private final ObjectMapper objectMapper;

	public StripePaymentProvider(BillingProperties properties, ObjectMapper objectMapper) {
		this.properties = properties;
		this.objectMapper = objectMapper;
	}

	@Override
	public PaymentProviderKey key() {
		return PaymentProviderKey.STRIPE;
	}

	@Override
	public boolean isEnabled() {
		return properties.getStripe().isConfigured();
	}

	@Override
	public ProviderCheckout createCheckout(CheckoutCommand command) {
		if (!isEnabled()) {
			throw new PaymentProviderException("Stripe is not configured: set billing.stripe.secret-key");
		}

		SessionCreateParams params = SessionCreateParams.builder()
				.setMode(SessionCreateParams.Mode.PAYMENT)
				.setSuccessUrl(command.successUrl())
				.setCancelUrl(command.cancelUrl())
				// Lets us match a webhook back to our order even if metadata is dropped.
				.setClientReferenceId(command.orderId().toString())
				.putMetadata(METADATA_ORDER_ID, command.orderId().toString())
				.putMetadata(METADATA_ACCOUNT_ID, command.accountId().toString())
				.putMetadata(METADATA_PACKAGE_CODE, command.packageCode())
				.putMetadata(METADATA_CREDITS, String.valueOf(command.credits()))
				// Copy metadata onto the PaymentIntent so payment_intent.* events resolve too.
				.setPaymentIntentData(
						SessionCreateParams.PaymentIntentData.builder()
								.putMetadata(METADATA_ORDER_ID, command.orderId().toString())
								.putMetadata(METADATA_ACCOUNT_ID, command.accountId().toString())
								.build())
				.addLineItem(
						SessionCreateParams.LineItem.builder()
								.setQuantity(1L)
								.setPriceData(
										SessionCreateParams.LineItem.PriceData.builder()
												.setCurrency(command.currency())
												.setUnitAmount(command.amountMinor())
												.setProductData(
														SessionCreateParams.LineItem.PriceData.ProductData.builder()
																.setName(command.packageName())
																.setDescription(command.credits() + " Role-Sync credits")
																.build())
												.build())
								.build())
				.build();

		// The idempotency key means a retried checkout call reuses the same session
		// instead of creating a second one the buyer could also pay.
		RequestOptions options = RequestOptions.builder()
				.setApiKey(properties.getStripe().getSecretKey())
				.setIdempotencyKey(command.idempotencyKey())
				.build();

		try {
			Session session = Session.create(params, options);
			return new ProviderCheckout(session.getId(), session.getUrl());
		}
		catch (StripeException ex) {
			// Never log the API key or full request; the Stripe message is enough to triage.
			log.error("Stripe checkout creation failed for order {}: {}", command.orderId(), ex.getMessage());
			throw new PaymentProviderException("Stripe rejected the checkout request: " + ex.getMessage(), ex);
		}
	}

	@Override
	public WebhookOutcome parseWebhook(String rawBody, String signatureHeader) {
		String secret = properties.getStripe().getWebhookSecret();
		if (secret == null || secret.isBlank()) {
			throw new PaymentProviderException("Stripe webhook secret is not configured");
		}
		if (signatureHeader == null || signatureHeader.isBlank()) {
			throw new PaymentProviderException("Missing Stripe-Signature header");
		}

		final Event event;
		try {
			// Verifies the HMAC over the exact raw bytes and enforces the timestamp
			// tolerance, which is what makes a forged or replayed request fail here.
			event = Webhook.constructEvent(rawBody, signatureHeader, secret);
		}
		catch (Exception ex) {
			throw new PaymentProviderException("Stripe signature verification failed", ex);
		}

		JsonNode object;
		try {
			object = objectMapper.readTree(rawBody).path("data").path("object");
		}
		catch (Exception ex) {
			throw new PaymentProviderException("Stripe webhook body was not readable JSON", ex);
		}

		String type = event.getType();
		String providerRef = text(object, "id");
		String orderId = text(object.path("metadata"), METADATA_ORDER_ID);
		if (orderId == null) {
			orderId = text(object, "client_reference_id");
		}

		return switch (type) {
			case "checkout.session.completed" -> {
				// A completed session is only money in the bank when it is also paid;
				// asynchronous methods can complete the session while still unpaid.
				String paymentStatus = text(object, "payment_status");
				boolean paid = "paid".equals(paymentStatus);
				yield new WebhookOutcome(
						event.getId(), type,
						paid ? WebhookResultKind.PAID : WebhookResultKind.IGNORED,
						providerRef,
						text(object, "payment_intent"),
						orderId,
						object.path("amount_total").asLong(0L),
						text(object, "currency"),
						paid ? "checkout session paid" : "checkout completed but payment_status=" + paymentStatus);
			}
			case "checkout.session.expired" -> new WebhookOutcome(
					event.getId(), type, WebhookResultKind.EXPIRED, providerRef,
					text(object, "payment_intent"), orderId,
					object.path("amount_total").asLong(0L), text(object, "currency"),
					"checkout session expired");
			case "payment_intent.payment_failed" -> new WebhookOutcome(
					event.getId(), type, WebhookResultKind.FAILED, null, providerRef, orderId,
					object.path("amount").asLong(0L), text(object, "currency"),
					"payment failed: " + text(object.path("last_payment_error"), "message"));
			case "charge.refunded" -> new WebhookOutcome(
					event.getId(), type, WebhookResultKind.REFUNDED, null,
					text(object, "payment_intent"), orderId,
					object.path("amount_refunded").asLong(0L), text(object, "currency"),
					"charge refunded");
			default -> new WebhookOutcome(
					event.getId(), type, WebhookResultKind.IGNORED, providerRef, null, orderId,
					0L, null, "unhandled event type");
		};
	}

	private static String text(JsonNode node, String field) {
		JsonNode value = node.path(field);
		return value.isMissingNode() || value.isNull() ? null : value.asText();
	}
}
