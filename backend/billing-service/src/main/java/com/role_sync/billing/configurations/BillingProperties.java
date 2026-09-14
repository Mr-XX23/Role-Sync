package com.role_sync.billing.configurations;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * All billing configuration, bound from the config server.
 *
 * <p>Prices, the credit value and every provider rate live here rather than in code, so they can
 * change without a deploy. Each order and usage event stores the amounts it was charged, so a
 * later change never rewrites history.
 */
@ConfigurationProperties(prefix = "billing")
@Getter
@Setter
public class BillingProperties {

	/** Where Stripe sends the buyer after paying; billing appends {@code orderId}. */
	private String successUrl = "http://localhost:5173/billing/success";

	/** Where Stripe sends the buyer who abandons checkout. */
	private String cancelUrl = "http://localhost:5173/pricing?checkout=cancelled";

	/** Shared secret other services send as X-Internal-Token. Empty disables the internal API. */
	private String internalToken = "";

	private String authServiceUrl = "http://auth-service:8082";

	private String workspaceServiceUrl = "http://workspace-service:8083";

	private Stripe stripe = new Stripe();

	private List<CreditPackage> packages = new ArrayList<>();

	private Credits credits = new Credits();

	private Rates rates = new Rates();

	/** "What credits buy" lines for the public pricing page. */
	private List<Example> examples = new ArrayList<>();

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
		/** Stripe secret or restricted key. Use a test key (sk_test_ / rk_test_) outside production. */
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

	@Getter
	@Setter
	public static class Credits {
		/** What one credit is worth to the user. */
		private BigDecimal priceUsd = new BigDecimal("0.01");
		/** Gross margin the charge formula targets; cost per credit = price × (1 − margin). */
		private BigDecimal targetMargin = new BigDecimal("0.80");
		/** Added to measured cost before it becomes credits, to absorb variance. */
		private BigDecimal buffer = new BigDecimal("0.15");
		/** Credits every new user's workspace receives once. */
		private long signupGrant = 500;
		/** The UI warns below this balance. */
		private long lowBalanceThreshold = 50;
		/** Largest single admin grant or deduction, in credits. */
		private long maxAdminAdjustment = 1_000_000;

		public BigDecimal costPerCredit() {
			return priceUsd.multiply(BigDecimal.ONE.subtract(targetMargin));
		}
	}

	@Getter
	@Setter
	public static class Rates {
		/** Used for a model no rule matches, so an unexpected model is still charged. */
		private ModelRate defaultModel = new ModelRate();
		private List<ModelRate> models = new ArrayList<>();
		private List<UnitRate> units = new ArrayList<>();
	}

	public enum MatchType {
		EXACT,
		PREFIX,
		SUFFIX,
		CONTAINS
	}

	@Getter
	@Setter
	public static class ModelRate {
		private String pattern = "";
		private MatchType match = MatchType.EXACT;
		/** USD per 1M input tokens. */
		private BigDecimal inputPerMillion = new BigDecimal("0.30");
		/** USD per 1M output tokens, thinking included. */
		private BigDecimal outputPerMillion = new BigDecimal("2.50");
		/** USD per 1M cached input tokens; the input rate when unset. */
		private BigDecimal cachedInputPerMillion;

		public boolean matches(String model) {
			if (model == null || pattern == null || pattern.isBlank()) {
				return false;
			}
			String candidate = model.toLowerCase();
			String rule = pattern.toLowerCase();
			return switch (match) {
				case EXACT -> candidate.equals(rule);
				case PREFIX -> candidate.startsWith(rule);
				case SUFFIX -> candidate.endsWith(rule);
				case CONTAINS -> candidate.contains(rule);
			};
		}

		public BigDecimal cachedRate() {
			return cachedInputPerMillion != null ? cachedInputPerMillion : inputPerMillion;
		}
	}

	@Getter
	@Setter
	public static class UnitRate {
		private String unit;
		/** USD per unit, e.g. per parsed page or per search. */
		private BigDecimal usd = BigDecimal.ZERO;
	}

	@Getter
	@Setter
	public static class Example {
		private String label;
		private long credits;
	}
}
