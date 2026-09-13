package com.role_sync.workspace.dto;

import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class MemberStatusRequest {

    /** false deactivates the membership (no access to the workspace); true restores it. */
    @NotNull(message = "active cannot be null")
    private Boolean active;
}
