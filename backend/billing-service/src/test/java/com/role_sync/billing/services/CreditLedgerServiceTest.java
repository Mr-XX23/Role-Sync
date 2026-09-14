package com.role_sync.billing.services;

import com.role_sync.billing.configurations.BillingProperties;
import com.role_sync.billing.dto.CreditDtos.CategoryUsage;
import com.role_sync.billing.dto.CreditDtos.UsageSummaryResponse;
import com.role_sync.billing.dto.UsageItem;
import com.role_sync.billing.models.CreditAccount;
import com.role_sync.billing.models.CreditTransactionType;
import com.role_sync.billing.models.UsageCategory;
import com.role_sync.billing.repository.CreditAccountRepository;
import com.role_sync.billing.repository.CreditTransactionRepository;
import com.role_sync.billing.repository.PaymentOrderRepository;
import com.role_sync.billing.repository.UsageEventRepository;
import com.role_sync.billing.repository.WelcomeGrantRepository;
import com.role_sync.billing.security.WorkspaceMembershipGuard;
import com.role_sync.billing.services.CreditLedgerService.CheckResult;
import com.role_sync.billing.services.CreditLedgerService.UsageCommand;
import com.role_sync.billing.services.CreditLedgerService.UsageResult;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.orm.jpa.EntityManagerHolder;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.doReturn;

/**
 * The ledger against a real database, with the same transactions production uses (the test's own
 * transaction is switched off so the ledger's locking and REQUIRES_NEW writes behave for real).
 */
@DataJpaTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
@Import({CreditLedgerService.class, CreditAccountWriter.class, CreditAccountLocker.class, PricingService.class,
		UsageReportService.class, CreditLedgerServiceTest.Config.class})
class CreditLedgerServiceTest {

	@TestConfiguration
	static class Config {
		/** Workspaces the test users were only invited to; every other workspace is their own. */
		static final Set<UUID> NOT_OWNED = ConcurrentHashMap.newKeySet();

		@Bean
		BillingProperties billingProperties() {
			return TestBillingProperties.create();
		}

		@Bean
		WorkspaceMembershipGuard workspaceMembershipGuard() {
			return new WorkspaceMembershipGuard(null) {
				@Override
				public boolean isOwner(UUID userId, UUID workspaceId) {
					return !NOT_OWNED.contains(workspaceId);
				}
			};
		}
	}

	@Autowired
	private CreditLedgerService ledger;
	@Autowired
	private UsageReportService reports;
	@Autowired
	private CreditAccountRepository accounts;
	@Autowired
	private CreditTransactionRepository transactions;
	@Autowired
	private UsageEventRepository usageEvents;
	@Autowired
	private WelcomeGrantRepository welcomeGrants;
	@Autowired
	private PaymentOrderRepository orders;
	@Autowired
	private CreditAccountWriter writer;
	@Autowired
	private EntityManagerFactory entityManagerFactory;
	@MockitoSpyBean
	private CreditAccountRepository accountsSpy;
	@MockitoSpyBean
	private WelcomeGrantRepository welcomeGrantsSpy;

	@BeforeEach
	void clean() {
		usageEvents.deleteAll();
		transactions.deleteAll();
		welcomeGrants.deleteAll();
		accounts.deleteAll();
		orders.deleteAll();
	}

	private static UsageCommand agentTurn(UUID workspace, UUID user, String key) {
		// $0.0342 → 19.665 credits
		return new UsageCommand(workspace, user, "agent.model_call", UsageCategory.AGENT, key, "session-1",
				List.of(UsageItem.tokens("gemini-3.5-flash", 18_000, 0, 800)), Map.of("purpose", "plan"));
	}

	@Test
	void givesEachUserTheirWelcomeCreditsExactlyOnce() {
		UUID user = UUID.randomUUID();
		UUID first = UUID.randomUUID();
		UUID second = UUID.randomUUID();

		assertThat(ledger.ensureAccount(first, user).getBalanceMillicredits()).isEqualTo(500_000);
		assertThat(ledger.ensureAccount(first, user).getBalanceMillicredits()).isEqualTo(500_000);
		// A second workspace for the same person gets nothing: no farming by creating workspaces.
		assertThat(ledger.ensureAccount(second, user).getBalanceMillicredits()).isZero();
		assertThat(welcomeGrants.count()).isEqualTo(1);
	}

	@Test
	void aRequestThatLosesTheFirstContactRaceGivesWayQuietly() {
		UUID workspace = UUID.randomUUID();
		UUID user = UUID.randomUUID();
		ledger.ensureAccount(workspace, user); // the winner: account created, 500 granted

		// The loser checked before the winner committed, so it believes both rows are still missing.
		doReturn(false).when(accountsSpy).existsById(workspace);
		doReturn(false).when(welcomeGrantsSpy).existsById(user);

		writer.createIfMissing(workspace);
		assertThat(writer.grantWelcomeIfDue(workspace, user)).isFalse();
		assertThat(accounts.findById(workspace).orElseThrow().getBalanceMillicredits()).isEqualTo(500_000);
		assertThat(welcomeGrants.count()).isEqualTo(1);
	}

	@Test
	void aStaleAccountHeldByTheRequestNeverOverwritesAConcurrentCharge() {
		UUID workspace = UUID.randomUUID();
		UUID user = UUID.randomUUID();
		// One persistence context for the whole "request", as open-in-view does.
		EntityManager requestContext = entityManagerFactory.createEntityManager();
		TransactionSynchronizationManager.bindResource(entityManagerFactory, new EntityManagerHolder(requestContext));
		try {
			writer.createIfMissing(workspace); // leaves the new account managed in the request's context

			// Meanwhile another request charges the workspace.
			CompletableFuture.runAsync(() -> ledger.recordUsage(agentTurn(workspace, null, "concurrent"))).join();

			assertThat(writer.grantWelcomeIfDue(workspace, user)).isTrue();
		}
		finally {
			TransactionSynchronizationManager.unbindResource(entityManagerFactory);
			requestContext.close();
		}
		assertThat(accounts.findById(workspace).orElseThrow().getBalanceMillicredits()).isEqualTo(500_000 - 19_665);
	}

	@Test
	void landsWelcomeCreditsOnlyInAWorkspaceTheUserOwns() {
		UUID user = UUID.randomUUID();
		UUID invitedTo = UUID.randomUUID();
		UUID own = UUID.randomUUID();
		Config.NOT_OWNED.add(invitedTo);

		// Opening a workspace they were invited to first adds nothing there...
		assertThat(ledger.ensureAccount(invitedTo, user).getBalanceMillicredits()).isZero();
		assertThat(ledger.check(invitedTo, user).code()).isEqualTo(BillingException.OUT_OF_CREDITS);
		// ...and their own workspace still gets the full grant afterwards.
		assertThat(ledger.ensureAccount(own, user).getBalanceMillicredits()).isEqualTo(500_000);
	}

	@Test
	void refusesNewWorkWhenTheBalanceIsEmptyAndAllowsItAfterAGrant() {
		UUID workspace = UUID.randomUUID();

		CheckResult empty = ledger.check(workspace, null);
		assertThat(empty.allowed()).isFalse();
		assertThat(empty.code()).isEqualTo(BillingException.OUT_OF_CREDITS);

		ledger.adminGrant(workspace, BigDecimal.TEN, "goodwill", UUID.randomUUID());
		assertThat(ledger.check(workspace, null).allowed()).isTrue();
	}

	@Test
	void chargesUsageOnceAndLetsWorkAlreadyDoneTakeTheBalanceBelowZero() {
		UUID workspace = UUID.randomUUID();
		ledger.adminGrant(workspace, BigDecimal.ONE, "tiny balance", UUID.randomUUID());

		UsageResult charged = ledger.recordUsage(agentTurn(workspace, null, "turn-1"));
		UsageResult replayed = ledger.recordUsage(agentTurn(workspace, null, "turn-1"));

		assertThat(charged.duplicate()).isFalse();
		assertThat(charged.millicreditsCharged()).isEqualTo(19_665);
		assertThat(charged.balanceMillicredits()).isEqualTo(1_000 - 19_665);
		assertThat(replayed.duplicate()).isTrue();
		assertThat(accounts.findById(workspace).orElseThrow().getBalanceMillicredits()).isEqualTo(1_000 - 19_665);
		assertThat(usageEvents.count()).isEqualTo(1);
		assertThat(ledger.check(workspace, null).code()).isEqualTo(BillingException.OUT_OF_CREDITS);
	}

	@Test
	void suspensionBlocksSpendingUntilReactivated() {
		UUID workspace = UUID.randomUUID();
		UUID admin = UUID.randomUUID();
		ledger.adminGrant(workspace, BigDecimal.valueOf(100), "trial", admin);

		ledger.suspend(workspace, "chargeback investigation", admin);
		assertThat(ledger.check(workspace, null).code()).isEqualTo(BillingException.CREDITS_SUSPENDED);

		assertThatThrownBy(() -> ledger.requireCanPurchase(workspace, null))
				.isInstanceOf(BillingException.class)
				.satisfies(ex -> assertThat(((BillingException) ex).code()).isEqualTo(BillingException.CREDITS_SUSPENDED));

		ledger.reactivate(workspace, "resolved", admin);
		assertThat(ledger.check(workspace, null).allowed()).isTrue();
		ledger.requireCanPurchase(workspace, null);
		assertThat(transactions.findAll()).extracting(t -> t.getType())
				.contains(CreditTransactionType.ACCOUNT_SUSPENDED, CreditTransactionType.ACCOUNT_REACTIVATED);
	}

	@Test
	void adminDeductRefusesAnOverdraftUnlessExplicitlyAllowed() {
		UUID workspace = UUID.randomUUID();
		UUID admin = UUID.randomUUID();
		ledger.adminGrant(workspace, BigDecimal.TEN, "start", admin);

		assertThatThrownBy(() -> ledger.adminDeduct(workspace, BigDecimal.valueOf(20), "too much", admin, false))
				.isInstanceOf(BillingException.class)
				.satisfies(ex -> assertThat(((BillingException) ex).status()).isEqualTo(HttpStatus.CONFLICT));

		CreditAccount account = ledger.adminDeduct(workspace, BigDecimal.valueOf(20), "reverse a mistaken grant", admin, true);
		assertThat(account.getBalanceMillicredits()).isEqualTo(-10_000);
	}

	@Test
	void adminChangesNeedAPositiveAmountAndAReason() {
		UUID workspace = UUID.randomUUID();

		assertThatThrownBy(() -> ledger.adminGrant(workspace, BigDecimal.ZERO, "nothing", UUID.randomUUID()))
				.isInstanceOf(BillingException.class);
		assertThatThrownBy(() -> ledger.adminGrant(workspace, BigDecimal.TEN, "  ", UUID.randomUUID()))
				.isInstanceOf(BillingException.class);
		assertThatThrownBy(() -> ledger.adminGrant(workspace, BigDecimal.valueOf(2_000_000), "huge", UUID.randomUUID()))
				.isInstanceOf(BillingException.class);
	}

	@Test
	void addsPurchasedCreditsOnceAndTakesThemBackOnceOnRefund() {
		UUID workspace = UUID.randomUUID();
		UUID order = UUID.randomUUID();

		assertThat(ledger.creditPurchase(workspace, 1_000, UUID.randomUUID(), order)).isTrue();
		assertThat(ledger.creditPurchase(workspace, 1_000, UUID.randomUUID(), order)).isFalse();
		assertThat(accounts.findById(workspace).orElseThrow().getBalanceMillicredits()).isEqualTo(1_000_000);

		assertThat(ledger.clawBackPurchase(workspace, 1_000, order)).isTrue();
		assertThat(ledger.clawBackPurchase(workspace, 1_000, order)).isFalse();
		CreditAccount account = accounts.findById(workspace).orElseThrow();
		assertThat(account.getBalanceMillicredits()).isZero();
		assertThat(account.getLifetimePurchasedMillicredits()).isZero();
	}

	@Test
	void summarisesUsageAsPercentages() {
		UUID workspace = UUID.randomUUID();
		UUID user = UUID.randomUUID();
		ledger.ensureAccount(workspace, user); // 500 welcome credits

		ledger.recordUsage(agentTurn(workspace, user, "a"));
		ledger.recordUsage(new UsageCommand(workspace, user, "document.ingest", UsageCategory.DOCUMENTS, "d", "doc-1",
				List.of(UsageItem.units("LLAMAPARSE_PAGE", BigDecimal.valueOf(8))), Map.of()));

		UsageSummaryResponse summary = reports.summary(accounts.findById(workspace).orElseThrow(), 30);

		assertThat(summary.categories()).hasSize(UsageCategory.values().length);
		CategoryUsage agent = summary.categories().stream().filter(c -> c.category().equals("AGENT")).findFirst().orElseThrow();
		CategoryUsage documents = summary.categories().stream().filter(c -> c.category().equals("DOCUMENTS")).findFirst().orElseThrow();
		// 19.665 agent + 17.25 documents credits
		assertThat(agent.credits()).isEqualByComparingTo("19.665");
		assertThat(documents.credits()).isEqualByComparingTo("17.250");
		assertThat(agent.percent().add(documents.percent())).isEqualByComparingTo("100.0");
		// 36.915 used of 500 credited
		assertThat(summary.usedPercent()).isEqualByComparingTo("7.4");
	}
}
