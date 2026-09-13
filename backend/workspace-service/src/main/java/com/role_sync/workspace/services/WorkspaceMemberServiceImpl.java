package com.role_sync.workspace.services;

import com.role_sync.workspace.clients.AuthAccountClient;
import com.role_sync.workspace.clients.AuthAccountClient.Account;
import com.role_sync.workspace.clients.AuthAccountClient.EmailOutcome;
import com.role_sync.workspace.dto.AddMemberRequest;
import com.role_sync.workspace.dto.InviteMemberRequest;
import com.role_sync.workspace.dto.InviteMemberResponse;
import com.role_sync.workspace.dto.MemberActivityResponse;
import com.role_sync.workspace.dto.MemberListResponse;
import com.role_sync.workspace.dto.MemberResponse;
import com.role_sync.workspace.dto.UpdateMemberRoleRequest;
import com.role_sync.workspace.dto.WorkspaceMembershipResponse;
import com.role_sync.workspace.models.OnboardingState;
import com.role_sync.workspace.models.Workspace;
import com.role_sync.workspace.models.WorkspaceMemberEvent;
import com.role_sync.workspace.models.WorkspaceMembership;
import com.role_sync.workspace.models.WorkspacePreferences;
import com.role_sync.workspace.models.WorkspaceProfile;
import com.role_sync.workspace.models.WorkspaceRole;
import com.role_sync.workspace.repository.OnboardingStateRepository;
import com.role_sync.workspace.repository.WorkspaceMemberEventRepository;
import com.role_sync.workspace.repository.WorkspaceMembershipRepository;
import com.role_sync.workspace.repository.WorkspacePreferencesRepository;
import com.role_sync.workspace.repository.WorkspaceProfileRepository;
import com.role_sync.workspace.repository.WorkspaceRepository;
import com.role_sync.workspace.repository.WorkspaceRoleRepository;
import com.role_sync.workspace.services.WorkspaceAuthorizationService.CallerContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Supplier;

@Slf4j
@Service
@RequiredArgsConstructor
public class WorkspaceMemberServiceImpl implements WorkspaceMemberService {

    private static final int MAX_ACTIVITY = 200;

    private final WorkspaceRepository workspaceRepository;
    private final WorkspaceProfileRepository profileRepository;
    private final WorkspaceRoleRepository roleRepository;
    private final WorkspaceMembershipRepository membershipRepository;
    private final WorkspaceMemberEventRepository eventRepository;
    private final WorkspacePreferencesRepository preferencesRepository;
    private final OnboardingStateRepository onboardingStateRepository;
    private final WorkspaceAuthorizationService authorizationService;
    private final AuthAccountClient accountClient;
    private final PlatformTransactionManager transactionManager;

    private record Added(UUID membershipId, boolean reactivated) {
    }

    @Override
    public Mono<MemberListResponse> listMembers(UUID workspaceId, UUID callerAuthUserId) {
        return Mono.fromCallable(() -> {
            CallerContext caller = authorizationService.requireAdmin(callerAuthUserId, workspaceId);
            Workspace workspace = requireWorkspace(workspaceId);
            UUID ownerProfileId = workspaceRepository.findOwnerProfileId(workspaceId).orElse(null);
            List<WorkspaceMembership> memberships = membershipRepository.findMembersOfWorkspace(workspaceId);

            Set<UUID> authUserIds = new LinkedHashSet<>();
            Set<UUID> inviterIds = new LinkedHashSet<>();
            for (WorkspaceMembership membership : memberships) {
                authUserIds.add(membership.getProfile().getAuthUserId());
                if (membership.getInvitedByProfileId() != null) {
                    inviterIds.add(membership.getInvitedByProfileId());
                }
            }
            Map<UUID, Account> accounts;
            boolean accountsAvailable = true;
            try {
                accounts = accountClient.lookup(authUserIds);
            } catch (ResponseStatusException e) {
                log.warn("Listing members of {} without sign-in details: {}", workspaceId, e.getReason());
                accounts = Map.of();
                accountsAvailable = false;
            }
            Map<UUID, WorkspaceProfile> inviters = new HashMap<>();
            profileRepository.findAllById(inviterIds).forEach(profile -> inviters.put(profile.getProfileId(), profile));

            LocalDateTime now = LocalDateTime.now();
            final Map<UUID, Account> known = accounts;
            List<MemberResponse> members = memberships.stream()
                    .map(membership -> toMember(membership, caller, ownerProfileId,
                            known.get(membership.getProfile().getAuthUserId()), inviters, now))
                    .toList();

            return MemberListResponse.builder()
                    .workspaceId(workspaceId)
                    .workspaceName(workspace.getName())
                    .yourRole(caller.roleName())
                    .assignableRoles(MemberAccess.assignableRoles(caller))
                    .accountDetailsAvailable(accountsAvailable)
                    .members(members)
                    .build();
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    public Mono<InviteMemberResponse> inviteMember(UUID workspaceId, UUID callerAuthUserId, InviteMemberRequest request) {
        return Mono.fromCallable(() -> {
            CallerContext caller = authorizationService.requireAdmin(callerAuthUserId, workspaceId);
            String email = MemberAccess.normalizeEmail(request.getEmail());
            String firstName = MemberAccess.cleanName(request.getFirstName(), "first name", true);
            String lastName = MemberAccess.cleanName(request.getLastName(), "last name", false);
            String roleName = authorizationService.validateAssignableRole(request.getRoleName(), caller);
            Workspace workspace = requireWorkspace(workspaceId);
            String inviterName = callerName(caller);

            Account account = accountClient.provision(email, fullName(firstName, lastName), callerAuthUserId);
            if (account.authUserId().equals(callerAuthUserId)) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "That's your own email address.");
            }
            // Sign-in details go out when the account is new, or nobody has signed in with it yet.
            boolean sendCredentials = account.wasCreated() || account.awaitingFirstSignIn();

            Added added;
            try {
                added = inTransaction(() -> addToWorkspace(workspace, caller, inviterName, account, email,
                        firstName, lastName, roleName, sendCredentials));
            } catch (DataIntegrityViolationException e) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "Someone else just added this person. Refresh the member list.");
            }

            EmailOutcome outcome;
            try {
                outcome = sendCredentials
                        ? accountClient.issueTemporaryPassword(account.authUserId(), workspace.getName(), inviterName, false)
                        : accountClient.sendWorkspaceAccessEmail(account.authUserId(), workspace.getName(), inviterName, roleName);
            } catch (ResponseStatusException e) {
                log.warn("Member {} added to workspace {} but the email failed: {}", account.authUserId(), workspaceId, e.getReason());
                outcome = EmailOutcome.failed(e.getReason());
            }

            return InviteMemberResponse.builder()
                    .member(memberView(added.membershipId(), caller))
                    .accountCreated(account.wasCreated())
                    .reactivated(added.reactivated())
                    .credentialsSent(sendCredentials)
                    .emailStatus(outcome.status())
                    .emailMessage(outcome.message())
                    .inviteExpiresAt(outcome.temporaryPasswordExpiresAt())
                    .build();
        }).subscribeOn(Schedulers.boundedElastic());
    }

    private Added addToWorkspace(Workspace workspace, CallerContext caller, String inviterName, Account account, String email,
                                 String firstName, String lastName, String roleName, boolean credentialsFromHere) {
        UUID workspaceId = workspace.getWorkspaceId();
        WorkspaceProfile profile = profileRepository.findByAuthUserId(account.authUserId())
                .orElseGet(() -> createProfile(account, firstName, lastName));
        // Serializes concurrent adds of the same person.
        profile = profileRepository.lockByProfileId(profile.getProfileId()).orElse(profile);
        if (isBlank(profile.getFirstName()) && isBlank(profile.getLastName())) {
            profile.setFirstName(firstName);
            profile.setLastName(lastName == null ? "" : lastName);
            profile = profileRepository.save(profile);
        }

        UUID ownerProfileId = workspaceRepository.findOwnerProfileId(workspaceId).orElse(null);
        WorkspaceMembership membership = membershipRepository
                .findByWorkspaceWorkspaceIdAndProfileProfileId(workspaceId, profile.getProfileId())
                .orElse(null);
        String previousRole = null;
        boolean reactivated = false;
        if (membership != null) {
            if (Boolean.TRUE.equals(membership.getIsActive())) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, email + " is already a member of this workspace.");
            }
            previousRole = membership.getRole().getRoleName();
            MemberAccess.requireCanManage(caller, profile.getProfileId(), previousRole, ownerProfileId);
            membership.setRole(findOrCreateRole(roleName));
            membership.setIsActive(true);
            membership.setInvitedByProfileId(caller.profileId());
            if (credentialsFromHere) {
                membership.setAccountCreated(true);
            }
            reactivated = true;
        } else {
            MemberAccess.requireCanManage(caller, profile.getProfileId(), roleName, ownerProfileId);
            membership = WorkspaceMembership.builder()
                    .workspace(workspace)
                    .profile(profile)
                    .role(findOrCreateRole(roleName))
                    .isActive(true)
                    .invitedByProfileId(caller.profileId())
                    .accountCreated(credentialsFromHere)
                    .build();
        }
        WorkspaceMembership saved = membershipRepository.save(membership);
        eventRepository.save(event(WorkspaceMemberEvent.MEMBER_ADDED, workspaceId, caller, inviterName, profile,
                account, previousRole, roleName));
        return new Added(saved.getMembershipId(), reactivated);
    }

    @Override
    public Mono<UUID> addMember(UUID workspaceId, UUID callerAuthUserId, AddMemberRequest request) {
        return Mono.fromCallable(() -> {
            CallerContext caller = authorizationService.requireAdmin(callerAuthUserId, workspaceId);
            Workspace workspace = requireWorkspace(workspaceId);
            String roleName = authorizationService.validateAssignableRole(request.getRoleName(), caller);
            String actorName = callerName(caller);
            return inTransaction(() -> {
                WorkspaceProfile profile = profileRepository.lockByProfileId(request.getProfileId())
                        .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Profile to add not found"));
                UUID ownerProfileId = workspaceRepository.findOwnerProfileId(workspaceId).orElse(null);
                WorkspaceMembership membership = membershipRepository
                        .findByWorkspaceWorkspaceIdAndProfileProfileId(workspaceId, profile.getProfileId())
                        .orElse(null);
                String previousRole = membership == null ? null : membership.getRole().getRoleName();
                MemberAccess.requireCanManage(caller, profile.getProfileId(), previousRole == null ? roleName : previousRole,
                        ownerProfileId);
                if (membership == null) {
                    membership = WorkspaceMembership.builder()
                            .workspace(workspace)
                            .profile(profile)
                            .isActive(true)
                            .invitedByProfileId(caller.profileId())
                            .accountCreated(false)
                            .build();
                }
                membership.setRole(findOrCreateRole(roleName));
                membership.setIsActive(true);
                WorkspaceMembership saved = membershipRepository.save(membership);
                eventRepository.save(event(WorkspaceMemberEvent.MEMBER_ADDED, workspaceId, caller, actorName, profile,
                        null, previousRole, roleName));
                return saved.getMembershipId();
            });
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    public Mono<WorkspaceMembershipResponse> updateMemberRole(UUID workspaceId, UUID membershipId, UUID callerAuthUserId,
                                                              UpdateMemberRoleRequest request) {
        return Mono.fromCallable(() -> {
            CallerContext caller = authorizationService.requireAdmin(callerAuthUserId, workspaceId);
            String roleName = authorizationService.validateAssignableRole(request.getRoleName(), caller);
            String actorName = callerName(caller);
            return inTransaction(() -> {
                WorkspaceMembership membership = requireMembership(workspaceId, membershipId);
                UUID ownerProfileId = workspaceRepository.findOwnerProfileId(workspaceId).orElse(null);
                String previousRole = membership.getRole().getRoleName();
                MemberAccess.requireCanManage(caller, membership.getProfile().getProfileId(), previousRole, ownerProfileId);
                WorkspaceMembership saved = membership;
                if (!previousRole.equals(roleName)) {
                    membership.setRole(findOrCreateRole(roleName));
                    saved = membershipRepository.save(membership);
                    eventRepository.save(event(WorkspaceMemberEvent.ROLE_CHANGED, workspaceId, caller, actorName,
                            membership.getProfile(), null, previousRole, roleName));
                }
                return WorkspaceMembershipResponse.builder()
                        .membershipId(saved.getMembershipId())
                        .workspaceId(workspaceId)
                        .profileId(membership.getProfile().getProfileId())
                        .roleName(roleName)
                        .joinedAt(saved.getJoinedAt())
                        .isActive(saved.getIsActive())
                        .build();
            });
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    public Mono<MemberResponse> setMemberActive(UUID workspaceId, UUID membershipId, UUID callerAuthUserId, boolean active) {
        return Mono.fromCallable(() -> {
            CallerContext caller = authorizationService.requireAdmin(callerAuthUserId, workspaceId);
            String actorName = callerName(caller);
            inTransaction(() -> {
                WorkspaceMembership membership = requireMembership(workspaceId, membershipId);
                UUID ownerProfileId = workspaceRepository.findOwnerProfileId(workspaceId).orElse(null);
                String role = membership.getRole().getRoleName();
                MemberAccess.requireCanManage(caller, membership.getProfile().getProfileId(), role, ownerProfileId);
                if (Boolean.TRUE.equals(membership.getIsActive()) != active) {
                    membership.setIsActive(active);
                    membershipRepository.save(membership);
                    eventRepository.save(event(active ? WorkspaceMemberEvent.MEMBER_REACTIVATED : WorkspaceMemberEvent.MEMBER_DEACTIVATED,
                            workspaceId, caller, actorName, membership.getProfile(), null, role, role));
                }
                return null;
            });
            return memberView(membershipId, caller);
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    public Mono<Void> removeMember(UUID workspaceId, UUID membershipId, UUID callerAuthUserId) {
        return Mono.fromRunnable(() -> {
            CallerContext caller = authorizationService.requireAdmin(callerAuthUserId, workspaceId);
            String actorName = callerName(caller);
            // The email is kept in the activity log, so look it up while the member still exists.
            WorkspaceMembership found = requireMembership(workspaceId, membershipId);
            Account account = accountOrNull(found.getProfile().getAuthUserId());
            inTransaction(() -> {
                WorkspaceMembership membership = requireMembership(workspaceId, membershipId);
                UUID ownerProfileId = workspaceRepository.findOwnerProfileId(workspaceId).orElse(null);
                String role = membership.getRole().getRoleName();
                MemberAccess.requireCanManage(caller, membership.getProfile().getProfileId(), role, ownerProfileId);
                eventRepository.save(event(WorkspaceMemberEvent.MEMBER_REMOVED, workspaceId, caller, actorName,
                        membership.getProfile(), account, role, null));
                membershipRepository.delete(membership);
                return null;
            });
        }).subscribeOn(Schedulers.boundedElastic()).then();
    }

    @Override
    public Mono<InviteMemberResponse> resendInvite(UUID workspaceId, UUID membershipId, UUID callerAuthUserId) {
        return Mono.fromCallable(() -> {
            CallerContext caller = authorizationService.requireAdmin(callerAuthUserId, workspaceId);
            WorkspaceMembership membership = requireMembership(workspaceId, membershipId);
            UUID ownerProfileId = workspaceRepository.findOwnerProfileId(workspaceId).orElse(null);
            String role = membership.getRole().getRoleName();
            MemberAccess.requireCanManage(caller, membership.getProfile().getProfileId(), role, ownerProfileId);
            if (!Boolean.TRUE.equals(membership.getIsActive())) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "Reactivate this member before sending them new sign-in details.");
            }
            if (!Boolean.TRUE.equals(membership.getAccountCreated())) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "This person's sign-in details weren't sent from this workspace, so they can't be resent here.");
            }
            UUID authUserId = membership.getProfile().getAuthUserId();
            Account account = accountClient.lookup(Set.of(authUserId)).get(authUserId);
            if (account == null) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND, "This person's sign-in account no longer exists.");
            }
            if (!account.mustChangePassword()) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "This person has already chosen their own password. They can reset it from the sign-in page.");
            }

            Workspace workspace = requireWorkspace(workspaceId);
            String actorName = callerName(caller);
            EmailOutcome outcome = accountClient.issueTemporaryPassword(authUserId, workspace.getName(), actorName, true);
            inTransaction(() -> eventRepository.save(event(WorkspaceMemberEvent.INVITE_RESENT, workspaceId, caller, actorName,
                    membership.getProfile(), account, role, role)));

            return InviteMemberResponse.builder()
                    .member(memberView(membershipId, caller))
                    .accountCreated(false)
                    .credentialsSent(true)
                    .emailStatus(outcome.status())
                    .emailMessage(outcome.message())
                    .inviteExpiresAt(outcome.temporaryPasswordExpiresAt())
                    .build();
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    public Mono<List<MemberActivityResponse>> listActivity(UUID workspaceId, UUID callerAuthUserId, int limit) {
        return Mono.fromCallable(() -> {
            authorizationService.requireAdmin(callerAuthUserId, workspaceId);
            int size = Math.max(1, Math.min(limit, MAX_ACTIVITY));
            return eventRepository.findByWorkspaceIdOrderByCreatedAtDesc(workspaceId, PageRequest.of(0, size)).stream()
                    .map(event -> MemberActivityResponse.builder()
                            .eventId(event.getEventId())
                            .action(event.getAction())
                            .actorName(event.getActorName())
                            .targetName(event.getTargetName())
                            .targetEmail(event.getTargetEmail())
                            .fromRole(event.getFromRole())
                            .toRole(event.getToRole())
                            .createdAt(event.getCreatedAt())
                            .build())
                    .toList();
        }).subscribeOn(Schedulers.boundedElastic());
    }

    /** One member as the list shows them, re-read after a change. */
    private MemberResponse memberView(UUID membershipId, CallerContext caller) {
        WorkspaceMembership membership = membershipRepository.findWithProfileAndRole(membershipId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Membership not found"));
        UUID workspaceId = membership.getWorkspace().getWorkspaceId();
        UUID ownerProfileId = workspaceRepository.findOwnerProfileId(workspaceId).orElse(null);
        Map<UUID, WorkspaceProfile> inviters = new HashMap<>();
        if (membership.getInvitedByProfileId() != null) {
            profileRepository.findById(membership.getInvitedByProfileId())
                    .ifPresent(profile -> inviters.put(profile.getProfileId(), profile));
        }
        return toMember(membership, caller, ownerProfileId, accountOrNull(membership.getProfile().getAuthUserId()),
                inviters, LocalDateTime.now());
    }

    static MemberResponse toMember(WorkspaceMembership membership, CallerContext caller, UUID ownerProfileId, Account account,
                                   Map<UUID, WorkspaceProfile> inviters, LocalDateTime now) {
        WorkspaceProfile profile = membership.getProfile();
        UUID profileId = profile.getProfileId();
        boolean owner = profileId.equals(ownerProfileId);
        String role = owner ? "OWNER" : membership.getRole().getRoleName();
        boolean active = Boolean.TRUE.equals(membership.getIsActive());
        boolean manage = MemberAccess.canManage(caller, profileId, role, ownerProfileId);
        boolean mustChangePassword = account != null && account.mustChangePassword();
        WorkspaceProfile inviter = membership.getInvitedByProfileId() == null ? null : inviters.get(membership.getInvitedByProfileId());

        return MemberResponse.builder()
                .membershipId(membership.getMembershipId())
                .profileId(profileId)
                .authUserId(profile.getAuthUserId())
                .name(memberName(profile, account))
                .firstName(profile.getFirstName())
                .lastName(profile.getLastName())
                .avatarUrl(profile.getAvatarUrl())
                .jobTitle(profile.getJobTitle())
                .email(account == null ? null : account.email())
                .role(role)
                .owner(owner)
                .you(profileId.equals(caller.profileId()))
                .active(active)
                .joinedAt(membership.getJoinedAt())
                .invitedByName(membership.getInvitedByProfileId() == null ? null
                        : inviter == null ? "A former member" : WorkspaceDealServiceImpl.displayName(inviter))
                .accountStatus(account == null ? null : account.status())
                .lastSignInAt(account == null ? null : account.lastLoginAt())
                .inviteStatus(account == null ? null
                        : MemberAccess.inviteStatus(mustChangePassword, account.temporaryPasswordExpiresAt(), now))
                .inviteExpiresAt(mustChangePassword ? account.temporaryPasswordExpiresAt() : null)
                .canChangeRole(manage)
                .canDeactivate(manage)
                .canRemove(manage)
                .canResendInvite(MemberAccess.canResendInvite(manage, active,
                        Boolean.TRUE.equals(membership.getAccountCreated()), mustChangePassword))
                .assignableRoles(manage ? MemberAccess.assignableRoles(caller) : List.of())
                .build();
    }

    /** Profile name, else the account's name, else the email's local part. */
    static String memberName(WorkspaceProfile profile, Account account) {
        String name = WorkspaceDealServiceImpl.displayName(profile);
        if (!"Workspace member".equals(name)) {
            return name;
        }
        if (account != null && !isBlank(account.username())) {
            return account.username().trim();
        }
        if (account != null && account.email() != null && account.email().contains("@")) {
            return account.email().substring(0, account.email().indexOf('@'));
        }
        return name;
    }

    private WorkspaceProfile createProfile(Account account, String firstName, String lastName) {
        WorkspaceProfile profile = profileRepository.save(WorkspaceProfile.builder()
                .authUserId(account.authUserId())
                .firstName(firstName)
                .lastName(lastName == null ? "" : lastName)
                .jobTitle("")
                .dailyUpdateCount(0)
                // Created by an admin: this person works only in workspaces they're added to.
                .managedAccount(account.provisionedBy() != null)
                .build());
        preferencesRepository.save(WorkspacePreferences.builder()
                .profile(profile)
                .theme("dark")
                .language("en")
                .timezone("UTC")
                .build());
        onboardingStateRepository.save(OnboardingState.builder()
                .profile(profile)
                .currentStep("PROFILE_SETUP")
                .isCompleted(false)
                .build());
        return profile;
    }

    private WorkspaceMembership requireMembership(UUID workspaceId, UUID membershipId) {
        return membershipRepository.findWithProfileAndRole(membershipId)
                .filter(membership -> membership.getWorkspace().getWorkspaceId().equals(workspaceId))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Member not found in this workspace"));
    }

    private Workspace requireWorkspace(UUID workspaceId) {
        return workspaceRepository.findById(workspaceId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace not found"));
    }

    private Account accountOrNull(UUID authUserId) {
        try {
            return accountClient.lookup(Set.of(authUserId)).get(authUserId);
        } catch (ResponseStatusException e) {
            log.warn("Sign-in details for {} unavailable: {}", authUserId, e.getReason());
            return null;
        }
    }

    /** The acting admin's name for emails and the activity log; their account's name until they fill in their profile. */
    private String callerName(CallerContext caller) {
        WorkspaceProfile profile = profileRepository.findById(caller.profileId()).orElse(null);
        if (profile == null) {
            return "A workspace admin";
        }
        String name = memberName(profile, accountOrNull(profile.getAuthUserId(), profile));
        return "Workspace member".equals(name) ? "A workspace admin" : name;
    }

    /** Looks the account up only when the profile has no name of its own. */
    private Account accountOrNull(UUID authUserId, WorkspaceProfile profile) {
        boolean named = !"Workspace member".equals(WorkspaceDealServiceImpl.displayName(profile));
        return named ? null : accountOrNull(authUserId);
    }

    private WorkspaceRole findOrCreateRole(String roleName) {
        return roleRepository.findByRoleName(roleName)
                .orElseGet(() -> roleRepository.save(WorkspaceRole.builder()
                        .roleName(roleName)
                        .description("Workspace Role: " + roleName)
                        .build()));
    }

    private static WorkspaceMemberEvent event(String action, UUID workspaceId, CallerContext caller, String actorName,
                                              WorkspaceProfile target, Account targetAccount, String fromRole, String toRole) {
        return WorkspaceMemberEvent.builder()
                .workspaceId(workspaceId)
                .action(action)
                .actorProfileId(caller.profileId())
                .actorName(truncate(actorName, 150))
                .targetProfileId(target.getProfileId())
                .targetName(truncate(memberName(target, targetAccount), 150))
                .targetEmail(truncate(targetAccount == null ? null : targetAccount.email(), 320))
                .fromRole(fromRole)
                .toRole(toRole)
                .build();
    }

    static String fullName(String firstName, String lastName) {
        return lastName == null ? firstName : firstName + " " + lastName;
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static String truncate(String value, int max) {
        return value == null || value.length() <= max ? value : value.substring(0, max);
    }

    private <T> T inTransaction(Supplier<T> work) {
        return new TransactionTemplate(transactionManager).execute(status -> work.get());
    }
}
