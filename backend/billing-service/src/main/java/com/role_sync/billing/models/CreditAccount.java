package com.role_sync.billing.models;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

import java.time.Instant;
import java.util.UUID;

/**
 * A workspace's credit balance. Members share it.
 *
 * <p>Amounts are millicredits (1 credit = 1,000) so a tiny operation is charged what it costs
 * instead of being rounded up to a whole credit. The balance is the running total of
 * {@link CreditTransaction}s and is only changed while this row is locked.
 */
@Entity
@Table(name = "credit_accounts", indexes = {
		@Index(name = "idx_credit_accounts_status", columnList = "status")
})
@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CreditAccount {

	@Id
	@Column(name = "workspace_id", nullable = false, updatable = false)
	private UUID workspaceId;

	@Column(name = "balance_millicredits", nullable = false)
	private long balanceMillicredits;

	@Enumerated(EnumType.STRING)
	@Column(name = "status", nullable = false, length = 16)
	private CreditAccountStatus status;

	@Column(name = "suspended_reason", length = 500)
	private String suspendedReason;

	@Column(name = "suspended_at")
	private Instant suspendedAt;

	@Column(name = "suspended_by")
	private UUID suspendedBy;

	/** Welcome grants, purchases and admin grants, less admin deductions and refund clawbacks. */
	@Column(name = "lifetime_credited_millicredits", nullable = false)
	private long lifetimeCreditedMillicredits;

	@Column(name = "lifetime_purchased_millicredits", nullable = false)
	private long lifetimePurchasedMillicredits;

	@Column(name = "lifetime_used_millicredits", nullable = false)
	private long lifetimeUsedMillicredits;

	@Column(name = "last_activity_at")
	private Instant lastActivityAt;

	@CreationTimestamp
	@Column(name = "created_at", nullable = false, updatable = false)
	private Instant createdAt;

	@UpdateTimestamp
	@Column(name = "updated_at")
	private Instant updatedAt;

	@Version
	@Column(name = "version")
	private Long version;

	public boolean isSuspended() {
		return status == CreditAccountStatus.SUSPENDED;
	}
}
