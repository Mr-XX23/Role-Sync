package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminWorkspaceMember {

    @JsonProperty("membership_id")
    private UUID membershipId;

    @JsonProperty("profile_id")
    private UUID profileId;

    @JsonProperty("auth_user_id")
    private UUID authUserId;

    private String name;

    /** Null when the account service couldn't be asked. */
    private String email;

    /** OWNER, ADMIN, MEMBER or VIEWER. */
    private String role;

    private boolean active;

    @JsonProperty("joined_at")
    private Instant joinedAt;
}
