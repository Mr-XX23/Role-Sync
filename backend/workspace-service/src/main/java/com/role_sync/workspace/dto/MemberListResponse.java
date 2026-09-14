package com.role_sync.workspace.dto;

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
public class MemberListResponse {

    @JsonProperty("workspace_id")
    private UUID workspaceId;

    @JsonProperty("workspace_name")
    private String workspaceName;

    @JsonProperty("your_role")
    private String yourRole;

    /** Roles the caller may give people they add. */
    @JsonProperty("assignable_roles")
    private List<String> assignableRoles;

    /** false when sign-in details (email, last sign-in, invitation) couldn't be loaded. */
    @JsonProperty("account_details_available")
    private boolean accountDetailsAvailable;

    private List<MemberResponse> members;
}
