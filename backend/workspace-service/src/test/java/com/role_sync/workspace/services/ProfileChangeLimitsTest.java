package com.role_sync.workspace.services;

import com.role_sync.workspace.models.WorkspaceProfile;
import com.role_sync.workspace.services.ProfileChangeLimits.Kind;
import com.role_sync.workspace.services.ProfileChangeLimits.Usage;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.time.LocalDateTime;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Offline tests for the profile save and photo change allowances (pure rules over the counters). */
class ProfileChangeLimitsTest {

    private static final LocalDateTime NOW = LocalDateTime.of(2026, 9, 14, 12, 0);

    @Test
    void aNewProfileHasTwentyFourSavesAndThreePhotoChanges() {
        WorkspaceProfile profile = WorkspaceProfile.builder().build();

        Usage saves = ProfileChangeLimits.usage(profile, Kind.PROFILE_SAVES, NOW);
        Usage photos = ProfileChangeLimits.usage(profile, Kind.PHOTO_CHANGES, NOW);

        assertEquals(24, saves.remaining());
        assertEquals(3, photos.remaining());
        assertNull(saves.resetsAt()); // nothing used: no window is open
        assertEquals(24, ProfileChangeLimits.usage(null, Kind.PROFILE_SAVES, NOW).remaining());
    }

    @Test
    void theTwentyFourthSaveIsAllowedAndTheTwentyFifthIsRefusedUntilTheWindowEnds() {
        WorkspaceProfile profile = WorkspaceProfile.builder()
                .dailyUpdateCount(23).updateWindowStart(NOW.minusHours(2)).build();

        Usage last = ProfileChangeLimits.usage(profile, Kind.PROFILE_SAVES, NOW).plusOne(NOW);
        assertEquals(24, last.used());
        assertEquals(NOW.minusHours(2), last.windowStart()); // the window doesn't move
        ProfileChangeLimits.record(profile, last);

        ResponseStatusException refused = assertThrows(ResponseStatusException.class,
                () -> ProfileChangeLimits.usage(profile, Kind.PROFILE_SAVES, NOW).plusOne(NOW));
        assertEquals(HttpStatus.TOO_MANY_REQUESTS, refused.getStatusCode());
        assertEquals("Profile update limit reached. You can update your profile 24 times every 24 hours. "
                + "Please try again in 22 hour(s).", refused.getReason());
    }

    @Test
    void aWindowEndsTwentyFourHoursAfterItsFirstChangeAndTheCountStartsAgain() {
        WorkspaceProfile profile = WorkspaceProfile.builder()
                .dailyUpdateCount(24).updateWindowStart(NOW.minusHours(24)).build();

        Usage saves = ProfileChangeLimits.usage(profile, Kind.PROFILE_SAVES, NOW);
        assertEquals(0, saves.used());
        assertNull(saves.resetsAt());

        Usage next = saves.plusOne(NOW);
        assertEquals(1, next.used());
        assertEquals(NOW, next.windowStart());
        assertEquals(NOW.plusHours(24), next.resetsAt());
    }

    @Test
    void photoChangesHaveTheirOwnSmallerAllowance() {
        WorkspaceProfile profile = WorkspaceProfile.builder()
                .avatarChangeCount(3).avatarWindowStart(NOW.minusMinutes(30))
                .dailyUpdateCount(1).updateWindowStart(NOW.minusMinutes(30)).build();

        ResponseStatusException refused = assertThrows(ResponseStatusException.class,
                () -> ProfileChangeLimits.usage(profile, Kind.PHOTO_CHANGES, NOW).plusOne(NOW));
        assertTrue(refused.getReason().startsWith(
                "Profile photo limit reached. You can change your profile photo 3 times every 24 hours."));
        assertTrue(refused.getReason().endsWith("Please try again in 23 hour(s) and 30 minute(s)."));
        assertEquals(23, ProfileChangeLimits.usage(profile, Kind.PROFILE_SAVES, NOW).remaining());
    }

    @Test
    void onlyADifferentPictureCountsAsAPhotoChange() {
        String photo = "https://res.cloudinary.com/demo/rolesync/avatars/a.png";
        assertTrue(ProfileChangeLimits.isNewPhoto(null, photo)); // the first photo
        assertTrue(ProfileChangeLimits.isNewPhoto(photo, "https://res.cloudinary.com/demo/rolesync/avatars/b.png"));
        assertFalse(ProfileChangeLimits.isNewPhoto(photo, " " + photo + " ")); // the same picture again
        assertFalse(ProfileChangeLimits.isNewPhoto(photo, null)); // removing the photo is always allowed
        assertFalse(ProfileChangeLimits.isNewPhoto(photo, ""));
    }

    @Test
    void theWaitIsRoundedUpToAWholeMinute() {
        assertEquals("1 minute(s)", ProfileChangeLimits.waitText(NOW, NOW.plusSeconds(5)));
        assertEquals("2 hour(s)", ProfileChangeLimits.waitText(NOW, NOW.plusHours(2)));
        assertEquals("3 hour(s) and 5 minute(s)", ProfileChangeLimits.waitText(NOW, NOW.plusHours(3).plusMinutes(4).plusSeconds(1)));
    }
}
