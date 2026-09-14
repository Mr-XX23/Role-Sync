package com.role_sync.billing.utils;

import java.math.BigDecimal;
import java.math.RoundingMode;

/** Converts between the ledger's millicredits and the credits people see. */
public final class CreditMath {

	public static final long MILLI = 1_000L;

	private CreditMath() {
	}

	/** Millicredits as credits with three decimals, e.g. 487235 → 487.235. */
	public static BigDecimal toCredits(long millicredits) {
		return BigDecimal.valueOf(millicredits, 3);
	}

	/** Credits as millicredits; anything below a thousandth of a credit rounds half up. */
	public static long toMillicredits(BigDecimal credits) {
		return credits.setScale(3, RoundingMode.HALF_UP).movePointRight(3).longValueExact();
	}

	public static long wholeCreditsToMillicredits(long credits) {
		return Math.multiplyExact(credits, MILLI);
	}

	/** Share of {@code part} in {@code whole} as a percentage with one decimal, capped at 0..100. */
	public static BigDecimal percent(long part, long whole) {
		if (whole <= 0) {
			return part > 0 ? BigDecimal.valueOf(100) : BigDecimal.ZERO.setScale(1);
		}
		BigDecimal value = BigDecimal.valueOf(Math.max(part, 0))
				.multiply(BigDecimal.valueOf(100))
				.divide(BigDecimal.valueOf(whole), 1, RoundingMode.HALF_UP);
		return value.min(BigDecimal.valueOf(100).setScale(1));
	}
}
