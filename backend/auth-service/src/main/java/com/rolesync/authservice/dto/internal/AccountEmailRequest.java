package com.rolesync.authservice.dto.internal;

import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/** Context for the emails a workspace admin's actions send: which workspace, who, which role. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AccountEmailRequest {

    @Size(max = 100, message = "Workspace name must be at most 100 characters")
    private String workspaceName;

    @Size(max = 150, message = "Inviter name must be at most 150 characters")
    private String invitedByName;

    @Size(max = 20, message = "Role name must be at most 20 characters")
    private String roleName;

    /** An admin is resending sign-in details, rather than adding the person for the first time. */
    private boolean resend;
}
