package com.role_sync.workspace.services;

import com.role_sync.workspace.dto.ProfileLimitsResponse;
import com.role_sync.workspace.dto.WorkspaceProfileRequest;
import com.role_sync.workspace.models.WorkspaceProfile;
import com.role_sync.workspace.repository.OnboardingStateRepository;
import com.role_sync.workspace.repository.WorkspacePreferencesRepository;
import com.role_sync.workspace.repository.WorkspaceProfileRepository;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.SimpleTransactionStatus;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

import java.lang.reflect.Proxy;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The profile service's limits over a repository that holds one profile: what counts as a save and as a
 * photo change, and that a refused save changes nothing.
 */
class WorkspaceProfileLimitsTest {

    private static final UUID USER = UUID.randomUUID();
    private static final String PHOTO = "https://res.cloudinary.com/demo/image/upload/rolesync/avatars/a.png";
    private static final String OTHER_PHOTO = "https://res.cloudinary.com/demo/image/upload/rolesync/avatars/b.png";

    private final List<String> uploads = new ArrayList<>();

    private static WorkspaceProfile profile(int saves, int photos) {
        LocalDateTime opened = LocalDateTime.now().minusHours(1);
        return WorkspaceProfile.builder()
                .profileId(UUID.randomUUID()).authUserId(USER).firstName("Rohan").avatarUrl(PHOTO)
                .dailyUpdateCount(saves).updateWindowStart(saves > 0 ? opened : null)
                .avatarChangeCount(photos).avatarWindowStart(photos > 0 ? opened : null)
                .build();
    }

    /** The service over repositories that know {@code stored} (for USER) and a Cloudinary that records uploads. */
    private WorkspaceProfileServiceImpl serviceWith(WorkspaceProfile stored) {
        WorkspaceProfileRepository profiles = stub(WorkspaceProfileRepository.class, (name, args) -> switch (name) {
            case "findByAuthUserId" -> USER.equals(args[0]) ? Optional.ofNullable(stored) : Optional.empty();
            case "lockByProfileId" -> Optional.ofNullable(stored);
            case "save" -> args[0];
            default -> throw new UnsupportedOperationException(name);
        });
        CloudinaryService cloudinary = new CloudinaryService() {
            @Override
            public Mono<String> uploadAvatar(FilePart filePart, String userId) {
                return Mono.error(new UnsupportedOperationException());
            }

            @Override
            public Mono<String> uploadImageBytes(byte[] bytes, String filename, String contentType) {
                return Mono.error(new UnsupportedOperationException());
            }

            @Override
            public Mono<String> uploadImageUrl(String imageUrl, String userId) {
                uploads.add(imageUrl);
                return Mono.just(OTHER_PHOTO);
            }
        };
        PlatformTransactionManager transactions = new PlatformTransactionManager() {
            @Override
            public TransactionStatus getTransaction(TransactionDefinition definition) {
                return new SimpleTransactionStatus();
            }

            @Override
            public void commit(TransactionStatus status) {
            }

            @Override
            public void rollback(TransactionStatus status) {
            }
        };
        return new WorkspaceProfileServiceImpl(profiles, stub(WorkspacePreferencesRepository.class, null),
                stub(OnboardingStateRepository.class, null), cloudinary, transactions);
    }

    private interface Answer {
        Object apply(String method, Object[] args);
    }

    @SuppressWarnings("unchecked")
    private static <T> T stub(Class<T> type, Answer answer) {
        return (T) Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[]{type}, (proxy, method, args) -> {
            if (method.getDeclaringClass() == Object.class) {
                return "toString".equals(method.getName()) ? type.getSimpleName() : method.invoke(type, args);
            }
            if (answer == null) {
                throw new UnsupportedOperationException(method.getName());
            }
            return answer.apply(method.getName(), args);
        });
    }

    private static WorkspaceProfileRequest rename(String firstName) {
        return WorkspaceProfileRequest.builder().firstName(firstName).build();
    }

    @Test
    void everySaveCountsAndTheTwentyFifthInADayIsRefusedWithoutChangingAnything() {
        WorkspaceProfile stored = profile(23, 0);
        WorkspaceProfileServiceImpl service = serviceWith(stored);

        service.createOrUpdateProfile(USER, rename("Ro")).block();
        assertEquals("Ro", stored.getFirstName());
        assertEquals(24, stored.getDailyUpdateCount());

        ResponseStatusException refused = assertThrows(ResponseStatusException.class,
                () -> service.createOrUpdateProfile(USER, rename("Rohan S.")).block());
        assertEquals(HttpStatus.TOO_MANY_REQUESTS, refused.getStatusCode());
        assertTrue(refused.getReason().contains("24 times every 24 hours"));
        assertEquals("Ro", stored.getFirstName());
        assertEquals(24, stored.getDailyUpdateCount());
    }

    @Test
    void aSaveThatPutsInADifferentPhotoAlsoCountsAPhotoChange() {
        WorkspaceProfile stored = profile(1, 0);
        WorkspaceProfileServiceImpl service = serviceWith(stored);

        service.createOrUpdateProfile(USER, WorkspaceProfileRequest.builder().avatarUrl(PHOTO).bio("Hi").build()).block();
        assertEquals(2, stored.getDailyUpdateCount());
        assertEquals(0, stored.getAvatarChangeCount()); // the same photo: no photo change

        service.createOrUpdateProfile(USER, WorkspaceProfileRequest.builder().avatarUrl(OTHER_PHOTO).build()).block();
        assertEquals(3, stored.getDailyUpdateCount());
        assertEquals(1, stored.getAvatarChangeCount());
        assertEquals(OTHER_PHOTO, stored.getAvatarUrl());
        assertTrue(uploads.isEmpty()); // already hosted: nothing to upload
    }

    @Test
    void aSaveWithANewPhotoOverThePhotoLimitIsRefusedBeforeAnythingIsUploaded() {
        WorkspaceProfile stored = profile(1, 3);
        WorkspaceProfileServiceImpl service = serviceWith(stored);
        WorkspaceProfileRequest request = WorkspaceProfileRequest.builder()
                .firstName("Changed").avatarUrl("https://example.com/me.png").build();

        ResponseStatusException refused = assertThrows(ResponseStatusException.class,
                () -> service.createOrUpdateProfile(USER, request).block());

        assertEquals(HttpStatus.TOO_MANY_REQUESTS, refused.getStatusCode());
        assertTrue(refused.getReason().contains("3 times every 24 hours"));
        assertTrue(uploads.isEmpty());
        assertEquals("Rohan", stored.getFirstName());
        assertEquals(PHOTO, stored.getAvatarUrl());
        assertEquals(1, stored.getDailyUpdateCount());
    }

    @Test
    void removingThePhotoIsAllowedWhenNoPhotoChangeIsLeft() {
        WorkspaceProfile stored = profile(1, 3);

        serviceWith(stored).createOrUpdateProfile(USER, WorkspaceProfileRequest.builder().avatarUrl("").build()).block();

        assertNull(stored.getAvatarUrl());
        assertEquals(3, stored.getAvatarChangeCount());
        assertEquals(2, stored.getDailyUpdateCount());
    }

    @Test
    void uploadedPhotosCountOnlyAsPhotoChanges() {
        WorkspaceProfile stored = profile(5, 2);
        WorkspaceProfileServiceImpl service = serviceWith(stored);

        service.requirePhotoChangeLeft(USER).block();
        service.updateAvatarUrl(USER, OTHER_PHOTO).block();
        assertEquals(3, stored.getAvatarChangeCount());
        assertEquals(5, stored.getDailyUpdateCount());

        ResponseStatusException refused = assertThrows(ResponseStatusException.class,
                () -> service.requirePhotoChangeLeft(USER).block());
        assertEquals(HttpStatus.TOO_MANY_REQUESTS, refused.getStatusCode());
        assertThrows(ResponseStatusException.class, () -> service.updateAvatarUrl(USER, PHOTO).block());
        assertEquals(OTHER_PHOTO, stored.getAvatarUrl());
    }

    @Test
    void limitsSayWhatIsLeftAndWhenTheAllowanceIsBack() {
        WorkspaceProfile stored = profile(4, 0);

        ProfileLimitsResponse limits = serviceWith(stored).getLimits(USER).block();

        assertEquals(new ProfileLimitsResponse.Allowance(3, 0, 3, 24, null), limits.photoChanges());
        ProfileLimitsResponse.Allowance saves = limits.profileSaves();
        assertEquals(24, saves.limit());
        assertEquals(4, saves.used());
        assertEquals(20, saves.remaining());
        Instant resetsAt = Instant.parse(saves.resetsAt());
        long minutesAway = Instant.now().until(resetsAt, ChronoUnit.MINUTES);
        assertTrue(minutesAway > 22 * 60 && minutesAway <= 23 * 60, "resets about 23 hours from now: " + resetsAt);
    }
}
