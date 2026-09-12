package com.role_sync.billing.dto;

import com.role_sync.billing.configurations.BillingProperties;

/** A purchasable credit package. */
public record CreditPackageResponse(
		String code,
		String name,
		long credits,
		long priceMinor,
		String currency
) {

	public static CreditPackageResponse from(BillingProperties.CreditPackage pkg) {
		return new CreditPackageResponse(
				pkg.getCode(),
				pkg.getName() == null ? pkg.getCode() : pkg.getName(),
				pkg.getCredits(),
				pkg.getPriceMinor(),
				pkg.getCurrency());
	}
}
