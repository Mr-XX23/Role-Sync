package com.role_sync.workspace.services;

import com.role_sync.workspace.clients.AuthAccountClient;
import com.role_sync.workspace.dto.admin.AdminAuditEntry;
import com.role_sync.workspace.dto.admin.AdminDailyCount;
import com.role_sync.workspace.dto.admin.AdminMemberEvent;
import com.role_sync.workspace.dto.admin.AdminPage;
import com.role_sync.workspace.dto.admin.AdminPlan;
import com.role_sync.workspace.dto.admin.AdminPlanRef;
import com.role_sync.workspace.dto.admin.AdminUserWorkspace;
import com.role_sync.workspace.dto.admin.AdminWorkspace;
import com.role_sync.workspace.dto.admin.AdminWorkspaceDetail;
import com.role_sync.workspace.dto.admin.AdminWorkspaceMember;
import com.role_sync.workspace.dto.admin.AdminWorkspaceStats;
import com.role_sync.workspace.dto.admin.PlanInput;
import com.role_sync.workspace.dto.admin.WorkspacePlanRequest;
import com.role_sync.workspace.dto.admin.WorkspaceStatusRequest;
import com.role_sync.workspace.models.PlatformAdminEvent;
import com.role_sync.workspace.models.PlatformPlan;
import com.role_sync.workspace.models.Workspace;
import com.role_sync.workspace.models.WorkspaceMembership;
import com.role_sync.workspace.models.WorkspaceProfile;
import com.role_sync.workspace.repository.AdminWorkspaceSearch;
import com.role_sync.workspace.repository.PlatformAdminEventRepository;
import com.role_sync.workspace.repository.PlatformPlanRepository;
import com.role_sync.workspace.repository.WorkspaceContextRepository;
import com.role_sync.workspace.repository.WorkspaceDealRepository;
import com.role_sync.workspace.repository.WorkspaceMemberEventRepository;
import com.role_sync.workspace.repository.WorkspaceMembershipRepository;
import com.role_sync.workspace.repository.WorkspaceNoteRepository;
import com.role_sync.workspace.repository.WorkspaceProfileRepository;
import com.role_sync.workspace.repository.WorkspaceRepository;
import com.role_sync.workspace.services.PlatformAdminGuard.Actor;
import com.role_sync.workspace.utils.SanitizationUtils;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.function.Function;
import java.util.function.Supplier;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Slf4j
public class AdminWorkspaceServiceImpl implements AdminWorkspaceService {

    private static final int MAX_PAGE_SIZE = 100;
    private static final int MAX_AUDIT = 200;
    private static final int MAX_DAYS = 365;
    private static final int RECENT_MEMBER_EVENTS = 20;
    private static final List<String> CLOSED_DEAL_STAGES = List.of("WON", "LOST");

    private final WorkspaceRepository workspaces;
    private final WorkspaceMembershipRepository memberships;
    private final WorkspaceProfileRepository profiles;
    private final WorkspaceDealRepository deals;
    private final WorkspaceContextRepository contexts;
    private final WorkspaceNoteRepository notes;
    private final WorkspaceMemberEventRepository memberEvents;
    private final PlatformPlanRepository plans;
    private final PlatformAdminEventRepository events;
    private final AdminWorkspaceSearch search;
    private final PlatformAdminGuard adminGuard;
    private final AuthAccountClient accounts;
    private final PlatformTransactionManager transactionManager;

    // ------------------------------------------------------------------ workspaces

    @Override
    public Mono<AdminPage<AdminWorkspace>> listWorkspaces(UUID actorUserId, String text, String status, UUID planId,
                                                          int page, int size) {
        return blocking(() -> {
            adminGuard.requireSuperAdmin(actorUserId);
            Boolean active = parseStatus(status);
            int safePage = Math.max(0, page);
            int safeSize = Math.max(1, Math.min(size, MAX_PAGE_SIZE));
            return inTransaction(() -> {
                List<PlatformPlan> allPlans = plans.findAll();
                PlatformPlan defaultPlan = defaultOf(allPlans);
                boolean includeUnassigned = planId != null && defaultPlan != null && planId.equals(defaultPlan.getPlanId());
                AdminWorkspaceSearch.Result result = search.search(
                        new AdminWorkspaceSearch.Criteria(text, active, planId, includeUnassigned), safePage, safeSize);
                return AdminPage.of(toAdminWorkspaces(result.workspaces(), allPlans), safePage, safeSize, result.total());
            });
        });
    }

    @Override
    public Mono<AdminWorkspaceDetail> getWorkspace(UUID actorUserId, UUID workspaceId) {
        return blocking(() -> {
            adminGuard.requireSuperAdmin(actorUserId);
            return inTransaction(() -> {
                Workspace workspace = requireWorkspace(workspaceId);
                List<WorkspaceMembership> rows = memberships.findMembersOfWorkspace(workspaceId);
                Map<UUID, AuthAccountClient.Account> accountsById = lookupAccounts(
                        rows.stream().map(m -> m.getProfile().getAuthUserId()).toList());
                List<AdminWorkspaceMember> members = rows.stream()
                        .map(m -> AdminWorkspaceMember.builder()
                                .membershipId(m.getMembershipId())
                                .profileId(m.getProfile().getProfileId())
                                .authUserId(m.getProfile().getAuthUserId())
                                .name(SupportTicketServiceImpl.displayName(m.getProfile()))
                                .email(emailOf(accountsById, m.getProfile().getAuthUserId()))
                                .role(m.getRole().getRoleName())
                                .active(!Boolean.FALSE.equals(m.getIsActive()))
                                .joinedAt(toInstant(m.getJoinedAt()))
                                .build())
                        .toList();
                List<AdminMemberEvent> recent = memberEvents
                        .findByWorkspaceIdOrderByCreatedAtDesc(workspaceId, PageRequest.of(0, RECENT_MEMBER_EVENTS))
                        .stream()
                        .map(e -> AdminMemberEvent.builder()
                                .eventId(e.getEventId())
                                .action(e.getAction())
                                .actorName(e.getActorName())
                                .targetName(e.getTargetName())
                                .targetEmail(e.getTargetEmail())
                                .fromRole(e.getFromRole())
                                .toRole(e.getToRole())
                                .createdAt(toInstant(e.getCreatedAt()))
                                .build())
                        .toList();
                return AdminWorkspaceDetail.builder()
                        .workspace(toAdminWorkspaces(List.of(workspace), plans.findAll()).get(0))
                        .members(members)
                        .counts(AdminWorkspaceDetail.Counts.builder()
                                .deals(deals.countByWorkspaceWorkspaceId(workspaceId))
                                .openDeals(deals.countOpenInWorkspace(workspaceId, CLOSED_DEAL_STAGES))
                                .contexts(contexts.countByWorkspaceWorkspaceId(workspaceId))
                                .notes(notes.countByWorkspaceWorkspaceId(workspaceId))
                                .build())
                        .recentMemberEvents(recent)
                        .build();
            });
        });
    }

    @Override
    public Mono<AdminWorkspace> setWorkspacePlan(UUID actorUserId, UUID workspaceId, WorkspacePlanRequest request) {
        return blocking(() -> {
            Actor actor = adminGuard.requireSuperAdmin(actorUserId);
            if (request == null || !request.isPlanIdSent()) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                        "plan_id is required (null puts the workspace on the default plan)");
            }
            UUID wanted = request.getPlanId();
            return inTransaction(() -> {
                Workspace locked = workspaces.lockById(workspaceId)
                        .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace not found"));
                UUID previous = locked.getPlanId();
                List<PlatformPlan> allPlans = plans.findAll();
                if (wanted != null) {
                    PlanRules.requireAssignable(find(allPlans, wanted), previous);
                }
                if (!Objects.equals(previous, wanted)) {
                    String from = planLabel(previous, allPlans);
                    locked.setPlanId(wanted);
                    workspaces.saveAndFlush(locked);
                    record(actor, PlatformAdminEvent.WORKSPACE_PLAN_CHANGED, PlatformAdminEvent.TARGET_WORKSPACE,
                            workspaceId.toString(), locked.getName(),
                            "Moved workspace \"" + locked.getName() + "\" from " + from + " to " + planLabel(wanted, allPlans));
                    log.info("Super admin {} changed the plan of workspace {} from {} to {}", actorUserId, workspaceId, previous, wanted);
                }
                return toAdminWorkspaces(List.of(requireWorkspace(workspaceId)), allPlans).get(0);
            });
        });
    }

    @Override
    public Mono<AdminWorkspace> setWorkspaceStatus(UUID actorUserId, UUID workspaceId, WorkspaceStatusRequest request) {
        return blocking(() -> {
            Actor actor = adminGuard.requireSuperAdmin(actorUserId);
            if (request == null || request.getActive() == null) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "active is required");
            }
            String cleaned = SanitizationUtils.sanitizeText(request.getReason());
            String reason = cleaned == null || cleaned.isBlank() ? null : cleaned;
            if (reason != null && reason.length() > 500) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "reason can be at most 500 characters");
            }
            boolean active = request.getActive();
            return inTransaction(() -> {
                Workspace locked = workspaces.lockById(workspaceId)
                        .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace not found"));
                boolean currentlyActive = !Boolean.FALSE.equals(locked.getIsActive());
                if (currentlyActive != active) {
                    locked.setIsActive(active);
                    workspaces.saveAndFlush(locked);
                    record(actor, active ? PlatformAdminEvent.WORKSPACE_REACTIVATED : PlatformAdminEvent.WORKSPACE_SUSPENDED,
                            PlatformAdminEvent.TARGET_WORKSPACE, workspaceId.toString(), locked.getName(),
                            (active ? "Reactivated" : "Suspended") + " workspace \"" + locked.getName() + "\""
                                    + (reason == null ? "" : ": " + reason));
                    log.info("Super admin {} {} workspace {}", actorUserId, active ? "reactivated" : "suspended", workspaceId);
                }
                return toAdminWorkspaces(List.of(requireWorkspace(workspaceId)), plans.findAll()).get(0);
            });
        });
    }

    @Override
    public Mono<List<AdminUserWorkspace>> userWorkspaces(UUID actorUserId, UUID authUserId) {
        return blocking(() -> {
            adminGuard.requireSuperAdmin(actorUserId);
            return inTransaction(() -> {
                WorkspaceProfile profile = profiles.findByAuthUserId(authUserId).orElse(null);
                if (profile == null) {
                    return List.<AdminUserWorkspace>of();
                }
                UUID profileId = profile.getProfileId();
                Set<UUID> owned = workspaces.findByOwnerProfileId(profileId).stream()
                        .map(Workspace::getWorkspaceId).collect(Collectors.toSet());
                List<AdminUserWorkspace> result = new ArrayList<>();
                Set<UUID> seen = new HashSet<>();
                for (WorkspaceMembership m : memberships.findAllOfProfile(profileId)) {
                    Workspace w = m.getWorkspace();
                    seen.add(w.getWorkspaceId());
                    result.add(AdminUserWorkspace.builder()
                            .workspaceId(w.getWorkspaceId())
                            .name(w.getName())
                            .active(!Boolean.FALSE.equals(w.getIsActive()))
                            .role(m.getRole().getRoleName())
                            .membershipActive(!Boolean.FALSE.equals(m.getIsActive()))
                            .owner(owned.contains(w.getWorkspaceId()))
                            .joinedAt(toInstant(m.getJoinedAt()))
                            .build());
                }
                for (Workspace w : workspaces.findByOwnerProfileId(profileId)) {
                    if (seen.add(w.getWorkspaceId())) {
                        result.add(AdminUserWorkspace.builder()
                                .workspaceId(w.getWorkspaceId())
                                .name(w.getName())
                                .active(!Boolean.FALSE.equals(w.getIsActive()))
                                .role("OWNER")
                                .membershipActive(false)
                                .owner(true)
                                .joinedAt(toInstant(w.getCreatedAt()))
                                .build());
                    }
                }
                return result;
            });
        });
    }

    // ------------------------------------------------------------------ plans

    @Override
    public Mono<List<AdminPlan>> listPlans(UUID actorUserId) {
        return blocking(() -> {
            adminGuard.requireSuperAdmin(actorUserId);
            return inTransaction(() -> {
                List<PlatformPlan> allPlans = sorted(plans.findAll());
                Map<UUID, Long> counts = effectiveCounts(allPlans);
                return allPlans.stream().map(p -> toAdminPlan(p, counts)).toList();
            });
        });
    }

    @Override
    public Mono<AdminPlan> createPlan(UUID actorUserId, PlanInput input) {
        return blocking(() -> {
            Actor actor = adminGuard.requireSuperAdmin(actorUserId);
            PlatformPlan plan = new PlatformPlan();
            PlanRules.apply(input, plan);
            return inTransaction(() -> {
                List<PlatformPlan> locked = plans.lockAll();
                requireUniqueCode(locked, plan.getCode(), null);
                // The first plan becomes the default, so there is always one.
                plan.setIsDefault(defaultOf(locked) == null);
                plan.setIsArchived(false);
                PlatformPlan saved = plans.saveAndFlush(plan);
                record(actor, PlatformAdminEvent.PLAN_CREATED, PlatformAdminEvent.TARGET_PLAN, saved.getPlanId().toString(),
                        saved.getName(), "Created plan \"" + saved.getName() + "\" (" + saved.getCode() + ")");
                return planView(saved.getPlanId());
            });
        });
    }

    @Override
    public Mono<AdminPlan> updatePlan(UUID actorUserId, UUID planId, PlanInput input) {
        return blocking(() -> {
            Actor actor = adminGuard.requireSuperAdmin(actorUserId);
            PlatformPlan checked = new PlatformPlan();
            PlanRules.apply(input, checked);
            return inTransaction(() -> {
                List<PlatformPlan> locked = plans.lockAll();
                PlatformPlan plan = find(locked, planId);
                requireUniqueCode(locked, checked.getCode(), planId);
                PlanRules.apply(input, plan);
                PlatformPlan saved = plans.saveAndFlush(plan);
                record(actor, PlatformAdminEvent.PLAN_UPDATED, PlatformAdminEvent.TARGET_PLAN, planId.toString(),
                        saved.getName(), "Updated plan \"" + saved.getName() + "\" (" + saved.getCode() + ")");
                return planView(planId);
            });
        });
    }

    @Override
    public Mono<AdminPlan> makePlanDefault(UUID actorUserId, UUID planId) {
        return blocking(() -> {
            Actor actor = adminGuard.requireSuperAdmin(actorUserId);
            return inTransaction(() -> {
                List<PlatformPlan> locked = plans.lockAll();
                PlatformPlan plan = find(locked, planId);
                if (Boolean.TRUE.equals(plan.getIsDefault())) {
                    return planView(planId);
                }
                PlanRules.requireCanBeDefault(plan);
                PlatformPlan previous = defaultOf(locked);
                for (PlatformPlan other : locked) {
                    if (Boolean.TRUE.equals(other.getIsDefault())) {
                        other.setIsDefault(false);
                        plans.save(other);
                    }
                }
                plan.setIsDefault(true);
                plans.saveAndFlush(plan);
                record(actor, PlatformAdminEvent.PLAN_MADE_DEFAULT, PlatformAdminEvent.TARGET_PLAN, planId.toString(),
                        plan.getName(), "Made \"" + plan.getName() + "\" the default plan"
                                + (previous == null ? "" : " (was \"" + previous.getName() + "\")"));
                return planView(planId);
            });
        });
    }

    @Override
    public Mono<AdminPlan> archivePlan(UUID actorUserId, UUID planId) {
        return setArchived(actorUserId, planId, true);
    }

    @Override
    public Mono<AdminPlan> restorePlan(UUID actorUserId, UUID planId) {
        return setArchived(actorUserId, planId, false);
    }

    private Mono<AdminPlan> setArchived(UUID actorUserId, UUID planId, boolean archived) {
        return blocking(() -> {
            Actor actor = adminGuard.requireSuperAdmin(actorUserId);
            return inTransaction(() -> {
                PlatformPlan plan = find(plans.lockAll(), planId);
                if (Boolean.TRUE.equals(plan.getIsArchived()) == archived) {
                    return planView(planId);
                }
                if (archived) {
                    PlanRules.requireArchivable(plan);
                }
                plan.setIsArchived(archived);
                plans.saveAndFlush(plan);
                record(actor, archived ? PlatformAdminEvent.PLAN_ARCHIVED : PlatformAdminEvent.PLAN_RESTORED,
                        PlatformAdminEvent.TARGET_PLAN, planId.toString(), plan.getName(),
                        (archived ? "Archived" : "Restored") + " plan \"" + plan.getName() + "\"");
                return planView(planId);
            });
        });
    }

    // ------------------------------------------------------------------ stats and audit

    @Override
    public Mono<AdminWorkspaceStats> stats(UUID actorUserId, int days) {
        return blocking(() -> {
            adminGuard.requireSuperAdmin(actorUserId);
            int range = Math.max(1, Math.min(days, MAX_DAYS));
            return inTransaction(() -> {
                long active = workspaces.countByIsActive(true);
                long suspended = workspaces.countByIsActive(false);
                LocalDate today = LocalDate.now(ZoneOffset.UTC);
                LocalDate first = today.minusDays(range - 1L);
                Map<LocalDate, Long> perDay = new LinkedHashMap<>();
                for (LocalDate day = first; !day.isAfter(today); day = day.plusDays(1)) {
                    perDay.put(day, 0L);
                }
                LocalDateTime since = first.atStartOfDay(ZoneOffset.UTC)
                        .withZoneSameInstant(ZoneId.systemDefault()).toLocalDateTime();
                for (LocalDateTime createdAt : workspaces.findCreatedAtSince(since)) {
                    LocalDate day = createdAt.atZone(ZoneId.systemDefault()).withZoneSameInstant(ZoneOffset.UTC).toLocalDate();
                    perDay.computeIfPresent(day, (d, n) -> n + 1);
                }
                List<PlatformPlan> allPlans = sorted(plans.findAll());
                Map<UUID, Long> counts = effectiveCounts(allPlans);
                return AdminWorkspaceStats.builder()
                        .workspacesTotal(active + suspended)
                        .workspacesActive(active)
                        .workspacesSuspended(suspended)
                        .profilesTotal(profiles.count())
                        .membershipsActive(memberships.countAllActive())
                        .newWorkspacesDaily(perDay.entrySet().stream()
                                .map(e -> new AdminDailyCount(e.getKey(), e.getValue())).toList())
                        .planDistribution(allPlans.stream()
                                .map(p -> AdminWorkspaceStats.PlanShare.builder()
                                        .planId(p.getPlanId())
                                        .code(p.getCode())
                                        .name(p.getName())
                                        .workspaceCount(counts.getOrDefault(p.getPlanId(), 0L))
                                        .build())
                                .toList())
                        .dealsTotal(deals.count())
                        .dealsOpen(deals.countOpen(CLOSED_DEAL_STAGES))
                        .build();
            });
        });
    }

    @Override
    public Mono<List<AdminAuditEntry>> audit(UUID actorUserId, int limit) {
        return blocking(() -> {
            adminGuard.requireSuperAdmin(actorUserId);
            int safeLimit = Math.max(1, Math.min(limit, MAX_AUDIT));
            return inTransaction(() -> events.findRecent(PageRequest.of(0, safeLimit)).stream()
                    .map(e -> AdminAuditEntry.builder()
                            .id(e.getEventId())
                            .service("workspace")
                            .actorUserId(e.getActorUserId())
                            .actorEmail(e.getActorEmail())
                            .action(e.getAction())
                            .targetType(e.getTargetType())
                            .targetId(e.getTargetId())
                            .targetLabel(e.getTargetLabel())
                            .summary(e.getSummary())
                            .createdAt(toInstant(e.getCreatedAt()))
                            .build())
                    .toList());
        });
    }

    // ------------------------------------------------------------------ helpers

    private static <T> Mono<T> blocking(Callable<T> work) {
        return Mono.fromCallable(work).subscribeOn(Schedulers.boundedElastic());
    }

    private <T> T inTransaction(Supplier<T> work) {
        return new TransactionTemplate(transactionManager).execute(status -> work.get());
    }

    private Workspace requireWorkspace(UUID workspaceId) {
        return workspaces.findWithOwner(workspaceId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace not found"));
    }

    private static PlatformPlan find(List<PlatformPlan> all, UUID planId) {
        return all.stream().filter(p -> p.getPlanId().equals(planId)).findFirst()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Plan not found"));
    }

    private static void requireUniqueCode(List<PlatformPlan> all, String code, UUID exceptPlanId) {
        if (all.stream().anyMatch(p -> p.getCode().equalsIgnoreCase(code) && !p.getPlanId().equals(exceptPlanId))) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Another plan already uses the code " + code);
        }
    }

    /** "active" / "suspended" / empty for both. */
    static Boolean parseStatus(String status) {
        if (status == null || status.isBlank()) {
            return null;
        }
        return switch (status.trim().toLowerCase(Locale.ROOT)) {
            case "active" -> true;
            case "suspended" -> false;
            default -> throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "status must be active or suspended");
        };
    }

    private static PlatformPlan defaultOf(Collection<PlatformPlan> all) {
        return all.stream().filter(p -> Boolean.TRUE.equals(p.getIsDefault())).findFirst().orElse(null);
    }

    private static List<PlatformPlan> sorted(List<PlatformPlan> all) {
        return all.stream()
                .sorted(Comparator.comparing((PlatformPlan p) -> p.getSortOrder() == null ? 0 : p.getSortOrder())
                        .thenComparing(PlatformPlan::getName, String.CASE_INSENSITIVE_ORDER))
                .toList();
    }

    /** Workspaces effectively on each plan: unassigned ones (and ones on a missing plan) count for the default plan. */
    private Map<UUID, Long> effectiveCounts(List<PlatformPlan> allPlans) {
        Set<UUID> known = allPlans.stream().map(PlatformPlan::getPlanId).collect(Collectors.toSet());
        PlatformPlan defaultPlan = defaultOf(allPlans);
        Map<UUID, Long> counts = new HashMap<>();
        for (Object[] row : workspaces.countByPlanId()) {
            UUID planId = (UUID) row[0];
            long count = ((Number) row[1]).longValue();
            UUID effective = planId != null && known.contains(planId) ? planId
                    : defaultPlan == null ? null : defaultPlan.getPlanId();
            if (effective != null) {
                counts.merge(effective, count, Long::sum);
            }
        }
        return counts;
    }

    private AdminPlan planView(UUID planId) {
        List<PlatformPlan> allPlans = plans.findAll();
        return toAdminPlan(find(allPlans, planId), effectiveCounts(allPlans));
    }

    private static AdminPlan toAdminPlan(PlatformPlan p, Map<UUID, Long> counts) {
        return AdminPlan.builder()
                .planId(p.getPlanId())
                .code(p.getCode())
                .name(p.getName())
                .description(p.getDescription())
                .priceMonthlyCents(p.getPriceMonthlyCents())
                .currency(p.getCurrency())
                .maxMembers(p.getMaxMembers())
                .agentTokensPerDay(p.getAgentTokensPerDay())
                .maxConcurrentAgentRuns(p.getMaxConcurrentAgentRuns())
                .defaultPlan(Boolean.TRUE.equals(p.getIsDefault()))
                .archived(Boolean.TRUE.equals(p.getIsArchived()))
                .sortOrder(p.getSortOrder() == null ? 0 : p.getSortOrder())
                .workspaceCount(counts.getOrDefault(p.getPlanId(), 0L))
                .createdAt(toInstant(p.getCreatedAt()))
                .updatedAt(toInstant(p.getUpdatedAt()))
                .build();
    }

    private static String planLabel(UUID planId, List<PlatformPlan> allPlans) {
        if (planId == null) {
            PlatformPlan defaultPlan = defaultOf(allPlans);
            return "the default plan" + (defaultPlan == null ? "" : " (" + defaultPlan.getName() + ")");
        }
        return allPlans.stream().filter(p -> p.getPlanId().equals(planId)).findFirst()
                .map(p -> "\"" + p.getName() + "\"").orElse("an unknown plan");
    }

    /** Workspaces (owners loaded) as the console lists them: owner email, active member count and effective plan. */
    private List<AdminWorkspace> toAdminWorkspaces(List<Workspace> rows, List<PlatformPlan> allPlans) {
        if (rows.isEmpty()) {
            return List.of();
        }
        Map<UUID, PlatformPlan> plansById = allPlans.stream()
                .collect(Collectors.toMap(PlatformPlan::getPlanId, Function.identity()));
        PlatformPlan defaultPlan = defaultOf(allPlans);
        Map<UUID, Long> memberCounts = new HashMap<>();
        for (Object[] row : memberships.countActiveMembersByWorkspace(rows.stream().map(Workspace::getWorkspaceId).toList())) {
            memberCounts.put((UUID) row[0], ((Number) row[1]).longValue());
        }
        Map<UUID, AuthAccountClient.Account> accountsById = lookupAccounts(rows.stream()
                .map(w -> w.getOwner() == null ? null : w.getOwner().getAuthUserId()).toList());
        return rows.stream().map(w -> {
            WorkspaceProfile owner = w.getOwner();
            PlatformPlan assigned = w.getPlanId() == null ? null : plansById.get(w.getPlanId());
            PlatformPlan effective = assigned != null ? assigned : defaultPlan;
            return AdminWorkspace.builder()
                    .workspaceId(w.getWorkspaceId())
                    .name(w.getName())
                    .description(w.getDescription())
                    .active(!Boolean.FALSE.equals(w.getIsActive()))
                    .createdAt(toInstant(w.getCreatedAt()))
                    .updatedAt(toInstant(w.getUpdatedAt()))
                    .owner(owner == null ? null : AdminWorkspace.Owner.builder()
                            .profileId(owner.getProfileId())
                            .authUserId(owner.getAuthUserId())
                            .name(SupportTicketServiceImpl.displayName(owner))
                            .email(emailOf(accountsById, owner.getAuthUserId()))
                            .build())
                    .memberCount(memberCounts.getOrDefault(w.getWorkspaceId(), 0L))
                    .plan(effective == null ? null : AdminPlanRef.builder()
                            .planId(effective.getPlanId())
                            .code(effective.getCode())
                            .name(effective.getName())
                            .defaultPlan(Boolean.TRUE.equals(effective.getIsDefault()))
                            .build())
                    .planAssigned(assigned != null)
                    .build();
        }).toList();
    }

    private void record(Actor actor, String action, String targetType, String targetId, String targetLabel, String summary) {
        events.save(PlatformAdminEvent.builder()
                .actorUserId(actor.authUserId())
                .actorEmail(actor.email())
                .action(action)
                .targetType(targetType)
                .targetId(targetId)
                .targetLabel(truncate(targetLabel, 200))
                .summary(truncate(summary, 500))
                .build());
    }

    /** Emails from auth-service; none when it can't be asked (the console shows the rest anyway). */
    private Map<UUID, AuthAccountClient.Account> lookupAccounts(Collection<UUID> authUserIds) {
        Set<UUID> ids = new HashSet<>(authUserIds);
        ids.remove(null);
        if (ids.isEmpty()) {
            return Map.of();
        }
        try {
            return accounts.lookup(ids);
        } catch (RuntimeException e) {
            log.warn("Account emails unavailable for the workspace console: {}", e.getMessage());
            return Map.of();
        }
    }

    private static String emailOf(Map<UUID, AuthAccountClient.Account> accountsById, UUID authUserId) {
        AuthAccountClient.Account account = authUserId == null ? null : accountsById.get(authUserId);
        return account == null ? null : account.email();
    }

    private static String truncate(String value, int max) {
        if (value == null) {
            return null;
        }
        return value.length() <= max ? value : value.substring(0, max - 1) + "…";
    }

    private static Instant toInstant(LocalDateTime value) {
        return value == null ? null : value.atZone(ZoneId.systemDefault()).toInstant();
    }
}
