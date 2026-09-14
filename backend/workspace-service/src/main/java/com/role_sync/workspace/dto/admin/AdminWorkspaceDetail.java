package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminWorkspaceDetail {

    private AdminWorkspace workspace;

    /** Every membership, active or not, oldest first. */
    private List<AdminWorkspaceMember> members;

    private Counts counts;

    /** The last 20 member changes, newest first. */
    @JsonProperty("recent_member_events")
    private List<AdminMemberEvent> recentMemberEvents;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Counts {

        private long deals;

        /** Deals not WON or LOST. */
        @JsonProperty("open_deals")
        private long openDeals;

        private long contexts;

        private long notes;
    }
}
