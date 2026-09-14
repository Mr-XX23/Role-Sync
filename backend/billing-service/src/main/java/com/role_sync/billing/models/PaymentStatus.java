package com.role_sync.billing.models;

/**
 * Lifecycle of a payment order. PENDING advances to a terminal state; the one exception is a
 * payment that settles after the order was marked FAILED or EXPIRED, which still becomes
 * SUCCEEDED because the money was taken. Credits are keyed by order, so replays stay safe.
 */
public enum PaymentStatus {
	/** Order row created, provider checkout not yet opened. */
	CREATED,
	/** Handed to the provider; awaiting a webhook from the provider. */
	PENDING,
	/** Provider confirmed payment. Credits granted. */
	SUCCEEDED,
	/** Provider reported a failure. */
	FAILED,
	/** Checkout window expired without payment. */
	EXPIRED,
	/** Payment was refunded after the fact. */
	REFUNDED;

	public boolean isTerminal() {
		return this == SUCCEEDED || this == FAILED || this == EXPIRED || this == REFUNDED;
	}
}
