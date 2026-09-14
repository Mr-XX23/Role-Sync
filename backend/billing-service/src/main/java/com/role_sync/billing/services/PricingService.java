package com.role_sync.billing.services;

import com.role_sync.billing.configurations.BillingProperties;
import com.role_sync.billing.configurations.BillingProperties.MatchType;
import com.role_sync.billing.configurations.BillingProperties.ModelRate;
import com.role_sync.billing.configurations.BillingProperties.UnitRate;
import com.role_sync.billing.dto.UsageItem;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

/**
 * Turns reported usage into provider cost, and cost into millicredits.
 *
 * <p>{@code millicredits = ceil(cost × (1 + buffer) ÷ costPerCredit × 1000)}. Rounding up happens
 * once per charge at a thousandth of a credit, so a near-free operation costs a sliver of a credit
 * instead of a whole one, and the business never undercharges.
 */
@Service
public class PricingService {

	private static final Logger log = LoggerFactory.getLogger(PricingService.class);
	private static final BigDecimal MILLION = BigDecimal.valueOf(1_000_000);
	private static final int COST_SCALE = 8;

	private final BillingProperties properties;

	public PricingService(BillingProperties properties) {
		this.properties = properties;
	}

	public BigDecimal costOf(List<UsageItem> items) {
		BigDecimal total = BigDecimal.ZERO;
		for (UsageItem item : items) {
			total = total.add(switch (item.kind()) {
				case TOKENS -> tokenCost(item);
				case UNITS -> unitCost(item);
			});
		}
		return total.setScale(COST_SCALE, RoundingMode.HALF_UP);
	}

	public long millicreditsFor(BigDecimal costUsd) {
		if (costUsd == null || costUsd.signum() <= 0) {
			return 0;
		}
		BigDecimal costPerCredit = properties.getCredits().costPerCredit();
		BigDecimal credits = costUsd
				.multiply(BigDecimal.ONE.add(properties.getCredits().getBuffer()))
				.divide(costPerCredit, 12, RoundingMode.HALF_UP);
		return credits.movePointRight(3).setScale(0, RoundingMode.CEILING).longValueExact();
	}

	/** The rate a model is charged at: exact rules win, then prefix, suffix and contains rules. */
	public ModelRate rateFor(String model) {
		List<ModelRate> rules = properties.getRates().getModels();
		for (MatchType type : MatchType.values()) {
			for (ModelRate rule : rules) {
				if (rule.getMatch() == type && rule.matches(model)) {
					return rule;
				}
			}
		}
		return properties.getRates().getDefaultModel();
	}

	private BigDecimal tokenCost(UsageItem item) {
		ModelRate rate = rateFor(item.model());
		long input = Math.max(0, item.inputTokens());
		long cached = Math.min(Math.max(0, item.cachedInputTokens()), input);
		long output = Math.max(0, item.outputTokens());
		BigDecimal uncachedCost = BigDecimal.valueOf(input - cached).multiply(rate.getInputPerMillion());
		BigDecimal cachedCost = BigDecimal.valueOf(cached).multiply(rate.cachedRate());
		BigDecimal outputCost = BigDecimal.valueOf(output).multiply(rate.getOutputPerMillion());
		return uncachedCost.add(cachedCost).add(outputCost).divide(MILLION, COST_SCALE + 4, RoundingMode.HALF_UP);
	}

	private BigDecimal unitCost(UsageItem item) {
		String unit = item.unit() == null ? "" : item.unit().trim();
		for (UnitRate rate : properties.getRates().getUnits()) {
			if (rate.getUnit() != null && rate.getUnit().equalsIgnoreCase(unit)) {
				return item.quantity().max(BigDecimal.ZERO).multiply(rate.getUsd());
			}
		}
		// A unit billing has no price for yet is recorded at zero rather than dropped, so the
		// usage still shows up and the rate can be added to configuration.
		log.warn("No rate configured for unit '{}'; recorded at zero cost", unit);
		return BigDecimal.ZERO;
	}
}
