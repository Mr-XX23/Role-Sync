package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminWorkspaceStats {

    @JsonProperty("workspaces_total")
    private long workspacesTotal;

    @JsonProperty("workspaces_active")
    private long workspacesActive;

    @JsonProperty("workspaces_suspended")
    private long workspacesSuspended;

    @JsonProperty("profiles_total")
    private long profilesTotal;

    @JsonProperty("memberships_active")
    private long membershipsActive;

    /** One entry per UTC day of the range, oldest first, zero-filled. */
    @JsonProperty("new_workspaces_daily")
    private List<AdminDailyCount> newWorkspacesDaily;

    /** Every plan in display order, with the workspaces effectively on it. */
    @JsonProperty("plan_distribution")
    private List<PlanShare> planDistribution;

    @JsonProperty("deals_total")
    private long dealsTotal;

    /** Deals not WON or LOST. */
    @JsonProperty("deals_open")
    private long dealsOpen;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class PlanShare {

        @JsonProperty("plan_id")
        private UUID planId;

        private String code;

        private String name;

        @JsonProperty("workspace_count")
        private long workspaceCount;
    }
}
