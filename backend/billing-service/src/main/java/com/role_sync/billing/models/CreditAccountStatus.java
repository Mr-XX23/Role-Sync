package com.role_sync.billing.models;

/** Whether a workspace may start new paid operations. */
public enum CreditAccountStatus {
	ACTIVE,
	/** A super admin stopped all credit spending for this workspace. */
	SUSPENDED
}
