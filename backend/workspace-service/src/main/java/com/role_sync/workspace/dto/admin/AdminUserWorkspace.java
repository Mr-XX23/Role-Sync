package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

/** A workspace one user belongs to (or owns), for the admin console's user page. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminUserWorkspace {

    @JsonProperty("workspace_id")
    private UUID workspaceId;

    private String name;

    /** false: the workspace is suspended. */
    @JsonProperty("is_active")
    private boolean active;

    private String role;

    /** false: the user was deactivated in this workspace. */
    @JsonProperty("membership_active")
    private boolean membershipActive;

    @JsonProperty("is_owner")
    private boolean owner;

    @JsonProperty("joined_at")
    private Instant joinedAt;
}
