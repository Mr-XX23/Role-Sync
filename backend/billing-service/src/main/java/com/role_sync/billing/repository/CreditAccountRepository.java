package com.role_sync.billing.repository;

import com.role_sync.billing.models.CreditAccount;
import com.role_sync.billing.models.CreditAccountStatus;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;
import java.util.UUID;

public interface CreditAccountRepository extends JpaRepository<CreditAccount, UUID> {

	/** Every balance change goes through this lock, so concurrent charges can't lose an update. */
	@Lock(LockModeType.PESSIMISTIC_WRITE)
	@Query("select a from CreditAccount a where a.workspaceId = :workspaceId")
	Optional<CreditAccount> findForUpdate(@Param("workspaceId") UUID workspaceId);

	@Query("""
			select a from CreditAccount a
			where (:status is null or a.status = :status)
			  and (:query = '' or lower(cast(a.workspaceId as string)) like concat('%', :query, '%'))
			order by a.lastActivityAt desc nulls last, a.createdAt desc
			""")
	Page<CreditAccount> search(@Param("query") String query, @Param("status") CreditAccountStatus status, Pageable pageable);

	long countByStatus(CreditAccountStatus status);

	long countByBalanceMillicreditsLessThan(long balance);

	@Query("select coalesce(sum(a.balanceMillicredits), 0) from CreditAccount a where a.balanceMillicredits > 0")
	long sumPositiveBalances();
}
