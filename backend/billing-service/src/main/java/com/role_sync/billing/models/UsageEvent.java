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

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/**
 * One metered operation as a service reported it: what it used, what that cost us and what the
 * workspace was charged. Kept for usage pages, margin analytics and billing disputes.
 */
@Entity
@Table(
		name = "usage_events",
		indexes = {
				@Index(name = "idx_usage_events_workspace_created", columnList = "workspace_id, created_at"),
				@Index(name = "idx_usage_events_created", columnList = "created_at")
		},
		uniqueConstraints = {
				@UniqueConstraint(name = "uk_usage_events_idempotency", columnNames = "idempotency_key")
		}
)
@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UsageEvent {

	@Id
	@GeneratedValue
	@Column(name = "id", nullable = false, updatable = false)
	private UUID id;

	@Column(name = "workspace_id", nullable = false)
	private UUID workspaceId;

	@Column(name = "user_id")
	private UUID userId;

	@Column(name = "operation", nullable = false, length = 96)
	private String operation;

	@Enumerated(EnumType.STRING)
	@Column(name = "category", nullable = false, length = 16)
	private UsageCategory category;

	/** Provider cost of the operation at the rates in force when it was charged. */
	@Column(name = "cost_usd", nullable = false, precision = 18, scale = 8)
	private BigDecimal costUsd;

	@Column(name = "millicredits", nullable = false)
	private long millicredits;

	/** First model in the report, for per-model analytics; items keeps the full detail. */
	@Column(name = "model", length = 128)
	private String model;

	@Column(name = "input_tokens", nullable = false)
	private long inputTokens;

	@Column(name = "cached_input_tokens", nullable = false)
	private long cachedInputTokens;

	@Column(name = "output_tokens", nullable = false)
	private long outputTokens;

	@Column(name = "items_json", columnDefinition = "TEXT")
	private String itemsJson;

	@Column(name = "metadata_json", columnDefinition = "TEXT")
	private String metadataJson;

	@Column(name = "reference", length = 255)
	private String reference;

	@Column(name = "idempotency_key", nullable = false, length = 255)
	private String idempotencyKey;

	@CreationTimestamp
	@Column(name = "created_at", nullable = false, updatable = false)
	private Instant createdAt;
}
