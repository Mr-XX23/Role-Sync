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
 * The money-to-credits seam.
 *
 * <p>A settled payment writes exactly one grant row, unique on {@code orderId}.
 * The credit ledger, built in the next slice, consumes PENDING grants and marks
 * them APPLIED. Keeping this separate is what decouples the money domain from the
 * credit domain: a payment never touches a balance directly.
 */
@Entity
@Table(
		name = "credit_grants",
		uniqueConstraints = {
				@UniqueConstraint(name = "uk_credit_grants_order", columnNames = "order_id")
		},
		indexes = {
				@Index(name = "idx_credit_grants_status", columnList = "status"),
				@Index(name = "idx_credit_grants_account", columnList = "account_id")
		}
)
@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CreditGrant {

	@Id
	@GeneratedValue
	@Column(name = "id", nullable = false, updatable = false)
	private UUID id;

	@Column(name = "order_id", nullable = false)
	private UUID orderId;

	@Column(name = "account_id", nullable = false)
	private UUID accountId;

	@Column(name = "user_id", nullable = false)
	private UUID userId;

	@Column(name = "credits", nullable = false)
	private long credits;

	@Enumerated(EnumType.STRING)
	@Column(name = "status", nullable = false, length = 16)
	private GrantStatus status;

	@Column(name = "applied_at")
	private Instant appliedAt;

	@CreationTimestamp
	@Column(name = "created_at", nullable = false, updatable = false)
	private Instant createdAt;
}
