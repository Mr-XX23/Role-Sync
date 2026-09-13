package com.role_sync.workspace.services;

import com.role_sync.workspace.clients.AuthAccountClient.Account;
import com.role_sync.workspace.dto.MemberResponse;
import com.role_sync.workspace.models.WorkspaceMembership;
import com.role_sync.workspace.models.WorkspaceProfile;
import com.role_sync.workspace.models.WorkspaceRole;
import com.role_sync.workspace.services.WorkspaceAuthorizationService.CallerContext;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** The security-critical member management rules, offline. */
class MemberAccessTest {

    private final UUID ownerProfile = UUID.randomUUID();
    private final CallerContext owner = new CallerContext(ownerProfile, "OWNER");
    private final CallerContext admin = new CallerContext(UUID.randomUUID(), "ADMIN");
    private final CallerContext member = new CallerContext(UUID.randomUUID(), "MEMBER");

    @Test
    void ownersManageEveryoneButThemselves() {
        assertTrue(MemberAccess.canManage(owner, UUID.randomUUID(), "ADMIN", ownerProfile));
        assertTrue(MemberAccess.canManage(owner, UUID.randomUUID(), "VIEWER", ownerProfile));
        assertFalse(MemberAccess.canManage(owner, ownerProfile, "OWNER", ownerProfile));
    }

    @Test
    void adminsManageMembersAndViewersButNotAdminsOrTheOwner() {
        assertTrue(MemberAccess.canManage(admin, UUID.randomUUID(), "MEMBER", ownerProfile));
        assertTrue(MemberAccess.canManage(admin, UUID.randomUUID(), "VIEWER", ownerProfile));
        assertFalse(MemberAccess.canManage(admin, UUID.randomUUID(), "ADMIN", ownerProfile));
        assertFalse(MemberAccess.canManage(admin, ownerProfile, "OWNER", ownerProfile));
        assertFalse(MemberAccess.canManage(admin, admin.profileId(), "ADMIN", ownerProfile));
    }

    @Test
    void theOwnerIsProtectedEvenIfTheirMembershipRowSaysOtherwise() {
        assertFalse(MemberAccess.canManage(owner, UUID.randomUUID(), "OWNER", ownerProfile));
        assertFalse(MemberAccess.canManage(admin, ownerProfile, "MEMBER", ownerProfile));
    }

    @Test
    void membersManageNobody() {
        ResponseStatusException refused = assertThrows(ResponseStatusException.class,
                () -> MemberAccess.requireCanManage(member, UUID.randomUUID(), "VIEWER", ownerProfile));
        assertEquals(HttpStatus.FORBIDDEN, refused.getStatusCode());
        assertEquals(List.of(), MemberAccess.assignableRoles(member));
    }

    @Test
    void onlyTheOwnerCanHandOutTheAdminRole() {
        assertEquals(List.of("ADMIN", "MEMBER", "VIEWER"), MemberAccess.assignableRoles(owner));
        assertEquals(List.of("MEMBER", "VIEWER"), MemberAccess.assignableRoles(admin));
    }

    @Test
    void emailsAreNormalizedAndBadOnesExplained() {
        assertEquals("jane.doe@acme.com", MemberAccess.normalizeEmail("  Jane.Doe@ACME.com "));
        for (String bad : new String[] {null, " ", "jane", "jane@acme", "jane doe@acme.com", "a".repeat(95) + "@acme.com"}) {
            ResponseStatusException refused = assertThrows(ResponseStatusException.class, () -> MemberAccess.normalizeEmail(bad));
            assertEquals(HttpStatus.BAD_REQUEST, refused.getStatusCode(), String.valueOf(bad));
        }
    }

    @Test
    void namesAreCleanedAndLimited() {
        assertEquals("Jane Doe", MemberAccess.cleanName("  Jane \n  Doe <b>", "first name", true));
        assertNull(MemberAccess.cleanName("   ", "last name", false));
        assertThrows(ResponseStatusException.class, () -> MemberAccess.cleanName("", "first name", true));
        assertThrows(ResponseStatusException.class, () -> MemberAccess.cleanName("x".repeat(51), "first name", true));
    }

    @Test
    void invitationsArePendingUntilTheTemporaryPasswordIsReplacedOrExpires() {
        LocalDateTime now = LocalDateTime.of(2026, 9, 13, 12, 0);
        assertEquals("PENDING", MemberAccess.inviteStatus(true, now.plusDays(1), now));
        assertEquals("PENDING", MemberAccess.inviteStatus(true, null, now));
        assertEquals("EXPIRED", MemberAccess.inviteStatus(true, now, now));
        assertNull(MemberAccess.inviteStatus(false, now.minusDays(1), now));
    }

    @Test
    void signInDetailsAreOnlyResentByTheWorkspaceThatSentThem() {
        assertTrue(MemberAccess.canResendInvite(true, true, true, true));
        assertFalse(MemberAccess.canResendInvite(false, true, true, true)); // not allowed to manage them
        assertFalse(MemberAccess.canResendInvite(true, false, true, true)); // deactivated
        assertFalse(MemberAccess.canResendInvite(true, true, false, true)); // another workspace sent them
        assertFalse(MemberAccess.canResendInvite(true, true, true, false)); // they chose their own password
    }

    @Test
    void theMemberListShowsWhatTheCallerMayDo() {
        UUID memberProfile = UUID.randomUUID();
        WorkspaceMembership membership = WorkspaceMembership.builder()
                .membershipId(UUID.randomUUID())
                .profile(WorkspaceProfile.builder().profileId(memberProfile).authUserId(UUID.randomUUID()).firstName("").lastName("").build())
                .role(WorkspaceRole.builder().roleName("MEMBER").build())
                .isActive(true)
                .accountCreated(true)
                .invitedByProfileId(ownerProfile)
                .build();
        LocalDateTime now = LocalDateTime.now();
        Account pending = new Account(membership.getProfile().getAuthUserId(), "sam@acme.com", "Sam", "ACTIVE", true,
                true, now.plusDays(3), null, now, UUID.randomUUID(), null);
        Map<UUID, WorkspaceProfile> inviters = Map.of(ownerProfile,
                WorkspaceProfile.builder().profileId(ownerProfile).firstName("Rohan").lastName("B").build());

        MemberResponse asAdmin = WorkspaceMemberServiceImpl.toMember(membership, admin, ownerProfile, pending, inviters, now);
        assertEquals("Sam", asAdmin.getName()); // no profile name yet: the account's name
        assertEquals("sam@acme.com", asAdmin.getEmail());
        assertEquals("PENDING", asAdmin.getInviteStatus());
        assertEquals("Rohan B", asAdmin.getInvitedByName());
        assertTrue(asAdmin.isCanResendInvite());
        assertTrue(asAdmin.isCanChangeRole());
        assertEquals(List.of("MEMBER", "VIEWER"), asAdmin.getAssignableRoles());

        MemberResponse withoutAccountDetails = WorkspaceMemberServiceImpl.toMember(membership, admin, ownerProfile, null, inviters, now);
        assertNull(withoutAccountDetails.getEmail());
        assertFalse(withoutAccountDetails.isCanResendInvite());

        MemberResponse ownerRow = WorkspaceMemberServiceImpl.toMember(WorkspaceMembership.builder()
                .membershipId(UUID.randomUUID())
                .profile(WorkspaceProfile.builder().profileId(ownerProfile).authUserId(UUID.randomUUID()).firstName("Rohan").build())
                .role(WorkspaceRole.builder().roleName("OWNER").build())
                .isActive(true)
                .build(), admin, ownerProfile, null, inviters, now);
        assertTrue(ownerRow.isOwner());
        assertFalse(ownerRow.isCanRemove());
        assertEquals(List.of(), ownerRow.getAssignableRoles());
    }
}
