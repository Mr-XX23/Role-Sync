package com.role_sync.billing.models;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.CreationTimestamp;

import java.time.Instant;
import java.util.UUID;

/**
 * Records that a user already received their sign-up credits. The user id is the primary key, so
 * a person can never be granted twice, however many workspaces they create.
 */
@Entity
@Table(name = "welcome_grants")
@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class WelcomeGrant {

	@Id
	@Column(name = "user_id", nullable = false, updatable = false)
	private UUID userId;

	@Column(name = "workspace_id", nullable = false)
	private UUID workspaceId;

	@Column(name = "millicredits", nullable = false)
	private long millicredits;

	@CreationTimestamp
	@Column(name = "created_at", nullable = false, updatable = false)
	private Instant createdAt;
}
