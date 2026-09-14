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
import org.hibernate.annotations.UpdateTimestamp;

import java.time.Instant;
import java.util.UUID;

/**
 * A single attempt to buy a credit package.
 *
 * <p>The credit and money amounts are SNAPSHOT here at checkout time from the
 * configured package, so a later price change never rewrites history, and the
 * client can never influence what it is charged.
 */
@Entity
@Table(
		name = "payment_orders",
		indexes = {
				@Index(name = "idx_payment_orders_account", columnList = "account_id"),
				@Index(name = "idx_payment_orders_status", columnList = "status"),
				@Index(name = "idx_payment_orders_provider_ref", columnList = "provider_ref")
		},
		uniqueConstraints = {
				@UniqueConstraint(name = "uk_payment_orders_idempotency", columnNames = "idempotency_key")
		}
)
@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PaymentOrder {

	@Id
	@GeneratedValue
	@Column(name = "id", nullable = false, updatable = false)
	private UUID id;

	/** Workspace the credits belong to. Credits are workspace-scoped. */
	@Column(name = "account_id", nullable = false)
	private UUID accountId;

	/** The user who started the purchase (audit only; credits go to the workspace). */
	@Column(name = "user_id", nullable = false)
	private UUID userId;

	@Column(name = "package_code", nullable = false, length = 64)
	private String packageCode;

	/** Credits to grant on success. Snapshot from config at checkout. */
	@Column(name = "credits", nullable = false)
	private long credits;

	/** Charge amount in the MINOR unit of the currency (cents, paisa). Never a float. */
	@Column(name = "amount_minor", nullable = false)
	private long amountMinor;

	@Column(name = "currency", nullable = false, length = 3)
	private String currency;

	@Enumerated(EnumType.STRING)
	@Column(name = "provider", nullable = false, length = 16)
	private PaymentProviderKey provider;

	@Enumerated(EnumType.STRING)
	@Column(name = "status", nullable = false, length = 16)
	private PaymentStatus status;

	/** Provider-side checkout id, e.g. a Stripe Checkout Session id. */
	@Column(name = "provider_ref", length = 255)
	private String providerRef;

	/** Provider-side payment id, e.g. a Stripe PaymentIntent id, known after success. */
	@Column(name = "provider_payment_ref", length = 255)
	private String providerPaymentRef;

	@Column(name = "checkout_url", length = 2048)
	private String checkoutUrl;

	/** Caller-supplied or derived key that makes checkout creation idempotent. */
	@Column(name = "idempotency_key", nullable = false, length = 255)
	private String idempotencyKey;

	@Column(name = "failure_reason", length = 512)
	private String failureReason;

	@Column(name = "paid_at")
	private Instant paidAt;

	@CreationTimestamp
	@Column(name = "created_at", nullable = false, updatable = false)
	private Instant createdAt;

	@UpdateTimestamp
	@Column(name = "updated_at")
	private Instant updatedAt;
}
