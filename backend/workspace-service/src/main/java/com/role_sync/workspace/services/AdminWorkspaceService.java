package com.role_sync.workspace.services;

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
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.UUID;

/** The Super Admin Console's workspaces, plans, stats and audit trail. Every call requires a platform super admin. */
public interface AdminWorkspaceService {

    Mono<AdminPage<AdminWorkspace>> listWorkspaces(UUID actorUserId, String text, String status, UUID planId, int page, int size);

    Mono<AdminWorkspaceDetail> getWorkspace(UUID actorUserId, UUID workspaceId);

    Mono<AdminWorkspace> setWorkspacePlan(UUID actorUserId, UUID workspaceId, WorkspacePlanRequest request);

    Mono<AdminWorkspace> setWorkspaceStatus(UUID actorUserId, UUID workspaceId, WorkspaceStatusRequest request);

    Mono<List<AdminUserWorkspace>> userWorkspaces(UUID actorUserId, UUID authUserId);

    Mono<List<AdminPlan>> listPlans(UUID actorUserId);

    Mono<AdminPlan> createPlan(UUID actorUserId, PlanInput input);

    Mono<AdminPlan> updatePlan(UUID actorUserId, UUID planId, PlanInput input);

    Mono<AdminPlan> makePlanDefault(UUID actorUserId, UUID planId);

    Mono<AdminPlan> archivePlan(UUID actorUserId, UUID planId);

    Mono<AdminPlan> restorePlan(UUID actorUserId, UUID planId);

    Mono<AdminWorkspaceStats> stats(UUID actorUserId, int days);

    Mono<List<AdminAuditEntry>> audit(UUID actorUserId, int limit);
}
