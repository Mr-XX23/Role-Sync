package com.rolesync.authservice.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminSignOutResponse {

    private AdminUserResponse user;

    /** Sessions that were still active and are now signed out. */
    @JsonProperty("revoked_sessions")
    private long revokedSessions;
}
