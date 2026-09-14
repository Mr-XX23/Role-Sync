package com.role_sync.billing.models;

/** Why a workspace balance changed. Status changes are recorded too, with zero credits. */
public enum CreditTransactionType {
	WELCOME_GRANT,
	PURCHASE,
	ADMIN_GRANT,
	ADMIN_DEDUCT,
	USAGE,
	REFUND_CLAWBACK,
	ACCOUNT_SUSPENDED,
	ACCOUNT_REACTIVATED
}
