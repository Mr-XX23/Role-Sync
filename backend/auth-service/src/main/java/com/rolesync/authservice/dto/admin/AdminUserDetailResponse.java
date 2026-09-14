package com.rolesync.authservice.dto.admin;

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
public class AdminUserDetailResponse {

    private AdminUserResponse user;

    /** Distinct sessions that still have an unrevoked, unexpired token. */
    @JsonProperty("active_sessions")
    private long activeSessions;

    /** The user's latest security events, newest first. */
    @JsonProperty("recent_events")
    private List<AdminSecurityEvent> recentEvents;
}
