package com.rolesync.authservice.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.rolesync.authservice.models.AuthSecurityEvent;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/** A security event of one user, without its free-text event data. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminSecurityEvent {

    @JsonProperty("event_type")
    private String eventType;

    @JsonProperty("event_time")
    private String eventTime;

    @JsonProperty("ip_address")
    private String ipAddress;

    @JsonProperty("user_agent")
    private String userAgent;

    public static AdminSecurityEvent of(AuthSecurityEvent event) {
        return AdminSecurityEvent.builder()
                .eventType(event.getEventType())
                .eventTime(AdminTimestamps.utc(event.getEventTime()))
                .ipAddress(event.getIpAddress())
                .userAgent(event.getUserAgent())
                .build();
    }
}
