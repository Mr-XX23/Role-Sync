package com.role_sync.billing.payments;

import com.role_sync.billing.models.PaymentProviderKey;

/**
 * A payment gateway.
 *
 * <p>Stripe is the first implementation. eSewa and Khalti implement this same
 * interface, so adding them needs a new class and configuration only, with no
 * change to the controllers or to fulfilment.
 */
public interface PaymentProvider {

	PaymentProviderKey key();

	/** True when this provider has the credentials it needs to operate. */
	boolean isEnabled();

	/** Opens a hosted checkout for an order that is already persisted. */
	ProviderCheckout createCheckout(CheckoutCommand command);

	/**
	 * Verifies a webhook and normalises it.
	 *
	 * @param rawBody         the exact bytes received, as a string; signatures cover
	 *                        the raw payload, so this must not be re-serialised
	 * @param signatureHeader provider signature header value
	 * @throws PaymentProviderException when the signature cannot be verified
	 */
	WebhookOutcome parseWebhook(String rawBody, String signatureHeader);
}
