package com.role_sync.billing.payments;

/** Provider-neutral meaning of a webhook, so fulfilment logic stays gateway-agnostic. */
public enum WebhookResultKind {
	PAID,
	/** The checkout is over and nothing was paid. */
	FAILED,
	/**
	 * One payment attempt failed (a declined card) but the checkout is still open, so the buyer can
	 * retry and pay. Must not close the order.
	 */
	ATTEMPT_FAILED,
	EXPIRED,
	REFUNDED,
	/** The buyer's bank opened a chargeback against a settled payment. */
	DISPUTED,
	/** Received and verified, but not a state change we act on. */
	IGNORED
}
