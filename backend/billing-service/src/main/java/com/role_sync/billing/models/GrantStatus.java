package com.role_sync.billing.models;

/** State of a credit grant produced by a paid order. */
public enum GrantStatus {
	/** Payment settled; the credit ledger has not consumed this yet. */
	PENDING,
	/** The credit ledger has applied this grant to the account balance. */
	APPLIED
}
