package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

/** A workspace as the admin console lists it. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminWorkspace {

    @JsonProperty("workspace_id")
    private UUID workspaceId;

    private String name;

    private String description;

    /** false: suspended. */
    @JsonProperty("is_active")
    private boolean active;

    @JsonProperty("created_at")
    private Instant createdAt;

    @JsonProperty("updated_at")
    private Instant updatedAt;

    /** Null when the owner's profile is unknown. */
    private Owner owner;

    /** Active memberships. */
    @JsonProperty("member_count")
    private long memberCount;

    /** The plan the workspace is effectively on. */
    private AdminPlanRef plan;

    /** false: no plan assigned, so the workspace follows the default plan. */
    @JsonProperty("plan_assigned")
    private boolean planAssigned;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Owner {

        @JsonProperty("profile_id")
        private UUID profileId;

        @JsonProperty("auth_user_id")
        private UUID authUserId;

        private String name;

        /** Null when the account service couldn't be asked. */
        private String email;
    }
}
