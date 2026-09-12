package com.role_sync.billing.models;

/**
 * Lifecycle of a payment order. Only PENDING may advance to a terminal state,
 * which is what makes webhook replay safe.
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
