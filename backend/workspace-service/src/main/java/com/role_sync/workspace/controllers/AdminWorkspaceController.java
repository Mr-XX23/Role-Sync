package com.role_sync.workspace.controllers;

import com.role_sync.workspace.dto.admin.AdminAuditEntry;
import com.role_sync.workspace.dto.admin.AdminPage;
import com.role_sync.workspace.dto.admin.AdminPlan;
import com.role_sync.workspace.dto.admin.AdminUserWorkspace;
import com.role_sync.workspace.dto.admin.AdminWorkspace;
import com.role_sync.workspace.dto.admin.AdminWorkspaceDetail;
import com.role_sync.workspace.dto.admin.AdminWorkspaceStats;
import com.role_sync.workspace.dto.admin.PlanInput;
import com.role_sync.workspace.dto.admin.WorkspacePlanRequest;
import com.role_sync.workspace.dto.admin.WorkspaceStatusRequest;
import com.role_sync.workspace.services.AdminWorkspaceService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.UUID;

/**
 * The Super Admin Console's workspaces, plans, stats and audit trail. Every call checks with
 * auth-service that the caller (the gateway's verified {@code X-User-Id}) is a platform super admin.
 */
@RestController
@RequestMapping("/api/v1/workspaces/admin")
@RequiredArgsConstructor
public class AdminWorkspaceController {

    private final AdminWorkspaceService admin;

    @GetMapping("/workspaces")
    public Mono<AdminPage<AdminWorkspace>> workspaces(
            @RequestParam(value = "q", required = false) String text,
            @RequestParam(value = "status", required = false) String status,
            @RequestParam(value = "plan_id", required = false) UUID planId,
            @RequestParam(value = "page", defaultValue = "0") int page,
            @RequestParam(value = "size", defaultValue = "25") int size,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        return admin.listWorkspaces(actor(userIdHeader, authUserIdHeader), text, status, planId, page, size);
    }

    @GetMapping("/workspaces/{workspaceId}")
    public Mono<AdminWorkspaceDetail> workspace(
            @PathVariable UUID workspaceId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        return admin.getWorkspace(actor(userIdHeader, authUserIdHeader), workspaceId);
    }

    @PutMapping("/workspaces/{workspaceId}/plan")
    public Mono<AdminWorkspace> setPlan(
            @PathVariable UUID workspaceId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader,
            @RequestBody WorkspacePlanRequest request) {
        return admin.setWorkspacePlan(actor(userIdHeader, authUserIdHeader), workspaceId, request);
    }

    @PutMapping("/workspaces/{workspaceId}/status")
    public Mono<AdminWorkspace> setStatus(
            @PathVariable UUID workspaceId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader,
            @RequestBody WorkspaceStatusRequest request) {
        return admin.setWorkspaceStatus(actor(userIdHeader, authUserIdHeader), workspaceId, request);
    }

    @GetMapping("/users/{authUserId}/workspaces")
    public Mono<List<AdminUserWorkspace>> userWorkspaces(
            @PathVariable UUID authUserId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        return admin.userWorkspaces(actor(userIdHeader, authUserIdHeader), authUserId);
    }

    @GetMapping("/plans")
    public Mono<List<AdminPlan>> plans(
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        return admin.listPlans(actor(userIdHeader, authUserIdHeader));
    }

    @PostMapping("/plans")
    public Mono<ResponseEntity<AdminPlan>> createPlan(
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader,
            @RequestBody PlanInput input) {
        return admin.createPlan(actor(userIdHeader, authUserIdHeader), input)
                .map(plan -> ResponseEntity.status(HttpStatus.CREATED).body(plan));
    }

    @PutMapping("/plans/{planId}")
    public Mono<AdminPlan> updatePlan(
            @PathVariable UUID planId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader,
            @RequestBody PlanInput input) {
        return admin.updatePlan(actor(userIdHeader, authUserIdHeader), planId, input);
    }

    @PostMapping("/plans/{planId}/default")
    public Mono<AdminPlan> makeDefault(
            @PathVariable UUID planId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        return admin.makePlanDefault(actor(userIdHeader, authUserIdHeader), planId);
    }

    @PostMapping("/plans/{planId}/archive")
    public Mono<AdminPlan> archive(
            @PathVariable UUID planId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        return admin.archivePlan(actor(userIdHeader, authUserIdHeader), planId);
    }

    @PostMapping("/plans/{planId}/restore")
    public Mono<AdminPlan> restore(
            @PathVariable UUID planId,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        return admin.restorePlan(actor(userIdHeader, authUserIdHeader), planId);
    }

    @GetMapping("/stats")
    public Mono<AdminWorkspaceStats> stats(
            @RequestParam(value = "days", defaultValue = "30") int days,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        return admin.stats(actor(userIdHeader, authUserIdHeader), days);
    }

    @GetMapping("/audit")
    public Mono<List<AdminAuditEntry>> audit(
            @RequestParam(value = "limit", defaultValue = "100") int limit,
            @RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
            @RequestHeader(value = "X-Auth-User-Id", required = false) String authUserIdHeader) {
        return admin.audit(actor(userIdHeader, authUserIdHeader), limit);
    }

    private static UUID actor(String userIdHeader, String authUserIdHeader) {
        return WorkspaceSupportTicketController.resolveAuthUserId(userIdHeader, authUserIdHeader);
    }
}
