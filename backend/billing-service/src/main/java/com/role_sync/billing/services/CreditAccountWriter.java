package com.role_sync.billing.services;

import com.role_sync.billing.configurations.BillingProperties;
import com.role_sync.billing.models.CreditAccount;
import com.role_sync.billing.models.CreditAccountStatus;
import com.role_sync.billing.models.CreditTransaction;
import com.role_sync.billing.models.CreditTransactionType;
import com.role_sync.billing.models.WelcomeGrant;
import com.role_sync.billing.repository.CreditAccountRepository;
import com.role_sync.billing.repository.CreditTransactionRepository;
import com.role_sync.billing.repository.WelcomeGrantRepository;
import com.role_sync.billing.utils.CreditMath;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.util.UUID;

/**
 * The two writes that can race on first contact — creating an account and granting a user's
 * welcome credits — each in its own transaction.
 *
 * <p>Two requests for a brand-new workspace or user can arrive together. The database's unique
 * keys decide the winner. The loser's constraint error is caught <em>outside</em> its transaction:
 * caught inside, the transaction would already be marked rollback-only and its commit would fail
 * with an unexpected-rollback error instead of quietly giving way. Running in a transaction of its
 * own also keeps the error from poisoning the caller's transaction.
 */
@Component
public class CreditAccountWriter {

	private static final Logger log = LoggerFactory.getLogger(CreditAccountWriter.class);

	private final CreditAccountRepository accounts;
	private final CreditTransactionRepository transactions;
	private final WelcomeGrantRepository welcomeGrants;
	private final CreditAccountLocker locker;
	private final BillingProperties properties;
	private final TransactionTemplate ownTransaction;

	public CreditAccountWriter(CreditAccountRepository accounts,
	                           CreditTransactionRepository transactions,
	                           WelcomeGrantRepository welcomeGrants,
	                           CreditAccountLocker locker,
	                           BillingProperties properties,
	                           PlatformTransactionManager transactionManager) {
		this.accounts = accounts;
		this.transactions = transactions;
		this.welcomeGrants = welcomeGrants;
		this.locker = locker;
		this.properties = properties;
		this.ownTransaction = new TransactionTemplate(transactionManager);
		this.ownTransaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
	}

	public void createIfMissing(UUID workspaceId) {
		if (accounts.existsById(workspaceId)) {
			return;
		}
		try {
			ownTransaction.executeWithoutResult(status -> accounts.saveAndFlush(CreditAccount.builder()
					.workspaceId(workspaceId)
					.status(CreditAccountStatus.ACTIVE)
					.build()));
		}
		catch (DataIntegrityViolationException raced) {
			log.debug("Credit account for {} was created concurrently", workspaceId);
		}
	}

	/**
	 * Gives a user's workspace the sign-up credits, once per user ever.
	 *
	 * @return true when this call granted them
	 */
	public boolean grantWelcomeIfDue(UUID workspaceId, UUID userId) {
		long grant = properties.getCredits().getSignupGrant();
		if (userId == null || grant <= 0 || welcomeGrants.existsById(userId)) {
			return false;
		}
		try {
			ownTransaction.executeWithoutResult(status -> grantWelcome(workspaceId, userId, grant));
			log.info("Granted {} welcome credits to workspace {} for user {}", grant, workspaceId, userId);
			return true;
		}
		catch (DataIntegrityViolationException raced) {
			// Another request granted this user first; the unique user id kept it to one grant.
			return false;
		}
	}

	private void grantWelcome(UUID workspaceId, UUID userId, long grant) {
		long millicredits = CreditMath.wholeCreditsToMillicredits(grant);
		welcomeGrants.saveAndFlush(WelcomeGrant.builder()
				.userId(userId)
				.workspaceId(workspaceId)
				.millicredits(millicredits)
				.build());

		CreditAccount account = locker.lock(workspaceId);
		account.setBalanceMillicredits(account.getBalanceMillicredits() + millicredits);
		account.setLifetimeCreditedMillicredits(account.getLifetimeCreditedMillicredits() + millicredits);
		account.setLastActivityAt(Instant.now());
		accounts.save(account);

		transactions.save(CreditTransaction.builder()
				.workspaceId(workspaceId)
				.type(CreditTransactionType.WELCOME_GRANT)
				.amountMillicredits(millicredits)
				.balanceAfterMillicredits(account.getBalanceMillicredits())
				.reason("Welcome credits")
				.actorUserId(userId)
				.idempotencyKey("welcome:" + userId)
				.build());
	}
}
