package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/** A plan's details as the admin console sends them to create or replace a plan. Checked by {@code PlanRules}. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PlanInput {

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

    @JsonProperty("sort_order")
    private Integer sortOrder;
}
