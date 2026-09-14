package com.role_sync.billing.services;

import com.role_sync.billing.models.CreditAccount;
import com.role_sync.billing.repository.CreditAccountRepository;
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Component;

import java.util.UUID;

/**
 * Takes the row lock every balance change needs, and hands back the account as it is committed.
 *
 * <p>Locking alone isn't enough: when the persistence context already holds the account (created
 * or read earlier in the same request), the locking query returns that older copy, and writing it
 * back would overwrite a concurrent charge or fail its version check. Refreshing under the lock
 * makes every write start from the committed balance.
 */
@Component
public class CreditAccountLocker {

	private final CreditAccountRepository accounts;
	private final EntityManager entityManager;

	public CreditAccountLocker(CreditAccountRepository accounts, EntityManager entityManager) {
		this.accounts = accounts;
		this.entityManager = entityManager;
	}

	/** Must run inside a transaction; the lock lasts until it ends. */
	public CreditAccount lock(UUID workspaceId) {
		CreditAccount account = accounts.findForUpdate(workspaceId)
				.orElseThrow(() -> new IllegalStateException("Credit account missing for " + workspaceId));
		entityManager.refresh(account);
		return account;
	}
}
