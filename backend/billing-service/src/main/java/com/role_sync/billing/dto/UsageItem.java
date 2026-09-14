package com.role_sync.billing.dto;

import java.math.BigDecimal;

/**
 * One line of reported usage: tokens used on a model, or a count of a priced unit.
 *
 * @param kind              TOKENS or UNITS
 * @param model             model id, for TOKENS
 * @param inputTokens       total prompt tokens, cached ones included
 * @param cachedInputTokens the part of the prompt served from cache
 * @param outputTokens      output tokens, thinking included
 * @param unit              unit name, for UNITS (e.g. LLAMAPARSE_PAGE)
 * @param quantity          how many units
 */
public record UsageItem(
		Kind kind,
		String model,
		long inputTokens,
		long cachedInputTokens,
		long outputTokens,
		String unit,
		BigDecimal quantity
) {

	public enum Kind {
		TOKENS,
		UNITS
	}

	public static UsageItem tokens(String model, long input, long cached, long output) {
		return new UsageItem(Kind.TOKENS, model, input, cached, output, null, BigDecimal.ZERO);
	}

	public static UsageItem units(String unit, BigDecimal quantity) {
		return new UsageItem(Kind.UNITS, null, 0, 0, 0, unit, quantity);
	}
}
