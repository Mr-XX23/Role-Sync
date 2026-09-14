package com.role_sync.workspace.services;

import com.role_sync.workspace.models.WorkspaceProfile;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.time.Duration;
import java.time.LocalDateTime;

/**
 * How often a person may change their profile: 24 profile saves and 3 profile photo changes every
 * 24 hours, counted separately. Each count has its own window, which opens with the first change
 * after the previous window ended; when a window ends, the full allowance is back.
 *
 * <p>Pure rules over the profile's counters, so they are testable without a database.
 */
public final class ProfileChangeLimits {

    public static final Duration WINDOW = Duration.ofHours(24);

    public enum Kind {
        PROFILE_SAVES(24, "Profile update limit reached. You can update your profile 24 times every 24 hours."),
        PHOTO_CHANGES(3, "Profile photo limit reached. You can change your profile photo 3 times every 24 hours.");

        private final int limit;
        private final String refusal;

        Kind(int limit, String refusal) {
            this.limit = limit;
            this.refusal = refusal;
        }

        public int limit() {
            return limit;
        }
    }

    /** One allowance at a moment: changes used in the open window ({@code windowStart} null: no window is open). */
    public record Usage(Kind kind, int used, LocalDateTime windowStart) {

        public int limit() {
            return kind.limit;
        }

        public int remaining() {
            return Math.max(0, kind.limit - used);
        }

        /** When the open window ends and the full allowance is back; null when none of it is used. */
        public LocalDateTime resetsAt() {
            return windowStart == null ? null : windowStart.plus(WINDOW);
        }

        /** The allowance after one more change at {@code now}; 429 when the open window has none left. */
        public Usage plusOne(LocalDateTime now) {
            if (windowStart == null) {
                return new Usage(kind, 1, now);
            }
            if (remaining() == 0) {
                throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS,
                        kind.refusal + " Please try again in " + waitText(now, resetsAt()) + ".");
            }
            return new Usage(kind, used + 1, windowStart);
        }
    }

    private ProfileChangeLimits() {
    }

    /** The profile's allowance of this kind at {@code now}; a person without a profile has all of it. */
    public static Usage usage(WorkspaceProfile profile, Kind kind, LocalDateTime now) {
        if (profile == null) {
            return new Usage(kind, 0, null);
        }
        return switch (kind) {
            case PROFILE_SAVES -> usage(kind, profile.getDailyUpdateCount(), profile.getUpdateWindowStart(), now);
            case PHOTO_CHANGES -> usage(kind, profile.getAvatarChangeCount(), profile.getAvatarWindowStart(), now);
        };
    }

    /** Stores an allowance (usually one {@link Usage#plusOne} returned) in the profile's counters. */
    public static void record(WorkspaceProfile profile, Usage usage) {
        switch (usage.kind()) {
            case PROFILE_SAVES -> {
                profile.setDailyUpdateCount(usage.used());
                profile.setUpdateWindowStart(usage.windowStart());
            }
            case PHOTO_CHANGES -> {
                profile.setAvatarChangeCount(usage.used());
                profile.setAvatarWindowStart(usage.windowStart());
            }
        }
    }

    /**
     * Whether saving {@code requested} as the photo puts a different picture in place of {@code current}.
     * Keeping the same one doesn't count, and neither does removing the photo: that is always allowed.
     */
    public static boolean isNewPhoto(String current, String requested) {
        String next = blankToNull(requested);
        return next != null && !next.equals(blankToNull(current));
    }

    static Usage usage(Kind kind, Integer count, LocalDateTime windowStart, LocalDateTime now) {
        if (windowStart == null || !now.isBefore(windowStart.plus(WINDOW))) {
            return new Usage(kind, 0, null);
        }
        return new Usage(kind, count == null ? 0 : Math.max(0, count), windowStart);
    }

    /** "3 hour(s) and 12 minute(s)": the wait until {@code until}, rounded up to a whole minute. */
    static String waitText(LocalDateTime now, LocalDateTime until) {
        long minutes = Math.max(1, (Duration.between(now, until).toSeconds() + 59) / 60);
        long hours = minutes / 60;
        long rest = minutes % 60;
        if (hours == 0) {
            return rest + " minute(s)";
        }
        return rest == 0 ? hours + " hour(s)" : hours + " hour(s) and " + rest + " minute(s)";
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
