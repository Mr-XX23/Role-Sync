package com.role_sync.workspace.services;

import com.role_sync.workspace.models.WorkspaceProfile;
import com.role_sync.workspace.repository.WorkspaceMembershipRepository;
import com.role_sync.workspace.repository.WorkspaceMembershipRepository.ActiveMembershipView;
import com.role_sync.workspace.repository.WorkspaceProfileRepository;
import com.role_sync.workspace.services.WorkspaceAuthorizationService.CallerContext;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.lang.reflect.Proxy;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Offline unit tests for the role-escalation rules — the security-critical part
 * of member management. {@code validateAssignableRole} and the CallerContext
 * checks are pure, so no repositories/DB are needed (repos passed as null).
 */
class WorkspaceAuthorizationServiceTest {

    private final WorkspaceAuthorizationService authz =
            new WorkspaceAuthorizationService(null, null);

    private static CallerContext caller(String role) {
        return new CallerContext(UUID.randomUUID(), role);
    }

    @Test
    void ownerRoleIsRecognized() {
        assertTrue(caller("OWNER").isOwner());
        assertTrue(caller("OWNER").isAdmin());
    }

    @Test
    void adminIsAdminButNotOwner() {
        assertTrue(caller("ADMIN").isAdmin());
        assertFalse(caller("ADMIN").isOwner());
    }

    @Test
    void memberIsNeitherAdminNorOwner() {
        assertFalse(caller("MEMBER").isAdmin());
        assertFalse(caller("MEMBER").isOwner());
    }

    @Test
    void blankOrNullRoleDefaultsToMember() {
        assertEquals("MEMBER", authz.validateAssignableRole(null, caller("OWNER")));
        assertEquals("MEMBER", authz.validateAssignableRole("  ", caller("OWNER")));
    }

    @Test
    void roleNamesAreNormalizedAndAllowed() {
        assertEquals("MEMBER", authz.validateAssignableRole("member", caller("ADMIN")));
        assertEquals("VIEWER", authz.validateAssignableRole(" Viewer ", caller("ADMIN")));
    }

    @Test
    void ownerRoleCannotBeAssignedThroughMemberOps() {
        ResponseStatusException ex = assertThrows(ResponseStatusException.class,
                () -> authz.validateAssignableRole("OWNER", caller("OWNER")));
        assertEquals(HttpStatus.BAD_REQUEST, ex.getStatusCode());
    }

    @Test
    void unknownRoleIsRejected() {
        ResponseStatusException ex = assertThrows(ResponseStatusException.class,
                () -> authz.validateAssignableRole("SUPERUSER", caller("OWNER")));
        assertEquals(HttpStatus.BAD_REQUEST, ex.getStatusCode());
    }

    @Test
    void onlyOwnerMayGrantAdmin() {
        // Owner can grant ADMIN
        assertEquals("ADMIN", authz.validateAssignableRole("ADMIN", caller("OWNER")));
        // A non-owner ADMIN cannot mint more admins
        ResponseStatusException ex = assertThrows(ResponseStatusException.class,
                () -> authz.validateAssignableRole("ADMIN", caller("ADMIN")));
        assertEquals(HttpStatus.FORBIDDEN, ex.getStatusCode());
    }

    // --- membership checks, over repositories that answer one caller ---

    private static final UUID USER = UUID.randomUUID();
    private static final UUID PROFILE = UUID.randomUUID();
    private static final UUID WORKSPACE = UUID.randomUUID();

    private record Membership(String roleName, Boolean workspaceActive) implements ActiveMembershipView {
        @Override
        public String getRoleName() {
            return roleName;
        }

        @Override
        public Boolean getWorkspaceActive() {
            return workspaceActive;
        }
    }

    /** Repositories that know one profile (for USER) and give the membership asked about. */
    private static WorkspaceAuthorizationService authorizationWith(Optional<ActiveMembershipView> membership) {
        WorkspaceProfileRepository profiles = (WorkspaceProfileRepository) Proxy.newProxyInstance(
                WorkspaceProfileRepository.class.getClassLoader(), new Class<?>[]{WorkspaceProfileRepository.class},
                (proxy, method, args) -> "findByAuthUserId".equals(method.getName()) && USER.equals(args[0])
                        ? Optional.of(WorkspaceProfile.builder().profileId(PROFILE).authUserId(USER).build())
                        : Optional.empty());
        WorkspaceMembershipRepository memberships = (WorkspaceMembershipRepository) Proxy.newProxyInstance(
                WorkspaceMembershipRepository.class.getClassLoader(), new Class<?>[]{WorkspaceMembershipRepository.class},
                (proxy, method, args) -> "findActiveMembership".equals(method.getName())
                        && WORKSPACE.equals(args[0]) && PROFILE.equals(args[1]) ? membership : Optional.empty());
        return new WorkspaceAuthorizationService(profiles, memberships);
    }

    @Test
    void anActiveMemberOfAnActiveWorkspaceGetsTheirRole() {
        CallerContext caller = authorizationWith(Optional.of(new Membership(" admin ", true)))
                .requireActiveMembership(USER, WORKSPACE);
        assertEquals(PROFILE, caller.profileId());
        assertEquals("ADMIN", caller.roleName());
        assertTrue(caller.isAdmin());
    }

    @Test
    void membersOfASuspendedWorkspaceAreRefused() {
        WorkspaceAuthorizationService suspended = authorizationWith(Optional.of(new Membership("OWNER", false)));
        ResponseStatusException ex = assertThrows(ResponseStatusException.class,
                () -> suspended.requireActiveMembership(USER, WORKSPACE));
        assertEquals(HttpStatus.FORBIDDEN, ex.getStatusCode());
        assertTrue(ex.getReason().contains("suspended"));
        // Owners and admins too: suspension is decided by the RoleSync team, not the workspace.
        assertThrows(ResponseStatusException.class, () -> suspended.requireAdmin(USER, WORKSPACE));
    }

    @Test
    void someoneWhoIsNotAnActiveMemberIsRefused() {
        ResponseStatusException ex = assertThrows(ResponseStatusException.class,
                () -> authorizationWith(Optional.empty()).requireActiveMembership(USER, WORKSPACE));
        assertEquals(HttpStatus.FORBIDDEN, ex.getStatusCode());
        assertEquals("You are not an active member of this workspace", ex.getReason());
    }

    @Test
    void aCallerWithoutAProfileIsRefused() {
        ResponseStatusException ex = assertThrows(ResponseStatusException.class,
                () -> authorizationWith(Optional.of(new Membership("OWNER", true))).requireActiveMembership(UUID.randomUUID(), WORKSPACE));
        assertEquals(HttpStatus.FORBIDDEN, ex.getStatusCode());
    }
}
