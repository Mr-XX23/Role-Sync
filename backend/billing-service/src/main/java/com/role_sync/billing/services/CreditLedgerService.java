package com.role_sync.billing.services;

import com.google.gson.Gson;
import com.role_sync.billing.configurations.BillingProperties;
import com.role_sync.billing.dto.UsageItem;
import com.role_sync.billing.models.CreditAccount;
import com.role_sync.billing.models.CreditAccountStatus;
import com.role_sync.billing.models.CreditTransaction;
import com.role_sync.billing.models.CreditTransactionType;
import com.role_sync.billing.models.UsageCategory;
import com.role_sync.billing.models.UsageEvent;
import com.role_sync.billing.repository.CreditAccountRepository;
import com.role_sync.billing.repository.CreditTransactionRepository;
import com.role_sync.billing.repository.UsageEventRepository;
import com.role_sync.billing.utils.CreditMath;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * The only code that changes a credit balance.
 *
 * <p>Every change locks the workspace's account row, writes one ledger line and updates the
 * balance in the same transaction. Retries are safe everywhere: charges, purchases and refunds
 * each carry a unique idempotency key that is checked again after the lock is taken.
 */
@Service
public class CreditLedgerService {

	private static final Logger log = LoggerFactory.getLogger(CreditLedgerService.class);
	private static final Gson GSON = new Gson();
	private static final int MAX_ITEMS = 50;
	private static final long MAX_TOKENS_PER_ITEM = 20_000_000L;
	private static final BigDecimal MAX_UNITS_PER_ITEM = BigDecimal.valueOf(1_000_000);

	public record CheckResult(boolean allowed, String code, long balanceMillicredits, CreditAccountStatus status) {
	}

	public record UsageCommand(
			UUID workspaceId,
			UUID userId,
			String operation,
			UsageCategory category,
			String idempotencyKey,
			String reference,
			List<UsageItem> items,
			Map<String, Object> metadata
	) {
	}

	public record UsageResult(long millicreditsCharged, BigDecimal costUsd, long balanceMillicredits,
	                          CreditAccountStatus status, boolean duplicate) {
	}

	private final CreditAccountRepository accounts;
	private final CreditTransactionRepository transactions;
	private final UsageEventRepository usageEvents;
	private final CreditAccountWriter writer;
	private final PricingService pricing;
	private final BillingProperties properties;

	public CreditLedgerService(CreditAccountRepository accounts,
	                           CreditTransactionRepository transactions,
	                           UsageEventRepository usageEvents,
	                           CreditAccountWriter writer,
	                           PricingService pricing,
	                           BillingProperties properties) {
		this.accounts = accounts;
		this.transactions = transactions;
		this.usageEvents = usageEvents;
		this.writer = writer;
		this.pricing = pricing;
		this.properties = properties;
	}

	/** The workspace's account, created on first contact, with the user's welcome credits if due. */
	public CreditAccount ensureAccount(UUID workspaceId, UUID userId) {
		writer.createIfMissing(workspaceId);
		writer.grantWelcomeIfDue(workspaceId, userId);
		return accounts.findById(workspaceId)
				.orElseThrow(() -> new IllegalStateException("Credit account missing for " + workspaceId));
	}

	/** Whether a new paid operation may start. Never blocks work that already ran. */
	public CheckResult check(UUID workspaceId, UUID userId) {
		CreditAccount account = ensureAccount(workspaceId, userId);
		if (account.isSuspended()) {
			return new CheckResult(false, BillingException.CREDITS_SUSPENDED, account.getBalanceMillicredits(), account.getStatus());
		}
		if (account.getBalanceMillicredits() <= 0) {
			return new CheckResult(false, BillingException.OUT_OF_CREDITS, account.getBalanceMillicredits(), account.getStatus());
		}
		return new CheckResult(true, "OK", account.getBalanceMillicredits(), account.getStatus());
	}

	/**
	 * Charges an operation that already happened. The balance may go below zero: the work is done
	 * and the provider has already billed us, so refusing to record it would only lose the charge.
	 * The next check blocks further spending until credits are added.
	 */
	@Transactional
	public UsageResult recordUsage(UsageCommand command) {
		validate(command);
		if (usageEvents.existsByIdempotencyKey(command.idempotencyKey())) {
			return duplicateResult(command.workspaceId());
		}

		// First-contact writes commit in their own transactions before this one takes its lock.
		writer.createIfMissing(command.workspaceId());
		writer.grantWelcomeIfDue(command.workspaceId(), command.userId());

		CreditAccount account = lock(command.workspaceId());
		if (usageEvents.existsByIdempotencyKey(command.idempotencyKey())) {
			return new UsageResult(0, BigDecimal.ZERO, account.getBalanceMillicredits(), account.getStatus(), true);
		}

		BigDecimal cost = pricing.costOf(command.items());
		long millicredits = pricing.millicreditsFor(cost);

		long input = 0;
		long cached = 0;
		long output = 0;
		String model = null;
		for (UsageItem item : command.items()) {
			if (item.kind() == UsageItem.Kind.TOKENS) {
				input += item.inputTokens();
				cached += item.cachedInputTokens();
				output += item.outputTokens();
				if (model == null) {
					model = item.model();
				}
			}
		}

		usageEvents.save(UsageEvent.builder()
				.workspaceId(command.workspaceId())
				.userId(command.userId())
				.operation(command.operation())
				.category(command.category())
				.costUsd(cost)
				.millicredits(millicredits)
				.model(truncate(model, 128))
				.inputTokens(input)
				.cachedInputTokens(cached)
				.outputTokens(output)
				.itemsJson(GSON.toJson(command.items()))
				.metadataJson(command.metadata() == null || command.metadata().isEmpty() ? null : truncate(GSON.toJson(command.metadata()), 4_000))
				.reference(truncate(command.reference(), 255))
				.idempotencyKey(command.idempotencyKey())
				.build());

		Instant now = Instant.now();
		if (millicredits > 0) {
			account.setBalanceMillicredits(account.getBalanceMillicredits() - millicredits);
			account.setLifetimeUsedMillicredits(account.getLifetimeUsedMillicredits() + millicredits);
			transactions.save(CreditTransaction.builder()
					.workspaceId(command.workspaceId())
					.type(CreditTransactionType.USAGE)
					.amountMillicredits(-millicredits)
					.balanceAfterMillicredits(account.getBalanceMillicredits())
					.operation(truncate(command.operation(), 96))
					.category(command.category())
					.actorUserId(command.userId())
					.reference(truncate(command.reference(), 255))
					.idempotencyKey("usage:" + command.idempotencyKey())
					.build());
		}
		account.setLastActivityAt(now);
		accounts.save(account);

		if (account.getBalanceMillicredits() < 0 && account.getBalanceMillicredits() + millicredits >= 0) {
			log.info("Workspace {} ran out of credits on {}", command.workspaceId(), command.operation());
		}
		return new UsageResult(millicredits, cost, account.getBalanceMillicredits(), account.getStatus(), false);
	}

	/** Adds purchased credits for a paid order, once. */
	@Transactional
	public boolean creditPurchase(UUID workspaceId, long credits, UUID buyerUserId, UUID orderId) {
		String key = "purchase:" + orderId;
		if (transactions.existsByIdempotencyKey(key)) {
			return false;
		}
		writer.createIfMissing(workspaceId);
		CreditAccount account = lock(workspaceId);
		if (transactions.existsByIdempotencyKey(key)) {
			return false;
		}
		long millicredits = CreditMath.wholeCreditsToMillicredits(credits);
		account.setBalanceMillicredits(account.getBalanceMillicredits() + millicredits);
		account.setLifetimeCreditedMillicredits(account.getLifetimeCreditedMillicredits() + millicredits);
		account.setLifetimePurchasedMillicredits(account.getLifetimePurchasedMillicredits() + millicredits);
		account.setLastActivityAt(Instant.now());
		accounts.save(account);
		transactions.save(CreditTransaction.builder()
				.workspaceId(workspaceId)
				.type(CreditTransactionType.PURCHASE)
				.amountMillicredits(millicredits)
				.balanceAfterMillicredits(account.getBalanceMillicredits())
				.reason("Purchased " + credits + " credits")
				.actorUserId(buyerUserId)
				.reference(orderId.toString())
				.idempotencyKey(key)
				.build());
		return true;
	}

	/**
	 * Takes back the credits of a refunded order, once. May leave a negative balance: credits already
	 * spent were consumed against a payment that no longer exists.
	 */
	@Transactional
	public boolean clawBackPurchase(UUID workspaceId, long credits, UUID orderId) {
		String key = "refund:" + orderId;
		if (transactions.existsByIdempotencyKey(key)) {
			return false;
		}
		writer.createIfMissing(workspaceId);
		CreditAccount account = lock(workspaceId);
		if (transactions.existsByIdempotencyKey(key)) {
			return false;
		}
		long millicredits = CreditMath.wholeCreditsToMillicredits(credits);
		account.setBalanceMillicredits(account.getBalanceMillicredits() - millicredits);
		account.setLifetimeCreditedMillicredits(Math.max(0, account.getLifetimeCreditedMillicredits() - millicredits));
		account.setLifetimePurchasedMillicredits(Math.max(0, account.getLifetimePurchasedMillicredits() - millicredits));
		account.setLastActivityAt(Instant.now());
		accounts.save(account);
		transactions.save(CreditTransaction.builder()
				.workspaceId(workspaceId)
				.type(CreditTransactionType.REFUND_CLAWBACK)
				.amountMillicredits(-millicredits)
				.balanceAfterMillicredits(account.getBalanceMillicredits())
				.reason("Payment refunded")
				.reference(orderId.toString())
				.idempotencyKey(key)
				.build());
		return true;
	}

	@Transactional
	public CreditAccount adminGrant(UUID workspaceId, BigDecimal credits, String reason, UUID adminUserId) {
		long millicredits = validAdjustment(credits);
		String cleanReason = requireReason(reason);
		writer.createIfMissing(workspaceId);
		CreditAccount account = lock(workspaceId);
		account.setBalanceMillicredits(account.getBalanceMillicredits() + millicredits);
		account.setLifetimeCreditedMillicredits(account.getLifetimeCreditedMillicredits() + millicredits);
		account.setLastActivityAt(Instant.now());
		accounts.save(account);
		transactions.save(CreditTransaction.builder()
				.workspaceId(workspaceId)
				.type(CreditTransactionType.ADMIN_GRANT)
				.amountMillicredits(millicredits)
				.balanceAfterMillicredits(account.getBalanceMillicredits())
				.reason(cleanReason)
				.actorUserId(adminUserId)
				.build());
		log.info("Admin {} granted {} credits to workspace {}: {}", adminUserId, credits, workspaceId, cleanReason);
		return account;
	}

	@Transactional
	public CreditAccount adminDeduct(UUID workspaceId, BigDecimal credits, String reason, UUID adminUserId, boolean allowNegative) {
		long millicredits = validAdjustment(credits);
		String cleanReason = requireReason(reason);
		writer.createIfMissing(workspaceId);
		CreditAccount account = lock(workspaceId);
		if (!allowNegative && account.getBalanceMillicredits() < millicredits) {
			throw new BillingException(HttpStatus.CONFLICT, BillingException.INSUFFICIENT_BALANCE,
					"The workspace only has " + CreditMath.toCredits(Math.max(0, account.getBalanceMillicredits()))
							+ " credits. Deduct less, or allow a negative balance.");
		}
		account.setBalanceMillicredits(account.getBalanceMillicredits() - millicredits);
		account.setLifetimeCreditedMillicredits(Math.max(0, account.getLifetimeCreditedMillicredits() - millicredits));
		account.setLastActivityAt(Instant.now());
		accounts.save(account);
		transactions.save(CreditTransaction.builder()
				.workspaceId(workspaceId)
				.type(CreditTransactionType.ADMIN_DEDUCT)
				.amountMillicredits(-millicredits)
				.balanceAfterMillicredits(account.getBalanceMillicredits())
				.reason(cleanReason)
				.actorUserId(adminUserId)
				.build());
		log.info("Admin {} deducted {} credits from workspace {}: {}", adminUserId, credits, workspaceId, cleanReason);
		return account;
	}

	@Transactional
	public CreditAccount suspend(UUID workspaceId, String reason, UUID adminUserId) {
		String cleanReason = requireReason(reason);
		writer.createIfMissing(workspaceId);
		CreditAccount account = lock(workspaceId);
		if (account.isSuspended()) {
			return account;
		}
		account.setStatus(CreditAccountStatus.SUSPENDED);
		account.setSuspendedReason(cleanReason);
		account.setSuspendedAt(Instant.now());
		account.setSuspendedBy(adminUserId);
		accounts.save(account);
		recordStatusChange(account, CreditTransactionType.ACCOUNT_SUSPENDED, cleanReason, adminUserId);
		log.warn("Admin {} suspended credits for workspace {}: {}", adminUserId, workspaceId, cleanReason);
		return account;
	}

	@Transactional
	public CreditAccount reactivate(UUID workspaceId, String reason, UUID adminUserId) {
		String cleanReason = requireReason(reason);
		writer.createIfMissing(workspaceId);
		CreditAccount account = lock(workspaceId);
		if (!account.isSuspended()) {
			return account;
		}
		account.setStatus(CreditAccountStatus.ACTIVE);
		account.setSuspendedReason(null);
		account.setSuspendedAt(null);
		account.setSuspendedBy(null);
		accounts.save(account);
		recordStatusChange(account, CreditTransactionType.ACCOUNT_REACTIVATED, cleanReason, adminUserId);
		log.info("Admin {} reactivated credits for workspace {}: {}", adminUserId, workspaceId, cleanReason);
		return account;
	}

	private void recordStatusChange(CreditAccount account, CreditTransactionType type, String reason, UUID adminUserId) {
		transactions.save(CreditTransaction.builder()
				.workspaceId(account.getWorkspaceId())
				.type(type)
				.amountMillicredits(0)
				.balanceAfterMillicredits(account.getBalanceMillicredits())
				.reason(reason)
				.actorUserId(adminUserId)
				.build());
	}

	private CreditAccount lock(UUID workspaceId) {
		return accounts.findForUpdate(workspaceId)
				.orElseThrow(() -> new IllegalStateException("Credit account missing for " + workspaceId));
	}

	private UsageResult duplicateResult(UUID workspaceId) {
		CreditAccount account = accounts.findById(workspaceId).orElse(null);
		long balance = account == null ? 0 : account.getBalanceMillicredits();
		CreditAccountStatus status = account == null ? CreditAccountStatus.ACTIVE : account.getStatus();
		return new UsageResult(0, BigDecimal.ZERO, balance, status, true);
	}

	private long validAdjustment(BigDecimal credits) {
		if (credits == null || credits.signum() <= 0) {
			throw new BillingException(HttpStatus.BAD_REQUEST, BillingException.INVALID_AMOUNT, "Enter an amount greater than zero.");
		}
		if (credits.scale() > 3 && credits.stripTrailingZeros().scale() > 3) {
			throw new BillingException(HttpStatus.BAD_REQUEST, BillingException.INVALID_AMOUNT, "Use at most three decimal places.");
		}
		if (credits.compareTo(BigDecimal.valueOf(properties.getCredits().getMaxAdminAdjustment())) > 0) {
			throw new BillingException(HttpStatus.BAD_REQUEST, BillingException.INVALID_AMOUNT,
					"A single change can be at most " + properties.getCredits().getMaxAdminAdjustment() + " credits.");
		}
		return CreditMath.toMillicredits(credits);
	}

	private static String requireReason(String reason) {
		if (reason == null || reason.isBlank()) {
			throw new BillingException(HttpStatus.BAD_REQUEST, "REASON_REQUIRED", "Give a reason; it is kept in the audit log.");
		}
		return truncate(reason.trim(), 500);
	}

	private static void validate(UsageCommand command) {
		if (command.workspaceId() == null) {
			throw new IllegalArgumentException("workspaceId is required");
		}
		if (command.idempotencyKey() == null || command.idempotencyKey().isBlank() || command.idempotencyKey().length() > 200) {
			throw new IllegalArgumentException("idempotencyKey is required and must be at most 200 characters");
		}
		if (command.operation() == null || command.operation().isBlank()) {
			throw new IllegalArgumentException("operation is required");
		}
		if (command.items() == null || command.items().isEmpty() || command.items().size() > MAX_ITEMS) {
			throw new IllegalArgumentException("items must contain between 1 and " + MAX_ITEMS + " entries");
		}
		for (UsageItem item : command.items()) {
			if (item.kind() == null) {
				throw new IllegalArgumentException("every item needs a type of TOKENS or UNITS");
			}
			if (item.kind() == UsageItem.Kind.TOKENS) {
				if (item.inputTokens() < 0 || item.outputTokens() < 0 || item.cachedInputTokens() < 0
						|| item.inputTokens() > MAX_TOKENS_PER_ITEM || item.outputTokens() > MAX_TOKENS_PER_ITEM) {
					throw new IllegalArgumentException("token counts must be between 0 and " + MAX_TOKENS_PER_ITEM);
				}
			}
			else if (item.quantity() == null || item.quantity().signum() < 0 || item.quantity().compareTo(MAX_UNITS_PER_ITEM) > 0
					|| item.unit() == null || item.unit().isBlank()) {
				throw new IllegalArgumentException("unit items need a unit and a quantity between 0 and " + MAX_UNITS_PER_ITEM);
			}
		}
	}

	private static String truncate(String value, int max) {
		if (value == null) {
			return null;
		}
		return value.length() <= max ? value : value.substring(0, max);
	}
}
