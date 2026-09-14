package com.role_sync.billing.services;

import com.role_sync.billing.dto.UsageItem;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class PricingServiceTest {

	private final PricingService pricing = new PricingService(TestBillingProperties.create());

	@Test
	void pricesTokensAtTheModelsRate() {
		BigDecimal cost = pricing.costOf(List.of(UsageItem.tokens("gemini-3.5-flash", 18_000, 0, 800)));

		// 18,000 × $1.50/M + 800 × $9.00/M
		assertThat(cost).isEqualByComparingTo("0.0342");
	}

	@Test
	void chargesCachedInputAtTheCachedRate() {
		BigDecimal cost = pricing.costOf(List.of(UsageItem.tokens("gemini-3.5-flash", 18_000, 18_000, 0)));

		assertThat(cost).isEqualByComparingTo("0.0027");
	}

	@Test
	void matchesExactBeforeSuffixAndPrefixRulesAndFallsBackToTheDefault() {
		assertThat(pricing.rateFor("gemini-3.5-flash-lite").getInputPerMillion()).isEqualByComparingTo("0.30");
		assertThat(pricing.rateFor("nvidia/nemotron-3.5-lightning:free").getInputPerMillion()).isEqualByComparingTo("0.10");
		assertThat(pricing.rateFor("some-new-model").getInputPerMillion()).isEqualByComparingTo("0.30");
	}

	@Test
	void pricesUnitsAndRecordsUnknownUnitsAtZero() {
		BigDecimal cost = pricing.costOf(List.of(
				UsageItem.units("LLAMAPARSE_PAGE", BigDecimal.valueOf(8)),
				UsageItem.units("SOMETHING_NEW", BigDecimal.ONE)));

		assertThat(cost).isEqualByComparingTo("0.03");
	}

	@Test
	void convertsCostToMillicreditsRoundingUpOnceAtAThousandthOfACredit() {
		// $0.0342 × 1.15 ÷ $0.002 = 19.665 credits
		assertThat(pricing.millicreditsFor(new BigDecimal("0.0342"))).isEqualTo(19_665);
		// A query embedding: $0.000008 → 0.0046 credits → 5 millicredits, not a whole credit.
		assertThat(pricing.millicreditsFor(new BigDecimal("0.000008"))).isEqualTo(5);
		assertThat(pricing.millicreditsFor(BigDecimal.ZERO)).isZero();
	}
}
