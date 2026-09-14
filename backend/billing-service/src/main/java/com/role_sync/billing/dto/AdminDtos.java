package com.role_sync.billing.dto;

import com.role_sync.billing.models.CreditAccount;
import com.role_sync.billing.models.CreditAccountStatus;
import com.role_sync.billing.models.CreditTransaction;
import com.role_sync.billing.utils.CreditMath;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

/** Request and response bodies for the super admin billing endpoints. */
public final class AdminDtos {

	private AdminDtos() {
	}

	public record AccountResponse(
			UUID workspaceId,
			BigDecimal balance,
			CreditAccountStatus status,
			BigDecimal lifetimeCredited,
			BigDecimal lifetimeUsed,
			BigDecimal lifetimePurchased,
			String suspendedReason,
			Instant suspendedAt,
			Instant lastActivityAt,
			Instant createdAt
	) {
		public static AccountResponse from(CreditAccount account) {
			return new AccountResponse(
					account.getWorkspaceId(),
					CreditMath.toCredits(account.getBalanceMillicredits()),
					account.getStatus(),
					CreditMath.toCredits(account.getLifetimeCreditedMillicredits()),
					CreditMath.toCredits(account.getLifetimeUsedMillicredits()),
					CreditMath.toCredits(account.getLifetimePurchasedMillicredits()),
					account.getSuspendedReason(),
					account.getSuspendedAt(),
					account.getLastActivityAt(),
					account.getCreatedAt());
		}
	}

	public record TransactionResponse(
			UUID id,
			String type,
			BigDecimal credits,
			BigDecimal balanceAfter,
			String operation,
			String category,
			String reason,
			UUID actorUserId,
			String reference,
			Instant createdAt
	) {
		public static TransactionResponse from(CreditTransaction t) {
			return new TransactionResponse(
					t.getId(),
					t.getType().name(),
					CreditMath.toCredits(t.getAmountMillicredits()),
					CreditMath.toCredits(t.getBalanceAfterMillicredits()),
					t.getOperation(),
					t.getCategory() == null ? null : t.getCategory().name(),
					t.getReason(),
					t.getActorUserId(),
					t.getReference(),
					t.getCreatedAt());
		}
	}

	public record CategoryCost(String category, String label, BigDecimal credits, BigDecimal costUsd, BigDecimal percent) {
	}

	public record AccountDetailResponse(AccountResponse account, List<TransactionResponse> transactions,
	                                    List<CategoryCost> usageByCategory) {
	}

	public record AdjustRequest(BigDecimal credits, String reason, Boolean allowNegative) {
	}

	public record StatusRequest(String reason) {
	}

	public record PageResponse<T>(List<T> items, int page, int size, long total) {
	}

	public record RevenueLine(String currency, long amountMinor, long payments) {
	}

	public record DailyUsage(LocalDate date, BigDecimal credits, BigDecimal costUsd) {
	}

	public record WorkspaceUsage(UUID workspaceId, BigDecimal credits, BigDecimal costUsd) {
	}

	public record OverviewResponse(
			int periodDays,
			Instant from,
			List<RevenueLine> revenue,
			BigDecimal revenueUsd,
			long successfulPayments,
			BigDecimal creditsSold,
			BigDecimal creditsGranted,
			BigDecimal creditsUsed,
			BigDecimal providerCostUsd,
			BigDecimal grossMarginPercent,
			BigDecimal outstandingCredits,
			long accounts,
			long suspendedAccounts,
			long negativeBalanceAccounts,
			List<CategoryCost> usageByCategory,
			List<DailyUsage> dailyUsage,
			List<WorkspaceUsage> topWorkspaces
	) {
	}

	public record OperationUsage(String operation, String category, long count, BigDecimal credits, BigDecimal costUsd) {
	}

	public record ModelUsage(String model, long calls, long inputTokens, long cachedInputTokens, long outputTokens,
	                         BigDecimal credits, BigDecimal costUsd) {
	}

	public record UsageBreakdownResponse(int periodDays, UUID workspaceId, List<CategoryCost> byCategory,
	                                     List<OperationUsage> byOperation, List<ModelUsage> byModel) {
	}
}
