package com.role_sync.workspace.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

/**
 * The plan a workspace is effectively on (its assigned plan, else the default plan). A null limit
 * means the plan sets none, so the platform defaults apply. Read by the sales agent engine.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class WorkspacePlanResponse {

    @JsonProperty("planId")
    private UUID planId;

    @JsonProperty("code")
    private String code;

    @JsonProperty("name")
    private String name;

    @JsonProperty("maxMembers")
    private Integer maxMembers;

    @JsonProperty("agentTokensPerDay")
    private Long agentTokensPerDay;

    @JsonProperty("maxConcurrentAgentRuns")
    private Integer maxConcurrentAgentRuns;
}
