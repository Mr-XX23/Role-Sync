package com.role_sync.workspace.models;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.ColumnDefault;

import java.time.LocalDateTime;
import java.util.UUID;

/**
 * A plan (entitlements) the RoleSync team puts workspaces on. A null limit means the plan sets no
 * limit of its own, so the platform defaults apply. A workspace without a plan is on the default
 * plan; there is always exactly one (see {@code PlanRules}).
 */
@Entity
@Table(name = "platform_plans", uniqueConstraints = {
        @UniqueConstraint(name = "uk_platform_plans_code", columnNames = "code")
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PlatformPlan {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "plan_id")
    private UUID planId;

    /** STANDARD, FREE, PRO...: capital letters, digits and underscores. */
    @Column(name = "code", length = 40, nullable = false)
    private String code;

    @Column(name = "name", length = 60, nullable = false)
    private String name;

    @Column(name = "description", length = 300)
    private String description;

    @Column(name = "price_monthly_cents")
    private Integer priceMonthlyCents;

    @Column(name = "currency", length = 3, nullable = false)
    @ColumnDefault("'USD'")
    @Builder.Default
    private String currency = "USD";

    /** Active memberships a workspace on this plan may have. */
    @Column(name = "max_members")
    private Integer maxMembers;

    /** Read by the sales agent engine: the workspace's daily token budget. */
    @Column(name = "agent_tokens_per_day")
    private Long agentTokensPerDay;

    /** Read by the sales agent engine: agent runs a workspace may have at once. */
    @Column(name = "max_concurrent_agent_runs")
    private Integer maxConcurrentAgentRuns;

    @Column(name = "is_default", nullable = false)
    @ColumnDefault("false")
    @Builder.Default
    private Boolean isDefault = false;

    /** Archived plans can't be newly assigned; workspaces already on one keep it. */
    @Column(name = "is_archived", nullable = false)
    @ColumnDefault("false")
    @Builder.Default
    private Boolean isArchived = false;

    @Column(name = "sort_order", nullable = false)
    @ColumnDefault("0")
    @Builder.Default
    private Integer sortOrder = 0;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }
}
