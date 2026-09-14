package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

/** A plan as the admin console shows it. Null limits: the plan sets none (platform defaults apply). */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminPlan {

    @JsonProperty("plan_id")
    private UUID planId;

    private String code;

    private String name;

    private String description;

    @JsonProperty("price_monthly_cents")
    private Integer priceMonthlyCents;

    private String currency;

    @JsonProperty("max_members")
    private Integer maxMembers;

    @JsonProperty("agent_tokens_per_day")
    private Long agentTokensPerDay;

    @JsonProperty("max_concurrent_agent_runs")
    private Integer maxConcurrentAgentRuns;

    @JsonProperty("is_default")
    private boolean defaultPlan;

    @JsonProperty("is_archived")
    private boolean archived;

    @JsonProperty("sort_order")
    private int sortOrder;

    /** Workspaces effectively on the plan (for the default plan, including those with no plan assigned). */
    @JsonProperty("workspace_count")
    private long workspaceCount;

    @JsonProperty("created_at")
    private Instant createdAt;

    @JsonProperty("updated_at")
    private Instant updatedAt;
}
