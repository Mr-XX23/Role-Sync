package com.role_sync.billing.payments;

/**
 * What a provider hands back when a checkout is opened.
 *
 * @param providerRef  provider-side id we can later match a webhook against
 * @param checkoutUrl  hosted page the buyer is redirected to
 */
public record ProviderCheckout(String providerRef, String checkoutUrl) {
}
