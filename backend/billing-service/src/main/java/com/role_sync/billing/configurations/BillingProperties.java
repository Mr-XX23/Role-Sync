package com.role_sync.billing.configurations;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * All billing configuration, bound from the config server.
 *
 * <p>Credit package pricing lives here rather than in code or in the payment
 * provider, so prices can change without a deploy and without touching Stripe.
 * Each order snapshots the values it was created with, so history stays correct.
 */
@ConfigurationProperties(prefix = "billing")
@Getter
@Setter
public class BillingProperties {

	/** Where the provider sends the buyer after a successful payment. */
	private String successUrl = "http://localhost:5173/billing/success";

	/** Where the provider sends the buyer if they abandon checkout. */
	private String cancelUrl = "http://localhost:5173/billing/cancel";

	private Stripe stripe = new Stripe();

	private List<CreditPackage> packages = new ArrayList<>();

	public Optional<CreditPackage> findPackage(String code) {
		if (code == null) {
			return Optional.empty();
		}
		return packages.stream()
				.filter(p -> p.getCode().equalsIgnoreCase(code) && p.isActive())
				.findFirst();
	}

	@Getter
	@Setter
	public static class Stripe {
		/** Stripe secret key. Use a test key (sk_test_...) outside production. */
		private String secretKey = "";
		/** Signing secret for the webhook endpoint (whsec_...). */
		private String webhookSecret = "";

		public boolean isConfigured() {
			return secretKey != null && !secretKey.isBlank();
		}
	}

	@Getter
	@Setter
	public static class CreditPackage {
		private String code;
		private String name;
		/** Credits granted when this package is paid for. */
		private long credits;
		/** Price in the MINOR unit of the currency (1000 = $10.00 when currency is usd). */
		private long priceMinor;
		private String currency = "usd";
		private boolean active = true;
		private int sort;
	}
}
