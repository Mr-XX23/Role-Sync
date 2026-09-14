package com.role_sync.billing.payments;

/**
 * A verified webhook, normalised into provider-neutral terms.
 *
 * @param providerEventId provider event id, used to reject replays
 * @param eventType       raw provider event name, kept for audit
 * @param kind            what this means for the order
 * @param providerRef     provider-side checkout id this refers to
 * @param paymentRef      provider-side payment id, when known
 * @param orderId         our order id, when the provider echoed it back in metadata
 * @param amountMinor     amount the provider says was paid, for cross-checking
 * @param currency        currency the provider says was charged
 * @param message         short human-readable note for the audit row
 */
public record WebhookOutcome(
		String providerEventId,
		String eventType,
		WebhookResultKind kind,
		String providerRef,
		String paymentRef,
		String orderId,
		long amountMinor,
		String currency,
		String message
) {
}
