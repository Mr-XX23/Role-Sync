package com.role_sync.billing.models;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.CreationTimestamp;

import java.time.Instant;
import java.util.UUID;

/**
 * One append-only line of a workspace's credit ledger.
 *
 * <p>{@code idempotencyKey} is unique, which is what stops a retried purchase, grant or charge
 * from changing the balance twice.
 */
@Entity
@Table(
		name = "credit_transactions",
		indexes = {
				@Index(name = "idx_credit_transactions_workspace_created", columnList = "workspace_id, created_at"),
				@Index(name = "idx_credit_transactions_type_created", columnList = "type, created_at")
		},
		uniqueConstraints = {
				@UniqueConstraint(name = "uk_credit_transactions_idempotency", columnNames = "idempotency_key")
		}
)
@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CreditTransaction {

	@Id
	@GeneratedValue
	@Column(name = "id", nullable = false, updatable = false)
	private UUID id;

	@Column(name = "workspace_id", nullable = false)
	private UUID workspaceId;

	@Enumerated(EnumType.STRING)
	@Column(name = "type", nullable = false, length = 24)
	private CreditTransactionType type;

	/** Signed: positive adds credits, negative removes them. */
	@Column(name = "amount_millicredits", nullable = false)
	private long amountMillicredits;

	@Column(name = "balance_after_millicredits", nullable = false)
	private long balanceAfterMillicredits;

	@Column(name = "operation", length = 96)
	private String operation;

	@Enumerated(EnumType.STRING)
	@Column(name = "category", length = 16)
	private UsageCategory category;

	@Column(name = "reason", length = 500)
	private String reason;

	/** The super admin or buyer behind the change, when there was one. */
	@Column(name = "actor_user_id")
	private UUID actorUserId;

	@Column(name = "reference", length = 255)
	private String reference;

	@Column(name = "idempotency_key", length = 255)
	private String idempotencyKey;

	@CreationTimestamp
	@Column(name = "created_at", nullable = false, updatable = false)
	private Instant createdAt;
}
