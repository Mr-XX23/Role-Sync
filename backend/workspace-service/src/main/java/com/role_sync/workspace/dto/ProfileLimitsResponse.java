package com.role_sync.workspace.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/** How many profile saves and profile photo changes the caller has left (see ProfileChangeLimits). */
public record ProfileLimitsResponse(
        @JsonProperty("profile_saves") Allowance profileSaves,
        @JsonProperty("photo_changes") Allowance photoChanges) {

    /**
     * {@code resets_at}: when the full allowance is back, as an ISO-8601 instant; null while none of it
     * is used. A window opens with the first change and lasts {@code window_hours}.
     */
    public record Allowance(
            int limit,
            int used,
            int remaining,
            @JsonProperty("window_hours") long windowHours,
            @JsonProperty("resets_at") String resetsAt) {
    }
}
