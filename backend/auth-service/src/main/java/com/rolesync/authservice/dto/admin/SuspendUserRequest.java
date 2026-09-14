package com.rolesync.authservice.dto.admin;

import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class SuspendUserRequest {

    /** Optional; recorded in the audit trail and the user's security events. */
    @Size(max = 500, message = "The reason must be at most 500 characters.")
    private String reason;
}
