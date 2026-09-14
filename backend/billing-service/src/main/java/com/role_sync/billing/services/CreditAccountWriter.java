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
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

/**
 * The two writes that can race on first contact — creating an account and granting a user's
 * welcome credits — each in its own transaction.
 *
 * <p>Two requests for a brand-new workspace or user can arrive together. The database's unique
 * keys decide the winner; the loser's constraint error is caught here, in a transaction of its
 * own, so it can't poison the caller's transaction.
 */
@Component
public class CreditAccountWriter {

	private static final Logger log = LoggerFactory.getLogger(CreditAccountWriter.class);

	private final CreditAccountRepository accounts;
	private final CreditTransactionRepository transactions;
	private final WelcomeGrantRepository welcomeGrants;
	private final BillingProperties properties;

	public CreditAccountWriter(CreditAccountRepository accounts,
	                           CreditTransactionRepository transactions,
	                           WelcomeGrantRepository welcomeGrants,
	                           BillingProperties properties) {
		this.accounts = accounts;
		this.transactions = transactions;
		this.welcomeGrants = welcomeGrants;
		this.properties = properties;
	}

	@Transactional(propagation = Propagation.REQUIRES_NEW)
	public void createIfMissing(UUID workspaceId) {
		if (accounts.existsById(workspaceId)) {
			return;
		}
		try {
			accounts.saveAndFlush(CreditAccount.builder()
					.workspaceId(workspaceId)
					.status(CreditAccountStatus.ACTIVE)
					.build());
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
	@Transactional(propagation = Propagation.REQUIRES_NEW)
	public boolean grantWelcomeIfDue(UUID workspaceId, UUID userId) {
		long grant = properties.getCredits().getSignupGrant();
		if (userId == null || grant <= 0 || welcomeGrants.existsById(userId)) {
			return false;
		}
		try {
			long millicredits = CreditMath.wholeCreditsToMillicredits(grant);
			welcomeGrants.saveAndFlush(WelcomeGrant.builder()
					.userId(userId)
					.workspaceId(workspaceId)
					.millicredits(millicredits)
					.build());

			CreditAccount account = accounts.findForUpdate(workspaceId)
					.orElseThrow(() -> new IllegalStateException("Credit account missing for " + workspaceId));
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
			log.info("Granted {} welcome credits to workspace {} for user {}", grant, workspaceId, userId);
			return true;
		}
		catch (DataIntegrityViolationException raced) {
			// Another request granted this user first; the unique user id kept it to one grant.
			return false;
		}
	}
}
