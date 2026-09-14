package com.role_sync.billing.payments.stripe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.role_sync.billing.configurations.BillingProperties;
import com.role_sync.billing.models.PaymentOrder;
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

import java.util.Optional;
import java.util.UUID;

/**
 * Stripe gateway, implemented with Stripe Checkout.
 *
 * <p>Checkout is a hosted page, so card details never reach our servers. The session carries a
 * dynamic price built from our own configured package, so pricing stays owned by this platform.
 *
 * <p>Webhook payloads are read with Gson, which stripe-java already ships, rather than an injected
 * Jackson mapper: Spring Boot 4 configures Jackson 3, and depending on a Jackson 2 bean here would
 * fail at startup.
 */
@Component
public class StripePaymentProvider implements PaymentProvider {

	private static final Logger log = LoggerFactory.getLogger(StripePaymentProvider.class);

	static final String METADATA_ORDER_ID = "order_id";
	static final String METADATA_ACCOUNT_ID = "account_id";
	static final String METADATA_PACKAGE_CODE = "package_code";
	static final String METADATA_CREDITS = "credits";
	/** Event type recorded when an order is settled from a Checkout Session look-up instead of a webhook. */
	static final String LOOKUP_EVENT = "checkout.session.lookup";

	private final BillingProperties properties;

	public StripePaymentProvider(BillingProperties properties) {
		this.properties = properties;
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

		// The idempotency key means a retried checkout call reuses the same session instead of
		// creating a second one the buyer could also pay.
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
			// Verifies the HMAC over the exact raw bytes and enforces the timestamp tolerance,
			// which is what makes a forged or replayed request fail here.
			event = Webhook.constructEvent(rawBody, signatureHeader, secret);
		}
		catch (Exception ex) {
			throw new PaymentProviderException("Stripe signature verification failed", ex);
		}

		JsonObject object;
		try {
			object = JsonParser.parseString(rawBody).getAsJsonObject()
					.getAsJsonObject("data")
					.getAsJsonObject("object");
		}
		catch (RuntimeException ex) {
			throw new PaymentProviderException("Stripe webhook body was not readable JSON", ex);
		}
		if (object == null) {
			throw new PaymentProviderException("Stripe webhook had no data.object");
		}

		String type = event.getType();
		String providerRef = text(object, "id");
		String orderId = text(child(object, "metadata"), METADATA_ORDER_ID);
		if (orderId == null) {
			orderId = text(object, "client_reference_id");
		}

		return switch (type) {
			case "checkout.session.completed", "checkout.session.async_payment_succeeded" -> {
				// A completed session is only money in the bank when it is also paid; asynchronous
				// methods can complete the session while still unpaid.
				String paymentStatus = text(object, "payment_status");
				boolean paid = "paid".equals(paymentStatus);
				yield new WebhookOutcome(
						event.getId(), type,
						paid ? WebhookResultKind.PAID : WebhookResultKind.IGNORED,
						providerRef,
						text(object, "payment_intent"),
						orderId,
						number(object, "amount_total"),
						text(object, "currency"),
						paid ? "checkout session paid" : "checkout completed but payment_status=" + paymentStatus);
			}
			case "checkout.session.expired" -> new WebhookOutcome(
					event.getId(), type, WebhookResultKind.EXPIRED, providerRef,
					text(object, "payment_intent"), orderId,
					number(object, "amount_total"), text(object, "currency"),
					"checkout session expired");
			case "checkout.session.async_payment_failed" -> new WebhookOutcome(
					event.getId(), type, WebhookResultKind.FAILED, providerRef,
					text(object, "payment_intent"), orderId,
					number(object, "amount_total"), text(object, "currency"),
					"asynchronous payment failed");
			// A declined card inside Checkout: the buyer can try another card in the same session.
			case "payment_intent.payment_failed" -> new WebhookOutcome(
					event.getId(), type, WebhookResultKind.ATTEMPT_FAILED, null, providerRef, orderId,
					number(object, "amount"), text(object, "currency"),
					"payment failed: " + text(child(object, "last_payment_error"), "message"));
			case "charge.refunded" -> new WebhookOutcome(
					event.getId(), type, WebhookResultKind.REFUNDED, null,
					text(object, "payment_intent"), orderId,
					number(object, "amount_refunded"), text(object, "currency"),
					"charge refunded");
			// Disputes carry no metadata; the order is found by its PaymentIntent.
			case "charge.dispute.created" -> new WebhookOutcome(
					event.getId(), type, WebhookResultKind.DISPUTED, null,
					text(object, "payment_intent"), orderId,
					number(object, "amount"), text(object, "currency"),
					"payment disputed: " + text(object, "reason"));
			default -> new WebhookOutcome(
					event.getId(), type, WebhookResultKind.IGNORED, providerRef, null, orderId,
					0L, null, "unhandled event type");
		};
	}

	@Override
	public Optional<WebhookOutcome> lookupCheckout(PaymentOrder order) {
		if (!isEnabled() || order.getProviderRef() == null || order.getProviderRef().isBlank()) {
			return Optional.empty();
		}
		try {
			Session session = Session.retrieve(order.getProviderRef(),
					RequestOptions.builder().setApiKey(properties.getStripe().getSecretKey()).build());
			return outcomeOf(session, order.getId());
		}
		catch (StripeException ex) {
			// A restricted key needs "Checkout Sessions: Read" for this; the webhook still settles the order.
			log.warn("Could not look up Stripe checkout {} for order {}: {}", order.getProviderRef(), order.getId(), ex.getMessage());
			return Optional.empty();
		}
	}

	/** What a retrieved Checkout Session says about its order: paid, expired, or nothing yet. */
	static Optional<WebhookOutcome> outcomeOf(Session session, UUID orderId) {
		long amount = session.getAmountTotal() == null ? 0L : session.getAmountTotal();
		// One audit event per session and result, so repeated look-ups are recorded once and a
		// webhook arriving later, with its own event id, finds the order already settled.
		String eventId = "lookup:" + session.getId() + ":";
		if ("paid".equals(session.getPaymentStatus())) {
			return Optional.of(new WebhookOutcome(eventId + "paid", LOOKUP_EVENT, WebhookResultKind.PAID,
					session.getId(), session.getPaymentIntent(), orderId.toString(), amount, session.getCurrency(),
					"checkout session paid (confirmed with the Stripe API)"));
		}
		if ("expired".equals(session.getStatus())) {
			return Optional.of(new WebhookOutcome(eventId + "expired", LOOKUP_EVENT, WebhookResultKind.EXPIRED,
					session.getId(), session.getPaymentIntent(), orderId.toString(), amount, session.getCurrency(),
					"checkout session expired (confirmed with the Stripe API)"));
		}
		return Optional.empty();
	}

	private static JsonObject child(JsonObject node, String field) {
		if (node == null) {
			return null;
		}
		JsonElement value = node.get(field);
		return value != null && value.isJsonObject() ? value.getAsJsonObject() : null;
	}

	private static String text(JsonObject node, String field) {
		if (node == null) {
			return null;
		}
		JsonElement value = node.get(field);
		return value == null || value.isJsonNull() || !value.isJsonPrimitive() ? null : value.getAsString();
	}

	private static long number(JsonObject node, String field) {
		JsonElement value = node == null ? null : node.get(field);
		if (value == null || value.isJsonNull() || !value.isJsonPrimitive()) {
			return 0L;
		}
		try {
			return value.getAsLong();
		}
		catch (NumberFormatException ex) {
			return 0L;
		}
	}
}
