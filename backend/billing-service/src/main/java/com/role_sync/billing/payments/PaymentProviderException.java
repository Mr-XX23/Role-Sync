package com.role_sync.billing.payments;

/** Raised when a gateway rejects a call or a webhook signature does not verify. */
public class PaymentProviderException extends RuntimeException {

	public PaymentProviderException(String message) {
		super(message);
	}

	public PaymentProviderException(String message, Throwable cause) {
		super(message, cause);
	}
}
