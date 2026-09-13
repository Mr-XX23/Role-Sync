package com.role_sync.workspace.services;

import com.role_sync.workspace.dto.AddMemberRequest;
import com.role_sync.workspace.dto.InviteMemberRequest;
import com.role_sync.workspace.dto.InviteMemberResponse;
import com.role_sync.workspace.dto.MemberActivityResponse;
import com.role_sync.workspace.dto.MemberListResponse;
import com.role_sync.workspace.dto.MemberResponse;
import com.role_sync.workspace.dto.UpdateMemberRoleRequest;
import com.role_sync.workspace.dto.WorkspaceMembershipResponse;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.UUID;

/** User Management: a workspace's OWNER and ADMINs manage its members. See {@link MemberAccess}. */
public interface WorkspaceMemberService {

    /** Every member, active or deactivated, with their sign-in details and what the caller may do. */
    Mono<MemberListResponse> listMembers(UUID workspaceId, UUID callerAuthUserId);

    /**
     * Adds someone by email. Without an account they get a verified one and their sign-in details
     * by email; with one they get a notice that they were added.
     */
    Mono<InviteMemberResponse> inviteMember(UUID workspaceId, UUID callerAuthUserId, InviteMemberRequest request);

    /** Adds an existing workspace profile (low-level form of {@link #inviteMember}). */
    Mono<UUID> addMember(UUID workspaceId, UUID callerAuthUserId, AddMemberRequest request);

    Mono<WorkspaceMembershipResponse> updateMemberRole(UUID workspaceId, UUID membershipId, UUID callerAuthUserId,
                                                       UpdateMemberRoleRequest request);

    /** Deactivates (no access, kept in the list) or reactivates a member. */
    Mono<MemberResponse> setMemberActive(UUID workspaceId, UUID membershipId, UUID callerAuthUserId, boolean active);

    Mono<Void> removeMember(UUID workspaceId, UUID membershipId, UUID callerAuthUserId);

    /** Emails new sign-in details to a member who hasn't chosen their own password yet. */
    Mono<InviteMemberResponse> resendInvite(UUID workspaceId, UUID membershipId, UUID callerAuthUserId);

    /** Recent member changes, newest first. */
    Mono<List<MemberActivityResponse>> listActivity(UUID workspaceId, UUID callerAuthUserId, int limit);
}
