package com.role_sync.billing.payments;

/** Provider-neutral meaning of a webhook, so fulfilment logic stays gateway-agnostic. */
public enum WebhookResultKind {
	PAID,
	FAILED,
	EXPIRED,
	REFUNDED,
	/** Received and verified, but not a state change we act on. */
	IGNORED
}
