package com.role_sync.billing.services;

import com.role_sync.billing.configurations.BillingProperties;
import com.role_sync.billing.configurations.BillingProperties.MatchType;
import com.role_sync.billing.configurations.BillingProperties.ModelRate;
import com.role_sync.billing.configurations.BillingProperties.UnitRate;

import java.math.BigDecimal;
import java.util.List;

/** The production rate card and credit rules, built in code for tests. */
final class TestBillingProperties {

	private TestBillingProperties() {
	}

	static BillingProperties create() {
		BillingProperties properties = new BillingProperties();
		properties.getRates().setModels(List.of(
				model("gemini-3.5-flash", MatchType.EXACT, "1.50", "9.00", "0.15"),
				model("gemini-3.5-flash-lite", MatchType.EXACT, "0.30", "2.50", "0.03"),
				model(":free", MatchType.SUFFIX, "0.10", "0.40", "0.01"),
				model("nvidia/", MatchType.PREFIX, "0.10", "0.40", "0.01")));
		properties.getRates().setUnits(List.of(unit("LLAMAPARSE_PAGE", "0.00375"), unit("TAVILY_SEARCH", "0.008")));
		return properties;
	}

	private static ModelRate model(String pattern, MatchType match, String in, String out, String cached) {
		ModelRate rate = new ModelRate();
		rate.setPattern(pattern);
		rate.setMatch(match);
		rate.setInputPerMillion(new BigDecimal(in));
		rate.setOutputPerMillion(new BigDecimal(out));
		rate.setCachedInputPerMillion(new BigDecimal(cached));
		return rate;
	}

	private static UnitRate unit(String unit, String usd) {
		UnitRate rate = new UnitRate();
		rate.setUnit(unit);
		rate.setUsd(new BigDecimal(usd));
		return rate;
	}
}
