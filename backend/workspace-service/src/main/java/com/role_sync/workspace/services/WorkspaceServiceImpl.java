package com.role_sync.workspace.services;

import com.role_sync.workspace.dto.WorkspaceRequest;
import com.role_sync.workspace.dto.WorkspaceResponse;
import com.role_sync.workspace.models.Workspace;
import com.role_sync.workspace.models.WorkspaceMembership;
import com.role_sync.workspace.models.WorkspaceProfile;
import com.role_sync.workspace.models.WorkspaceRole;
import com.role_sync.workspace.repository.WorkspaceMembershipRepository;
import com.role_sync.workspace.repository.WorkspaceProfileRepository;
import com.role_sync.workspace.repository.WorkspaceRepository;
import com.role_sync.workspace.repository.WorkspaceRoleRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class WorkspaceServiceImpl implements WorkspaceService {

    private final WorkspaceRepository workspaceRepository;
    private final WorkspaceProfileRepository workspaceProfileRepository;
    private final WorkspaceRoleRepository workspaceRoleRepository;
    private final WorkspaceMembershipRepository workspaceMembershipRepository;
    private final WorkspaceAuthorizationService authorizationService;
    private final WorkspaceProfileService workspaceProfileService;
    private final PlatformTransactionManager transactionManager;

    @Override
    @Transactional
    public Mono<WorkspaceResponse> createWorkspace(UUID authUserId, WorkspaceRequest request) {
        return Mono.fromCallable(() -> {
            WorkspaceProfile ownerProfile = workspaceProfileRepository.findByAuthUserId(authUserId)
                    .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace profile not found"));
            if (Boolean.TRUE.equals(ownerProfile.getManagedAccount())) {
                throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                        "Accounts created by a workspace admin can't create their own workspaces.");
            }
            return mapToResponse(createOwnedWorkspace(ownerProfile, request.getName(), request.getDescription()));
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    public Mono<WorkspaceResponse> ensureDefaultWorkspace(UUID authUserId) {
        return workspaceProfileService.getProfile(authUserId) // creates the profile on first use
                .flatMap(profile -> Mono.fromCallable(() -> new TransactionTemplate(transactionManager).execute(status -> {
                    // Two first requests from one user (e.g. two tabs) wait on the profile row, so
                    // the second one finds the workspace the first created.
                    WorkspaceProfile locked = workspaceProfileRepository.lockByProfileId(profile.getProfileId())
                            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace profile not found"));
                    List<Workspace> existing = workspaceMembershipRepository.findActiveWorkspacesByProfileId(locked.getProfileId());
                    if (existing == null || existing.isEmpty()) {
                        existing = workspaceRepository.findByOwnerProfileId(locked.getProfileId());
                    }
                    if (existing != null && !existing.isEmpty()) {
                        WorkspaceResponse response = mapToResponse(existing.get(0));
                        response.setRole(rolesFor(locked.getProfileId()).getOrDefault(response.getWorkspaceId(), "OWNER"));
                        return response;
                    }
                    // Someone a workspace admin added only works where they're a member.
                    if (Boolean.TRUE.equals(locked.getManagedAccount())) {
                        throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                                "You don't have access to any workspace right now. Ask your workspace admin to add you again.");
                    }
                    log.info("Provisioning a default workspace for user {}", authUserId);
                    WorkspaceResponse created = mapToResponse(createOwnedWorkspace(locked,
                            defaultWorkspaceName(locked.getFirstName()),
                            "Default workspace created automatically on first sign-in."));
                    created.setRole("OWNER");
                    return created;
                })).subscribeOn(Schedulers.boundedElastic()));
    }

    private Map<UUID, String> rolesFor(UUID profileId) {
        Map<UUID, String> roles = new HashMap<>();
        for (Object[] row : workspaceMembershipRepository.findActiveRolesByProfileId(profileId)) {
            roles.put((UUID) row[0], (String) row[1]);
        }
        return roles;
    }

    /** Same naming as the account-activation provisioning in {@code AuthEventConsumer}. */
    static String defaultWorkspaceName(String firstName) {
        return firstName != null && !firstName.isBlank() ? firstName.trim() + "'s Workspace" : "Personal Workspace";
    }

    private Workspace createOwnedWorkspace(WorkspaceProfile ownerProfile, String name, String description) {
        Workspace savedWorkspace = workspaceRepository.save(Workspace.builder()
                .name(name)
                .description(description)
                .owner(ownerProfile)
                .isActive(true)
                .build());

        // Fetch or create standard OWNER role
        WorkspaceRole ownerRole = workspaceRoleRepository.findByRoleName("OWNER")
                .orElseGet(() -> workspaceRoleRepository.save(
                        WorkspaceRole.builder()
                                .roleName("OWNER")
                                .description("Workspace Owner")
                                .build()
                ));

        // Create membership record for the owner
        workspaceMembershipRepository.save(WorkspaceMembership.builder()
                .workspace(savedWorkspace)
                .profile(ownerProfile)
                .role(ownerRole)
                .isActive(true)
                .build());
        return savedWorkspace;
    }

    @Override
    @Transactional(readOnly = true)
    public Flux<WorkspaceResponse> getWorkspacesForUser(UUID authUserId) {
        return Mono.fromCallable(() -> {
            WorkspaceProfile profile = workspaceProfileRepository.findByAuthUserId(authUserId)
                    .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace profile not found"));

            List<Workspace> workspaces = workspaceMembershipRepository.findActiveWorkspacesByProfileId(profile.getProfileId());
            Map<UUID, String> roles = rolesFor(profile.getProfileId());

            if (workspaces == null || workspaces.isEmpty()) {
                workspaces = workspaceRepository.findByOwnerProfileId(profile.getProfileId());
                if (workspaces != null) {
                    workspaces.forEach(ws -> roles.putIfAbsent(ws.getWorkspaceId(), "OWNER"));
                }
            }

            if (workspaces == null || workspaces.isEmpty()) {
                return Collections.<WorkspaceResponse>emptyList();
            }

            List<WorkspaceResponse> responseList = new ArrayList<>();
            for (Workspace ws : workspaces) {
                if (ws != null) {
                    WorkspaceResponse response = mapToResponse(ws);
                    response.setRole(roles.get(ws.getWorkspaceId()));
                    responseList.add(response);
                }
            }
            return responseList;
        })
        .subscribeOn(Schedulers.boundedElastic())
        .flatMapMany(Flux::fromIterable);
    }

    @Override
    @Transactional
    public Mono<WorkspaceResponse> updateWorkspace(UUID workspaceId, UUID authUserId, WorkspaceRequest request) {
        return Mono.fromCallable(() -> {
            // AuthZ: caller must be an OWNER/ADMIN of this workspace.
            authorizationService.requireAdmin(authUserId, workspaceId);

            Workspace workspace = workspaceRepository.findById(workspaceId)
                    .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace not found"));

            if (request.getName() != null && !request.getName().isBlank()) {
                workspace.setName(request.getName());
            }
            if (request.getDescription() != null) {
                workspace.setDescription(request.getDescription());
            }

            Workspace saved = workspaceRepository.save(workspace);
            return mapToResponse(saved);
        }).subscribeOn(Schedulers.boundedElastic());
    }

    private WorkspaceResponse mapToResponse(Workspace ws) {
        if (ws == null) return null;
        return WorkspaceResponse.builder()
                .workspaceId(ws.getWorkspaceId())
                .name(ws.getName())
                .description(ws.getDescription())
                .isActive(ws.getIsActive())
                .createdAt(ws.getCreatedAt())
                .updatedAt(ws.getUpdatedAt())
                .build();
    }
}
