package com.role_sync.workspace.services;

import com.role_sync.workspace.dto.OnboardingStepRequest;
import com.role_sync.workspace.dto.PreferencesRequest;
import com.role_sync.workspace.dto.ProfileLimitsResponse;
import com.role_sync.workspace.dto.WorkspaceProfileRequest;
import com.role_sync.workspace.models.OnboardingState;
import com.role_sync.workspace.models.WorkspacePreferences;
import com.role_sync.workspace.models.WorkspaceProfile;
import com.role_sync.workspace.repository.OnboardingStateRepository;
import com.role_sync.workspace.repository.WorkspacePreferencesRepository;
import com.role_sync.workspace.repository.WorkspaceProfileRepository;
import com.role_sync.workspace.services.ProfileChangeLimits.Kind;
import com.role_sync.workspace.services.ProfileChangeLimits.Usage;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.UUID;
import java.util.function.Supplier;

@Slf4j
@Service
@RequiredArgsConstructor
public class WorkspaceProfileServiceImpl implements WorkspaceProfileService {

    private final WorkspaceProfileRepository workspaceProfileRepository;
    private final WorkspacePreferencesRepository workspacePreferencesRepository;
    private final OnboardingStateRepository onboardingStateRepository;
    private final CloudinaryService cloudinaryService;
    private final PlatformTransactionManager transactionManager;

    @Override
    public Mono<WorkspaceProfile> createOrUpdateProfile(UUID authUserId, WorkspaceProfileRequest request) {
        return Mono.fromCallable(() -> {
            String sanitizedFirst = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getFirstName());
            String sanitizedLast = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getLastName());
            String sanitizedDisplay = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getDisplayName());
            String sanitizedAvatar = com.role_sync.workspace.utils.SanitizationUtils.sanitizeUrl(request.getAvatarUrl());
            String sanitizedJob = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getJobTitle());
            String sanitizedDept = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getDepartment());
            String sanitizedOrg = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getOrganization());
            String sanitizedLoc = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getLocation());
            String sanitizedSecEmail = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getSecondaryEmail());
            String sanitizedPhone = com.role_sync.workspace.utils.SanitizationUtils.sanitizePhoneNumber(request.getPhoneNumber());
            String sanitizedEdu = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getEducation());
            String sanitizedExp = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getExpertise());
            String sanitizedSkills = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getSkills());
            String sanitizedInterests = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getInterests());
            String sanitizedHobbies = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getHobbies());
            String sanitizedAiContext = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getAiPersonaContext());
            String sanitizedCommStyle = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getCommunicationStyle());
            String sanitizedLinkedin = com.role_sync.workspace.utils.SanitizationUtils.sanitizeUrl(request.getLinkedinUrl());
            String sanitizedGithub = com.role_sync.workspace.utils.SanitizationUtils.sanitizeUrl(request.getGithubUrl());
            String sanitizedWebsite = com.role_sync.workspace.utils.SanitizationUtils.sanitizeUrl(request.getWebsiteUrl());
            String sanitizedFacebook = com.role_sync.workspace.utils.SanitizationUtils.sanitizeUrl(request.getFacebookUrl());
            String sanitizedX = com.role_sync.workspace.utils.SanitizationUtils.sanitizeUrl(request.getXUrl());
            String sanitizedInstagram = com.role_sync.workspace.utils.SanitizationUtils.sanitizeUrl(request.getInstagramUrl());
            String sanitizedBio = com.role_sync.workspace.utils.SanitizationUtils.sanitizeText(request.getBio());

            WorkspaceProfile existing = workspaceProfileRepository.findByAuthUserId(authUserId).orElse(null);
            boolean newPhoto = request.getAvatarUrl() != null
                    && ProfileChangeLimits.isNewPhoto(existing == null ? null : existing.getAvatarUrl(), sanitizedAvatar);
            if (existing != null) {
                // A save over a limit is refused before its photo is hosted; the counts are taken under a lock below.
                LocalDateTime checkedAt = LocalDateTime.now();
                ProfileChangeLimits.usage(existing, Kind.PROFILE_SAVES, checkedAt).plusOne(checkedAt);
                if (newPhoto) {
                    ProfileChangeLimits.usage(existing, Kind.PHOTO_CHANGES, checkedAt).plusOne(checkedAt);
                }
            }

            // If a new external image URL is provided and not yet hosted on Cloudinary, host it permanently
            if (newPhoto && !sanitizedAvatar.contains("cloudinary.com")) {
                try {
                    String permanentUrl = cloudinaryService.uploadImageUrl(sanitizedAvatar, authUserId.toString()).block();
                    if (permanentUrl != null && !permanentUrl.isBlank()) {
                        sanitizedAvatar = permanentUrl;
                    }
                } catch (Exception e) {
                    log.warn("Could not convert external avatar URL to Cloudinary on profile save: {}", e.getMessage());
                }
            }

            LocalDateTime now = LocalDateTime.now();
            WorkspaceProfile profile;
            if (existing == null) {
                profile = WorkspaceProfile.builder()
                        .authUserId(authUserId)
                        .dailyUpdateCount(1)
                        .updateWindowStart(now)
                        .avatarChangeCount(newPhoto ? 1 : 0)
                        .avatarWindowStart(newPhoto ? now : null)
                        .firstName(sanitizedFirst)
                        .lastName(sanitizedLast)
                        .displayName(sanitizedDisplay)
                        .avatarUrl(sanitizedAvatar)
                        .jobTitle(sanitizedJob)
                        .department(sanitizedDept)
                        .organization(sanitizedOrg)
                        .location(sanitizedLoc)
                        .secondaryEmail(sanitizedSecEmail)
                        .phoneNumber(sanitizedPhone)
                        .education(sanitizedEdu)
                        .expertise(sanitizedExp)
                        .skills(sanitizedSkills)
                        .interests(sanitizedInterests)
                        .hobbies(sanitizedHobbies)
                        .aiPersonaContext(sanitizedAiContext)
                        .communicationStyle(sanitizedCommStyle)
                        .linkedinUrl(sanitizedLinkedin)
                        .githubUrl(sanitizedGithub)
                        .websiteUrl(sanitizedWebsite)
                        .facebookUrl(sanitizedFacebook)
                        .xUrl(sanitizedX)
                        .instagramUrl(sanitizedInstagram)
                        .bio(sanitizedBio)
                        .build();
                profile = workspaceProfileRepository.save(profile);

                // Create default preferences
                WorkspacePreferences prefs = WorkspacePreferences.builder()
                        .profile(profile)
                        .theme("dark")
                        .language("en")
                        .timezone("UTC")
                        .build();
                workspacePreferencesRepository.save(prefs);

                // Create default onboarding state
                OnboardingState onboarding = OnboardingState.builder()
                        .profile(profile)
                        .currentStep("PROFILE_SETUP")
                        .isCompleted(false)
                        .build();
                onboardingStateRepository.save(onboarding);
            } else {
                String photo = sanitizedAvatar;
                profile = inTransaction(() -> {
                    WorkspaceProfile locked = workspaceProfileRepository.lockByProfileId(existing.getProfileId())
                            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace profile not found"));
                    // Both counts are taken before anything changes: a save over either limit changes nothing.
                    Usage saves = ProfileChangeLimits.usage(locked, Kind.PROFILE_SAVES, now).plusOne(now);
                    Usage photos = request.getAvatarUrl() != null && ProfileChangeLimits.isNewPhoto(locked.getAvatarUrl(), photo)
                            ? ProfileChangeLimits.usage(locked, Kind.PHOTO_CHANGES, now).plusOne(now)
                            : null;
                    ProfileChangeLimits.record(locked, saves);
                    if (photos != null) {
                        ProfileChangeLimits.record(locked, photos);
                    }
                    if (request.getFirstName() != null) locked.setFirstName(sanitizedFirst);
                    if (request.getLastName() != null) locked.setLastName(sanitizedLast);
                    if (request.getDisplayName() != null) locked.setDisplayName(sanitizedDisplay);
                    if (request.getAvatarUrl() != null) locked.setAvatarUrl(photo);
                    if (request.getJobTitle() != null) locked.setJobTitle(sanitizedJob);
                    if (request.getDepartment() != null) locked.setDepartment(sanitizedDept);
                    if (request.getOrganization() != null) locked.setOrganization(sanitizedOrg);
                    if (request.getLocation() != null) locked.setLocation(sanitizedLoc);
                    if (request.getSecondaryEmail() != null) locked.setSecondaryEmail(sanitizedSecEmail);
                    if (request.getPhoneNumber() != null) locked.setPhoneNumber(sanitizedPhone);
                    if (request.getEducation() != null) locked.setEducation(sanitizedEdu);
                    if (request.getExpertise() != null) locked.setExpertise(sanitizedExp);
                    if (request.getSkills() != null) locked.setSkills(sanitizedSkills);
                    if (request.getInterests() != null) locked.setInterests(sanitizedInterests);
                    if (request.getHobbies() != null) locked.setHobbies(sanitizedHobbies);
                    if (request.getAiPersonaContext() != null) locked.setAiPersonaContext(sanitizedAiContext);
                    if (request.getCommunicationStyle() != null) locked.setCommunicationStyle(sanitizedCommStyle);
                    if (request.getLinkedinUrl() != null) locked.setLinkedinUrl(sanitizedLinkedin);
                    if (request.getGithubUrl() != null) locked.setGithubUrl(sanitizedGithub);
                    if (request.getWebsiteUrl() != null) locked.setWebsiteUrl(sanitizedWebsite);
                    if (request.getFacebookUrl() != null) locked.setFacebookUrl(sanitizedFacebook);
                    if (request.getXUrl() != null) locked.setXUrl(sanitizedX);
                    if (request.getInstagramUrl() != null) locked.setInstagramUrl(sanitizedInstagram);
                    if (request.getBio() != null) locked.setBio(sanitizedBio);
                    return workspaceProfileRepository.save(locked);
                });
            }
            return profile;
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    public Mono<WorkspaceProfile> updateAvatarUrl(UUID authUserId, String avatarUrl) {
        return Mono.fromCallable(() -> {
            WorkspaceProfile profile = getOrCreateProfile(authUserId);
            return inTransaction(() -> {
                WorkspaceProfile locked = workspaceProfileRepository.lockByProfileId(profile.getProfileId())
                        .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace profile not found"));
                if (ProfileChangeLimits.isNewPhoto(locked.getAvatarUrl(), avatarUrl)) {
                    LocalDateTime now = LocalDateTime.now();
                    ProfileChangeLimits.record(locked, ProfileChangeLimits.usage(locked, Kind.PHOTO_CHANGES, now).plusOne(now));
                }
                locked.setAvatarUrl(avatarUrl);
                return workspaceProfileRepository.save(locked);
            });
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    public Mono<Void> requirePhotoChangeLeft(UUID authUserId) {
        return Mono.fromRunnable(() -> workspaceProfileRepository.findByAuthUserId(authUserId).ifPresent(profile -> {
                    LocalDateTime now = LocalDateTime.now();
                    ProfileChangeLimits.usage(profile, Kind.PHOTO_CHANGES, now).plusOne(now);
                }))
                .subscribeOn(Schedulers.boundedElastic())
                .then();
    }

    @Override
    public Mono<ProfileLimitsResponse> getLimits(UUID authUserId) {
        return Mono.fromCallable(() -> {
            WorkspaceProfile profile = workspaceProfileRepository.findByAuthUserId(authUserId).orElse(null);
            LocalDateTime now = LocalDateTime.now();
            return new ProfileLimitsResponse(
                    allowance(ProfileChangeLimits.usage(profile, Kind.PROFILE_SAVES, now)),
                    allowance(ProfileChangeLimits.usage(profile, Kind.PHOTO_CHANGES, now)));
        }).subscribeOn(Schedulers.boundedElastic());
    }

    private static ProfileLimitsResponse.Allowance allowance(Usage usage) {
        LocalDateTime resetsAt = usage.resetsAt();
        return new ProfileLimitsResponse.Allowance(usage.limit(), usage.used(), usage.remaining(),
                ProfileChangeLimits.WINDOW.toHours(),
                resetsAt == null ? null : resetsAt.atZone(ZoneId.systemDefault()).toInstant().toString());
    }

    private <T> T inTransaction(Supplier<T> work) {
        return new TransactionTemplate(transactionManager).execute(status -> work.get());
    }

    private WorkspaceProfile getOrCreateProfile(UUID authUserId) {
        return workspaceProfileRepository.findByAuthUserId(authUserId)
                .orElseGet(() -> {
                    WorkspaceProfile profile = WorkspaceProfile.builder()
                            .authUserId(authUserId)
                            .firstName("")
                            .lastName("")
                            .jobTitle("")
                            .build();
                    profile = workspaceProfileRepository.save(profile);

                    WorkspacePreferences prefs = WorkspacePreferences.builder()
                            .profile(profile)
                            .theme("dark")
                            .language("en")
                            .timezone("UTC")
                            .build();
                    workspacePreferencesRepository.save(prefs);

                    OnboardingState onboarding = OnboardingState.builder()
                            .profile(profile)
                            .currentStep("PROFILE_SETUP")
                            .isCompleted(false)
                            .build();
                    onboardingStateRepository.save(onboarding);

                    return profile;
                });
    }

    @Override
    @Transactional
    public Mono<WorkspacePreferences> updatePreferences(UUID authUserId, PreferencesRequest request) {
        return Mono.fromCallable(() -> {
            WorkspaceProfile profile = getOrCreateProfile(authUserId);

            WorkspacePreferences prefs = workspacePreferencesRepository.findByProfileProfileId(profile.getProfileId())
                    .orElseGet(() -> WorkspacePreferences.builder().profile(profile).build());

            if (request.getTheme() != null) prefs.setTheme(request.getTheme());
            if (request.getLanguage() != null) prefs.setLanguage(request.getLanguage());
            if (request.getTimezone() != null) prefs.setTimezone(request.getTimezone());
            if (request.getDashboardLayout() != null) prefs.setDashboardLayout(request.getDashboardLayout());

            return workspacePreferencesRepository.save(prefs);
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    @Transactional
    public Mono<OnboardingState> updateOnboardingStep(UUID authUserId, OnboardingStepRequest request) {
        return Mono.fromCallable(() -> {
            WorkspaceProfile profile = getOrCreateProfile(authUserId);

            OnboardingState onboarding = onboardingStateRepository.findByProfileProfileId(profile.getProfileId())
                    .orElseGet(() -> OnboardingState.builder().profile(profile).build());

            if (request.getCurrentStep() != null) onboarding.setCurrentStep(request.getCurrentStep());
            if (request.getCompletedSteps() != null) onboarding.setCompletedSteps(request.getCompletedSteps());
            if (request.getIsCompleted() != null) onboarding.setIsCompleted(request.getIsCompleted());

            return onboardingStateRepository.save(onboarding);
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    @Transactional(readOnly = true)
    public Mono<WorkspaceProfile> getProfile(UUID authUserId) {
        return Mono.fromCallable(() -> getOrCreateProfile(authUserId))
                .subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    @Transactional(readOnly = true)
    public Mono<WorkspacePreferences> getPreferences(UUID authUserId) {
        return Mono.fromCallable(() -> {
            WorkspaceProfile profile = getOrCreateProfile(authUserId);
            return workspacePreferencesRepository.findByProfileProfileId(profile.getProfileId())
                    .orElseGet(() -> {
                        WorkspacePreferences prefs = WorkspacePreferences.builder()
                                .profile(profile)
                                .theme("dark")
                                .language("en")
                                .timezone("UTC")
                                .build();
                        return workspacePreferencesRepository.save(prefs);
                    });
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    @Transactional(readOnly = true)
    public Mono<OnboardingState> getOnboardingState(UUID authUserId) {
        return Mono.fromCallable(() -> {
            WorkspaceProfile profile = getOrCreateProfile(authUserId);
            return onboardingStateRepository.findByProfileProfileId(profile.getProfileId())
                    .orElseGet(() -> {
                        OnboardingState onboarding = OnboardingState.builder()
                                .profile(profile)
                                .currentStep("PROFILE_SETUP")
                                .isCompleted(false)
                                .build();
                        return onboardingStateRepository.save(onboarding);
                    });
        }).subscribeOn(Schedulers.boundedElastic());
    }
}
