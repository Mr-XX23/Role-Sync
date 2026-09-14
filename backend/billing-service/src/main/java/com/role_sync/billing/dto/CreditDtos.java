package com.role_sync.billing.dto;

import com.role_sync.billing.models.CreditAccountStatus;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Request and response bodies for the user, public and internal credit endpoints. */
public final class CreditDtos {

	private CreditDtos() {
	}

	public record CreditBalanceResponse(
			UUID workspaceId,
			BigDecimal balance,
			CreditAccountStatus status,
			boolean lowBalance,
			long lowBalanceThreshold,
			BigDecimal lifetimeCredited,
			BigDecimal lifetimeUsed
	) {
	}

	public record CategoryUsage(String category, String label, BigDecimal credits, BigDecimal percent) {
	}

	public record UsageSummaryResponse(
			UUID workspaceId,
			int periodDays,
			Instant from,
			Instant to,
			BigDecimal balance,
			BigDecimal lifetimeCredited,
			BigDecimal lifetimeUsed,
			BigDecimal usedPercent,
			BigDecimal periodUsed,
			List<CategoryUsage> categories
	) {
	}

	public record PricingExample(String label, long credits) {
	}

	public record PublicPricingResponse(
			String currency,
			long signupCredits,
			BigDecimal creditPriceUsd,
			List<CreditPackageResponse> packages,
			List<PricingExample> examples
	) {
	}

	public record CheckResponse(boolean allowed, String code, BigDecimal balance, CreditAccountStatus status) {
	}

	public record UsageItemRequest(
			String type,
			String model,
			Long inputTokens,
			Long cachedInputTokens,
			Long outputTokens,
			String unit,
			BigDecimal quantity
	) {
	}

	public record UsageRequest(
			UUID workspaceId,
			UUID userId,
			String operation,
			String category,
			String idempotencyKey,
			String reference,
			List<UsageItemRequest> items,
			Map<String, Object> metadata
	) {
	}

	public record UsageResponse(BigDecimal creditsCharged, BigDecimal costUsd, BigDecimal balance,
	                            CreditAccountStatus status, boolean duplicate) {
	}
}
