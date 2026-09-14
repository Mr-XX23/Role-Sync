package com.rolesync.authservice.dto.admin;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;

/** Timestamps as the Super Admin Console API writes them: ISO-8601 in UTC, e.g. "2026-09-14T05:05:36Z". */
public final class AdminTimestamps {

    private AdminTimestamps() {
    }

    /** Stored times are the JVM's local time ({@code LocalDateTime.now()}), so they are read in the system zone. */
    public static String utc(LocalDateTime value) {
        return utc(value, ZoneId.systemDefault());
    }

    static String utc(LocalDateTime value, ZoneId storedIn) {
        return value == null ? null : value.atZone(storedIn).toInstant().truncatedTo(ChronoUnit.SECONDS).toString();
    }
}
