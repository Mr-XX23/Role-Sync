package com.role_sync.workspace.controllers;

import com.role_sync.workspace.dto.AddMemberRequest;
import com.role_sync.workspace.dto.InviteMemberRequest;
import com.role_sync.workspace.dto.InviteMemberResponse;
import com.role_sync.workspace.dto.MemberActivityResponse;
import com.role_sync.workspace.dto.MemberListResponse;
import com.role_sync.workspace.dto.MemberResponse;
import com.role_sync.workspace.dto.MemberStatusRequest;
import com.role_sync.workspace.dto.UpdateMemberRoleRequest;
import com.role_sync.workspace.dto.WorkspaceMembershipResponse;
import com.role_sync.workspace.services.WorkspaceMemberService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * User Management: a workspace's OWNER and ADMINs add people (creating verified accounts that
 * receive their sign-in details by email), change roles, deactivate, remove, and review activity.
 */
@RestController
@RequestMapping("/api/v1/workspaces")
@RequiredArgsConstructor
public class WorkspaceMemberController {

    private final WorkspaceMemberService memberService;

    @GetMapping("/{workspaceId}/members")
    public Mono<MemberListResponse> listMembers(
            @PathVariable UUID workspaceId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        UUID callerAuthUserId = resolveAuthUserId(userIdHeader, authUserIdHeader);
        return memberService.listMembers(workspaceId, callerAuthUserId);
    }

    /** Adds someone by email, creating their account if they don't have one. */
    @PostMapping("/{workspaceId}/members/invite")
    public Mono<ResponseEntity<InviteMemberResponse>> inviteMember(
            @PathVariable UUID workspaceId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader,
            @RequestBody InviteMemberRequest request) {
        UUID callerAuthUserId = resolveAuthUserId(userIdHeader, authUserIdHeader);
        return memberService.inviteMember(workspaceId, callerAuthUserId, request)
                .map(response -> ResponseEntity.status(HttpStatus.CREATED).body(response));
    }

    @PostMapping("/{workspaceId}/members")
    public Mono<ResponseEntity<Map<String, Object>>> addMember(
            @PathVariable UUID workspaceId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader,
            @Valid @RequestBody AddMemberRequest request) {
        UUID callerAuthUserId = resolveAuthUserId(userIdHeader, authUserIdHeader);
        return memberService.addMember(workspaceId, callerAuthUserId, request)
                .map(membershipId -> ResponseEntity.status(HttpStatus.CREATED)
                        .body(Map.of(
                                "membership_id", membershipId,
                                "message", "Member added to workspace successfully"
                        )));
    }

    @PutMapping("/{workspaceId}/members/{membershipId}/role")
    public Mono<ResponseEntity<WorkspaceMembershipResponse>> updateMemberRole(
            @PathVariable UUID workspaceId,
            @PathVariable UUID membershipId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader,
            @Valid @RequestBody UpdateMemberRoleRequest request) {
        UUID callerAuthUserId = resolveAuthUserId(userIdHeader, authUserIdHeader);
        return memberService.updateMemberRole(workspaceId, membershipId, callerAuthUserId, request)
                .map(ResponseEntity::ok);
    }

    /** {"active": false} deactivates the member; {"active": true} restores their access. */
    @PutMapping("/{workspaceId}/members/{membershipId}/status")
    public Mono<MemberResponse> setMemberStatus(
            @PathVariable UUID workspaceId,
            @PathVariable UUID membershipId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader,
            @Valid @RequestBody MemberStatusRequest request) {
        UUID callerAuthUserId = resolveAuthUserId(userIdHeader, authUserIdHeader);
        return memberService.setMemberActive(workspaceId, membershipId, callerAuthUserId, request.getActive());
    }

    @DeleteMapping("/{workspaceId}/members/{membershipId}")
    public Mono<ResponseEntity<Void>> removeMember(
            @PathVariable UUID workspaceId,
            @PathVariable UUID membershipId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        UUID callerAuthUserId = resolveAuthUserId(userIdHeader, authUserIdHeader);
        return memberService.removeMember(workspaceId, membershipId, callerAuthUserId)
                .then(Mono.just(ResponseEntity.noContent().<Void>build()));
    }

    @PostMapping("/{workspaceId}/members/{membershipId}/resend-invite")
    public Mono<InviteMemberResponse> resendInvite(
            @PathVariable UUID workspaceId,
            @PathVariable UUID membershipId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        UUID callerAuthUserId = resolveAuthUserId(userIdHeader, authUserIdHeader);
        return memberService.resendInvite(workspaceId, membershipId, callerAuthUserId);
    }

    @GetMapping("/{workspaceId}/members/activity")
    public Mono<List<MemberActivityResponse>> listActivity(
            @PathVariable UUID workspaceId,
            @RequestParam(value = "limit", defaultValue = "50") int limit,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        UUID callerAuthUserId = resolveAuthUserId(userIdHeader, authUserIdHeader);
        return memberService.listActivity(workspaceId, callerAuthUserId, limit);
    }

    private UUID resolveAuthUserId(String userIdHeader, String authUserIdHeader) {
        String idStr = userIdHeader != null ? userIdHeader : authUserIdHeader;
        if (idStr == null || idStr.isBlank()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,
                    "Missing user identification header (X-User-Id or X-Auth-User-Id)");
        }
        try {
            return UUID.fromString(idStr);
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Invalid UUID format in user identification header");
        }
    }
}
