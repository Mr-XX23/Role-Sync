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
 * An inbound provider webhook, recorded for replay-safety and audit.
 *
 * <p>{@code providerEventId} is unique per provider: gateways retry webhooks, so
 * that unique constraint is what stops a retry from granting credits twice.
 *
 * <p>Only the event id, type and outcome are stored. Raw payloads are not
 * persisted, because they can carry customer contact details.
 */
@Entity
@Table(
		name = "payment_events",
		uniqueConstraints = {
				@UniqueConstraint(
						name = "uk_payment_events_provider_event",
						columnNames = {"provider", "provider_event_id"})
		},
		indexes = {
				@Index(name = "idx_payment_events_order", columnList = "order_id")
		}
)
@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PaymentEvent {

	@Id
	@GeneratedValue
	@Column(name = "id", nullable = false, updatable = false)
	private UUID id;

	@Enumerated(EnumType.STRING)
	@Column(name = "provider", nullable = false, length = 16)
	private PaymentProviderKey provider;

	@Column(name = "provider_event_id", nullable = false, length = 255)
	private String providerEventId;

	@Column(name = "event_type", nullable = false, length = 128)
	private String eventType;

	@Column(name = "order_id")
	private UUID orderId;

	@Column(name = "signature_verified", nullable = false)
	private boolean signatureVerified;

	/** Short outcome note, e.g. "granted 1000 credits" or "ignored: not a payment event". */
	@Column(name = "outcome", length = 512)
	private String outcome;

	@CreationTimestamp
	@Column(name = "received_at", nullable = false, updatable = false)
	private Instant receivedAt;
}
