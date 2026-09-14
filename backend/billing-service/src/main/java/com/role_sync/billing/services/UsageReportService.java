package com.role_sync.billing.services;

import com.role_sync.billing.dto.AdminDtos.AccountDetailResponse;
import com.role_sync.billing.dto.AdminDtos.AccountResponse;
import com.role_sync.billing.dto.AdminDtos.CategoryCost;
import com.role_sync.billing.dto.AdminDtos.DailyUsage;
import com.role_sync.billing.dto.AdminDtos.ModelUsage;
import com.role_sync.billing.dto.AdminDtos.OperationUsage;
import com.role_sync.billing.dto.AdminDtos.OverviewResponse;
import com.role_sync.billing.dto.AdminDtos.RevenueLine;
import com.role_sync.billing.dto.AdminDtos.TransactionResponse;
import com.role_sync.billing.dto.AdminDtos.UsageBreakdownResponse;
import com.role_sync.billing.dto.AdminDtos.WorkspaceUsage;
import com.role_sync.billing.dto.CreditDtos.CategoryUsage;
import com.role_sync.billing.dto.CreditDtos.UsageSummaryResponse;
import com.role_sync.billing.models.CreditAccount;
import com.role_sync.billing.models.CreditAccountStatus;
import com.role_sync.billing.models.CreditTransactionType;
import com.role_sync.billing.models.UsageCategory;
import com.role_sync.billing.repository.CreditAccountRepository;
import com.role_sync.billing.repository.CreditTransactionRepository;
import com.role_sync.billing.repository.PaymentOrderRepository;
import com.role_sync.billing.repository.UsageEventRepository;
import com.role_sync.billing.utils.CreditMath;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.UUID;

/** Read-only usage and revenue reporting for the usage page and the Super Admin Console. */
@Service
@Transactional(readOnly = true)
public class UsageReportService {

	public static final int MAX_PERIOD_DAYS = 365;

	private final UsageEventRepository usageEvents;
	private final CreditAccountRepository accounts;
	private final CreditTransactionRepository transactions;
	private final PaymentOrderRepository orders;

	public UsageReportService(UsageEventRepository usageEvents,
	                          CreditAccountRepository accounts,
	                          CreditTransactionRepository transactions,
	                          PaymentOrderRepository orders) {
		this.usageEvents = usageEvents;
		this.accounts = accounts;
		this.transactions = transactions;
		this.orders = orders;
	}

	public static int clampDays(Integer days) {
		if (days == null || days <= 0) {
			return 30;
		}
		return Math.min(days, MAX_PERIOD_DAYS);
	}

	/** Percent of credits used, and how the period's usage splits across categories. */
	public UsageSummaryResponse summary(CreditAccount account, int days) {
		Instant now = Instant.now();
		Instant from = now.minus(Duration.ofDays(days));
		Map<UsageCategory, long[]> byCategory = categoryTotals(usageEvents.sumByCategoryForWorkspace(account.getWorkspaceId(), from));

		long periodUsed = byCategory.values().stream().mapToLong(v -> v[0]).sum();
		List<CategoryUsage> categories = new ArrayList<>();
		for (UsageCategory category : UsageCategory.values()) {
			long used = byCategory.getOrDefault(category, new long[]{0})[0];
			categories.add(new CategoryUsage(category.name(), category.label(), CreditMath.toCredits(used),
					CreditMath.percent(used, periodUsed)));
		}

		return new UsageSummaryResponse(
				account.getWorkspaceId(),
				days,
				from,
				now,
				CreditMath.toCredits(account.getBalanceMillicredits()),
				CreditMath.toCredits(account.getLifetimeCreditedMillicredits()),
				CreditMath.toCredits(account.getLifetimeUsedMillicredits()),
				CreditMath.percent(account.getLifetimeUsedMillicredits(), account.getLifetimeCreditedMillicredits()),
				CreditMath.toCredits(periodUsed),
				categories);
	}

	public OverviewResponse overview(int days) {
		Instant from = Instant.now().minus(Duration.ofDays(days));

		List<RevenueLine> revenue = new ArrayList<>();
		BigDecimal revenueUsd = BigDecimal.ZERO;
		long payments = 0;
		for (Object[] row : orders.revenueSince(from)) {
			String currency = (String) row[0];
			long amountMinor = ((Number) row[1]).longValue();
			long count = ((Number) row[2]).longValue();
			revenue.add(new RevenueLine(currency, amountMinor, count));
			payments += count;
			if ("usd".equalsIgnoreCase(currency)) {
				revenueUsd = revenueUsd.add(BigDecimal.valueOf(amountMinor, 2));
			}
		}

		long sold = transactions.sumByTypesSince(List.of(CreditTransactionType.PURCHASE), from);
		long granted = transactions.sumByTypesSince(List.of(CreditTransactionType.WELCOME_GRANT, CreditTransactionType.ADMIN_GRANT), from);
		long used = -transactions.sumByTypesSince(List.of(CreditTransactionType.USAGE), from);
		BigDecimal cost = usageEvents.sumCostSince(from).setScale(4, RoundingMode.HALF_UP);
		BigDecimal margin = revenueUsd.signum() > 0
				? revenueUsd.subtract(cost).multiply(BigDecimal.valueOf(100)).divide(revenueUsd, 1, RoundingMode.HALF_UP)
				: null;

		return new OverviewResponse(
				days,
				from,
				revenue,
				revenueUsd,
				payments,
				CreditMath.toCredits(sold),
				CreditMath.toCredits(granted),
				CreditMath.toCredits(used),
				cost,
				margin,
				CreditMath.toCredits(accounts.sumPositiveBalances()),
				accounts.count(),
				accounts.countByStatus(CreditAccountStatus.SUSPENDED),
				accounts.countByBalanceMillicreditsLessThan(0),
				categoryCosts(usageEvents.sumByCategory(from, null)),
				daily(from, days),
				topWorkspaces(from));
	}

	public UsageBreakdownResponse breakdown(int days, UUID workspaceId) {
		Instant from = Instant.now().minus(Duration.ofDays(days));
		List<OperationUsage> byOperation = new ArrayList<>();
		for (Object[] row : usageEvents.sumByOperation(from, workspaceId)) {
			byOperation.add(new OperationUsage((String) row[0], String.valueOf(row[1]), ((Number) row[2]).longValue(),
					CreditMath.toCredits(((Number) row[3]).longValue()), money(row[4])));
		}
		List<ModelUsage> byModel = new ArrayList<>();
		for (Object[] row : usageEvents.sumByModel(from, workspaceId)) {
			byModel.add(new ModelUsage((String) row[0], ((Number) row[1]).longValue(), ((Number) row[2]).longValue(),
					((Number) row[3]).longValue(), ((Number) row[4]).longValue(),
					CreditMath.toCredits(((Number) row[5]).longValue()), money(row[6])));
		}
		return new UsageBreakdownResponse(days, workspaceId, categoryCosts(usageEvents.sumByCategory(from, workspaceId)),
				byOperation, byModel);
	}

	public AccountDetailResponse accountDetail(CreditAccount account, int transactionsLimit) {
		List<TransactionResponse> recent = transactions
				.findByWorkspaceIdOrderByCreatedAtDesc(account.getWorkspaceId(), PageRequest.of(0, transactionsLimit))
				.stream()
				.map(TransactionResponse::from)
				.toList();
		Instant from = Instant.now().minus(Duration.ofDays(30));
		return new AccountDetailResponse(AccountResponse.from(account), recent,
				categoryCosts(usageEvents.sumByCategory(from, account.getWorkspaceId())));
	}

	private List<DailyUsage> daily(Instant from, int days) {
		Map<LocalDate, BigDecimal[]> byDay = new TreeMap<>();
		LocalDate first = LocalDate.ofInstant(from, ZoneOffset.UTC);
		LocalDate today = LocalDate.now(ZoneOffset.UTC);
		for (LocalDate d = first; !d.isAfter(today); d = d.plusDays(1)) {
			byDay.put(d, new BigDecimal[]{BigDecimal.ZERO, BigDecimal.ZERO});
		}
		for (Object[] row : usageEvents.pointsSince(from)) {
			LocalDate day = LocalDate.ofInstant((Instant) row[0], ZoneOffset.UTC);
			BigDecimal[] totals = byDay.computeIfAbsent(day, d -> new BigDecimal[]{BigDecimal.ZERO, BigDecimal.ZERO});
			totals[0] = totals[0].add(CreditMath.toCredits(((Number) row[1]).longValue()));
			totals[1] = totals[1].add(money(row[2]));
		}
		List<DailyUsage> series = new ArrayList<>();
		byDay.forEach((day, totals) -> series.add(new DailyUsage(day, totals[0], totals[1].setScale(4, RoundingMode.HALF_UP))));
		return series.size() > days + 1 ? series.subList(series.size() - days - 1, series.size()) : series;
	}

	private List<WorkspaceUsage> topWorkspaces(Instant from) {
		List<WorkspaceUsage> top = new ArrayList<>();
		for (Object[] row : usageEvents.topWorkspaces(from, PageRequest.of(0, 10))) {
			top.add(new WorkspaceUsage((UUID) row[0], CreditMath.toCredits(((Number) row[1]).longValue()), money(row[2])));
		}
		return top;
	}

	private static Map<UsageCategory, long[]> categoryTotals(List<Object[]> rows) {
		Map<UsageCategory, long[]> totals = new EnumMap<>(UsageCategory.class);
		for (Object[] row : rows) {
			totals.put((UsageCategory) row[0], new long[]{((Number) row[1]).longValue()});
		}
		return totals;
	}

	private static List<CategoryCost> categoryCosts(List<Object[]> rows) {
		Map<UsageCategory, Object[]> byCategory = new EnumMap<>(UsageCategory.class);
		long total = 0;
		for (Object[] row : rows) {
			byCategory.put((UsageCategory) row[0], row);
			total += ((Number) row[1]).longValue();
		}
		List<CategoryCost> result = new ArrayList<>();
		for (UsageCategory category : UsageCategory.values()) {
			Object[] row = byCategory.get(category);
			long millicredits = row == null ? 0 : ((Number) row[1]).longValue();
			BigDecimal cost = row == null ? BigDecimal.ZERO : money(row[2]);
			result.add(new CategoryCost(category.name(), category.label(), CreditMath.toCredits(millicredits),
					cost.setScale(4, RoundingMode.HALF_UP), CreditMath.percent(millicredits, total)));
		}
		return result;
	}

	private static BigDecimal money(Object value) {
		if (value instanceof BigDecimal decimal) {
			return decimal;
		}
		return value == null ? BigDecimal.ZERO : new BigDecimal(value.toString());
	}
}
