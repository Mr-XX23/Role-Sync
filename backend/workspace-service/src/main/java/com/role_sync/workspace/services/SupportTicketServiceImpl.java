package com.role_sync.workspace.services;

import com.role_sync.workspace.clients.AuthAccountClient;
import com.role_sync.workspace.dto.SupportTicketMessageRequest;
import com.role_sync.workspace.dto.SupportTicketMessageResponse;
import com.role_sync.workspace.dto.SupportTicketRequest;
import com.role_sync.workspace.dto.SupportTicketResponse;
import com.role_sync.workspace.dto.admin.AdminPage;
import com.role_sync.workspace.dto.admin.AdminSupportTicket;
import com.role_sync.workspace.dto.admin.AdminSupportTicketDetail;
import com.role_sync.workspace.dto.admin.AdminSupportTicketStats;
import com.role_sync.workspace.dto.admin.SupportTicketStatusRequest;
import com.role_sync.workspace.models.PlatformAdminEvent;
import com.role_sync.workspace.models.SupportTicket;
import com.role_sync.workspace.models.SupportTicketMessage;
import com.role_sync.workspace.models.Workspace;
import com.role_sync.workspace.models.WorkspaceProfile;
import com.role_sync.workspace.repository.AdminSupportTicketSearch;
import com.role_sync.workspace.repository.PlatformAdminEventRepository;
import com.role_sync.workspace.repository.SupportTicketMessageRepository;
import com.role_sync.workspace.repository.SupportTicketRepository;
import com.role_sync.workspace.repository.WorkspaceProfileRepository;
import com.role_sync.workspace.repository.WorkspaceRepository;
import com.role_sync.workspace.services.PlatformAdminGuard.Actor;
import com.role_sync.workspace.services.WorkspaceAuthorizationService.CallerContext;
import com.role_sync.workspace.utils.SanitizationUtils;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Collection;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Supplier;

@Service
@RequiredArgsConstructor
@Slf4j
public class SupportTicketServiceImpl implements SupportTicketService {

    /** How replies from the RoleSync team are signed for the person asking. */
    static final String SUPPORT_AUTHOR = "RoleSync Support";
    private static final int MAX_LIST = 200;
    private static final int MAX_PAGE_SIZE = 100;

    private final SupportTicketRepository tickets;
    private final SupportTicketMessageRepository messages;
    private final WorkspaceRepository workspaces;
    private final WorkspaceProfileRepository profiles;
    private final WorkspaceAuthorizationService authorization;
    private final PlatformAdminGuard adminGuard;
    private final AdminSupportTicketSearch search;
    private final PlatformAdminEventRepository events;
    private final AuthAccountClient accounts;
    private final PlatformTransactionManager transactionManager;

    // ------------------------------------------------------------------ Support Desk

    @Override
    public Mono<SupportTicketResponse> create(UUID workspaceId, UUID authUserId, SupportTicketRequest request) {
        return Mono.fromCallable(() -> {
            CallerContext caller = authorization.requireActiveMembership(authUserId, workspaceId);
            String subject = SanitizationUtils.sanitizeText(request.getSubject());
            String description = SanitizationUtils.sanitizeText(request.getDescription());
            if (subject.isBlank() || description.isBlank()) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "subject and description cannot be blank");
            }
            return inTransaction(() -> {
                WorkspaceProfile reporter = profiles.findById(caller.profileId())
                        .orElseThrow(() -> new ResponseStatusException(HttpStatus.FORBIDDEN, "No workspace profile exists for the authenticated user"));
                SupportTicket ticket = SupportTicket.builder()
                        .workspace(workspaces.getReferenceById(workspaceId))
                        .reporter(reporter)
                        .reporterAuthUserId(authUserId)
                        .subject(subject)
                        .description(description)
                        .status(SupportTicket.OPEN)
                        .build();
                SupportTicket saved = tickets.saveAndFlush(ticket);
                log.info("Support ticket {} opened in workspace {} by profile {}", saved.getTicketId(), workspaceId, caller.profileId());
                return toResponse(saved, workspaceId, caller, authUserId, List.of());
            });
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    public Flux<SupportTicketResponse> list(UUID workspaceId, UUID authUserId, boolean everyone, int limit) {
        return Mono.fromCallable(() -> {
            CallerContext caller = authorization.requireActiveMembership(authUserId, workspaceId);
            PageRequest page = PageRequest.of(0, Math.max(1, Math.min(limit, MAX_LIST)));
            return inTransaction(() -> {
                List<SupportTicket> rows = everyone && caller.isAdmin()
                        ? tickets.findByWorkspace(workspaceId, page)
                        : tickets.findByWorkspaceAndReporter(workspaceId, caller.profileId(), page);
                return rows.stream().map(ticket -> toResponse(ticket, workspaceId, caller, authUserId, null)).toList();
            });
        })
        .subscribeOn(Schedulers.boundedElastic())
        .flatMapMany(Flux::fromIterable);
    }

    @Override
    public Mono<SupportTicketResponse> get(UUID workspaceId, UUID ticketId, UUID authUserId) {
        return Mono.fromCallable(() -> {
            CallerContext caller = authorization.requireActiveMembership(authUserId, workspaceId);
            return inTransaction(() -> {
                SupportTicket ticket = requireVisible(ticketId, workspaceId, caller);
                return toResponse(ticket, workspaceId, caller, authUserId, conversation(ticketId));
            });
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    public Mono<SupportTicketResponse> reply(UUID workspaceId, UUID ticketId, UUID authUserId, SupportTicketMessageRequest request) {
        return Mono.fromCallable(() -> {
            CallerContext caller = authorization.requireActiveMembership(authUserId, workspaceId);
            String body = SanitizationUtils.sanitizeText(request.getBody());
            if (body.isBlank()) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "body cannot be blank");
            }
            return inTransaction(() -> {
                SupportTicket ticket = requireVisible(ticketId, workspaceId, caller);
                if (!SupportTicketRules.canReporterReply(ticket.getStatus())) {
                    throw new ResponseStatusException(HttpStatus.CONFLICT,
                            "This ticket is closed. Open a new ticket if you still need help.");
                }
                WorkspaceProfile author = profiles.findById(caller.profileId()).orElse(null);
                addMessage(ticket, authUserId, displayName(author), false, body);
                ticket.setStatus(moveTo(ticket, SupportTicketRules.statusAfterReporterReply(ticket.getStatus())));
                SupportTicket saved = tickets.saveAndFlush(ticket);
                return toResponse(saved, workspaceId, caller, authUserId, conversation(ticketId));
            });
        }).subscribeOn(Schedulers.boundedElastic());
    }

    // ------------------------------------------------------------------ Super Admin Console

    @Override
    public Mono<AdminPage<AdminSupportTicket>> adminList(UUID actorUserId, String text, String status, UUID workspaceId,
                                                         boolean awaitingSupport, int page, int size) {
        return Mono.fromCallable(() -> {
            adminGuard.requireSuperAdmin(actorUserId);
            String wantedStatus = status == null || status.isBlank() ? null : SupportTicketRules.normalizeStatus(status);
            int safePage = Math.max(0, page);
            int safeSize = Math.max(1, Math.min(size, MAX_PAGE_SIZE));
            return inTransaction(() -> {
                AdminSupportTicketSearch.Result result = search.search(
                        new AdminSupportTicketSearch.Criteria(text, wantedStatus, workspaceId, awaitingSupport), safePage, safeSize);
                Map<UUID, AuthAccountClient.Account> accountsById = lookupAccounts(
                        result.tickets().stream().map(SupportTicket::getReporterAuthUserId).toList());
                List<AdminSupportTicket> items = result.tickets().stream()
                        .map(ticket -> toAdmin(ticket, accountsById))
                        .toList();
                return AdminPage.of(items, safePage, safeSize, result.total());
            });
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    public Mono<AdminSupportTicketStats> adminStats(UUID actorUserId) {
        return Mono.fromCallable(() -> {
            adminGuard.requireSuperAdmin(actorUserId);
            return inTransaction(() -> {
                long open = 0, inProgress = 0, resolved = 0, closed = 0;
                for (Object[] row : tickets.countByStatus()) {
                    long count = ((Number) row[1]).longValue();
                    switch (String.valueOf(row[0])) {
                        case SupportTicket.OPEN -> open = count;
                        case SupportTicket.IN_PROGRESS -> inProgress = count;
                        case SupportTicket.RESOLVED -> resolved = count;
                        case SupportTicket.CLOSED -> closed = count;
                        default -> { }
                    }
                }
                return AdminSupportTicketStats.builder()
                        .total(open + inProgress + resolved + closed)
                        .open(open)
                        .inProgress(inProgress)
                        .resolved(resolved)
                        .closed(closed)
                        .awaitingSupport(tickets.countAwaitingSupport(SupportTicketRules.ACTIVE_STATUSES))
                        .openedLast7Days(tickets.countCreatedSince(LocalDateTime.now().minusDays(7)))
                        .build();
            });
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    public Mono<AdminSupportTicketDetail> adminGet(UUID actorUserId, UUID ticketId) {
        return Mono.fromCallable(() -> {
            adminGuard.requireSuperAdmin(actorUserId);
            return inTransaction(() -> toAdminDetail(requireTicket(ticketId)));
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    public Mono<AdminSupportTicketDetail> adminReply(UUID actorUserId, UUID ticketId, SupportTicketMessageRequest request) {
        return Mono.fromCallable(() -> {
            Actor actor = adminGuard.requireSuperAdmin(actorUserId);
            String body = SanitizationUtils.sanitizeText(request.getBody());
            if (body.isBlank()) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "body cannot be blank");
            }
            return inTransaction(() -> {
                SupportTicket ticket = requireTicket(ticketId);
                if (SupportTicket.CLOSED.equals(ticket.getStatus())) {
                    throw new ResponseStatusException(HttpStatus.CONFLICT, "This ticket is closed. Reopen it first to reply.");
                }
                addMessage(ticket, actor.authUserId(), SUPPORT_AUTHOR, true, body);
                String previous = ticket.getStatus();
                ticket.setStatus(moveTo(ticket, SupportTicketRules.statusAfterSupportReply(previous)));
                SupportTicket saved = tickets.saveAndFlush(ticket);
                record(actor, saved, PlatformAdminEvent.SUPPORT_TICKET_REPLIED,
                        "Replied to support ticket \"" + saved.getSubject() + "\" from " + saved.getWorkspace().getName()
                                + (previous.equals(saved.getStatus()) ? "" : " (now " + saved.getStatus() + ")"));
                return toAdminDetail(saved);
            });
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @Override
    public Mono<AdminSupportTicketDetail> adminSetStatus(UUID actorUserId, UUID ticketId, SupportTicketStatusRequest request) {
        return Mono.fromCallable(() -> {
            Actor actor = adminGuard.requireSuperAdmin(actorUserId);
            String next = SupportTicketRules.normalizeStatus(request.getStatus());
            String note = SanitizationUtils.sanitizeText(request.getNote());
            return inTransaction(() -> {
                SupportTicket ticket = requireTicket(ticketId);
                String previous = ticket.getStatus();
                if (previous.equals(next)) {
                    return toAdminDetail(ticket);
                }
                ticket.setStatus(moveTo(ticket, next));
                SupportTicket saved = tickets.saveAndFlush(ticket);
                record(actor, saved, PlatformAdminEvent.SUPPORT_TICKET_STATUS_CHANGED,
                        "Moved support ticket \"" + saved.getSubject() + "\" from " + saved.getWorkspace().getName()
                                + " from " + previous + " to " + next
                                + (note == null || note.isBlank() ? "" : ": " + note));
                return toAdminDetail(saved);
            });
        }).subscribeOn(Schedulers.boundedElastic());
    }

    // ------------------------------------------------------------------ helpers

    private <T> T inTransaction(Supplier<T> work) {
        return new TransactionTemplate(transactionManager).execute(status -> work.get());
    }

    private SupportTicket requireTicket(UUID ticketId) {
        return tickets.findWithWorkspaceAndReporter(ticketId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Ticket not found"));
    }

    /** The ticket, if it belongs to the workspace and the caller may see it; otherwise 404 (no hint that it exists). */
    private SupportTicket requireVisible(UUID ticketId, UUID workspaceId, CallerContext caller) {
        SupportTicket ticket = requireTicket(ticketId);
        if (!ticket.getWorkspace().getWorkspaceId().equals(workspaceId)
                || !SupportTicketRules.canView(caller, ticket.getReporter().getProfileId())) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Ticket not found");
        }
        return ticket;
    }

    private List<SupportTicketMessage> conversation(UUID ticketId) {
        return messages.findByTicketTicketIdOrderByCreatedAtAscMessageIdAsc(ticketId);
    }

    private void addMessage(SupportTicket ticket, UUID authorAuthUserId, String authorName, boolean fromSupport, String body) {
        LocalDateTime now = LocalDateTime.now();
        messages.save(SupportTicketMessage.builder()
                .ticket(ticket)
                .authorAuthUserId(authorAuthUserId)
                .authorName(authorName)
                .fromSupport(fromSupport)
                .body(body)
                .createdAt(now)
                .build());
        ticket.setMessageCount(ticket.getMessageCount() + 1);
        ticket.setLastMessageAt(now);
        ticket.setLastMessageFromSupport(fromSupport);
    }

    /** The next status, with {@code closedAt} kept in step; returns it so the caller can assign it. */
    private static String moveTo(SupportTicket ticket, String next) {
        ticket.setClosedAt(SupportTicketRules.closedAt(ticket.getStatus(), next, ticket.getClosedAt(), LocalDateTime.now()));
        return next;
    }

    private void record(Actor actor, SupportTicket ticket, String action, String summary) {
        events.save(PlatformAdminEvent.builder()
                .actorUserId(actor.authUserId())
                .actorEmail(actor.email())
                .action(action)
                .targetType(PlatformAdminEvent.TARGET_SUPPORT_TICKET)
                .targetId(ticket.getTicketId().toString())
                .targetLabel(truncate(ticket.getSubject(), 200))
                .summary(truncate(summary, 500))
                .build());
    }

    /** Reporter emails from auth-service; none when it can't be asked (the console shows the ticket anyway). */
    private Map<UUID, AuthAccountClient.Account> lookupAccounts(Collection<UUID> authUserIds) {
        Set<UUID> ids = new HashSet<>(authUserIds);
        ids.remove(null);
        if (ids.isEmpty()) {
            return Map.of();
        }
        try {
            return accounts.lookup(ids);
        } catch (RuntimeException e) {
            log.warn("Reporter emails unavailable for the support ticket console: {}", e.getMessage());
            return Map.of();
        }
    }

    static String displayName(WorkspaceProfile profile) {
        if (profile == null) {
            return "Workspace member";
        }
        if (profile.getDisplayName() != null && !profile.getDisplayName().isBlank()) {
            return profile.getDisplayName().trim();
        }
        String full = ((profile.getFirstName() == null ? "" : profile.getFirstName()) + " "
                + (profile.getLastName() == null ? "" : profile.getLastName())).trim();
        return full.isEmpty() ? "Workspace member" : full;
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

    private static SupportTicketResponse toResponse(SupportTicket ticket, UUID workspaceId, CallerContext caller,
                                                    UUID callerAuthUserId, List<SupportTicketMessage> conversation) {
        WorkspaceProfile reporter = ticket.getReporter();
        boolean mine = reporter.getProfileId().equals(caller.profileId());
        return SupportTicketResponse.builder()
                .ticketId(ticket.getTicketId())
                .workspaceId(workspaceId)
                .subject(ticket.getSubject())
                .description(ticket.getDescription())
                .status(ticket.getStatus())
                .reporter(SupportTicketResponse.Reporter.builder()
                        .profileId(reporter.getProfileId())
                        .name(displayName(reporter))
                        .mine(mine)
                        .build())
                .messageCount(ticket.getMessageCount())
                .lastMessageAt(ticket.getLastMessageAt())
                .lastMessageFromSupport(ticket.isLastMessageFromSupport())
                .canReply(SupportTicketRules.canReporterReply(ticket.getStatus()))
                .createdAt(ticket.getCreatedAt())
                .updatedAt(ticket.getUpdatedAt())
                .closedAt(ticket.getClosedAt())
                .messages(conversation == null ? null : conversation.stream()
                        .map(message -> SupportTicketMessageResponse.builder()
                                .messageId(message.getMessageId())
                                .authorName(message.getAuthorName())
                                .fromSupport(message.isFromSupport())
                                .mine(!message.isFromSupport() && message.getAuthorAuthUserId().equals(callerAuthUserId))
                                .body(message.getBody())
                                .createdAt(message.getCreatedAt())
                                .build())
                        .toList())
                .build();
    }

    private static AdminSupportTicket toAdmin(SupportTicket ticket, Map<UUID, AuthAccountClient.Account> accountsById) {
        Workspace workspace = ticket.getWorkspace();
        WorkspaceProfile reporter = ticket.getReporter();
        AuthAccountClient.Account account = accountsById.get(ticket.getReporterAuthUserId());
        return AdminSupportTicket.builder()
                .ticketId(ticket.getTicketId())
                .subject(ticket.getSubject())
                .status(ticket.getStatus())
                .messageCount(ticket.getMessageCount())
                .lastMessageAt(toInstant(ticket.getLastMessageAt()))
                .lastMessageFromSupport(ticket.isLastMessageFromSupport())
                .createdAt(toInstant(ticket.getCreatedAt()))
                .updatedAt(toInstant(ticket.getUpdatedAt()))
                .closedAt(toInstant(ticket.getClosedAt()))
                .workspace(AdminSupportTicket.Workspace.builder()
                        .workspaceId(workspace.getWorkspaceId())
                        .name(workspace.getName())
                        .active(!Boolean.FALSE.equals(workspace.getIsActive()))
                        .build())
                .reporter(AdminSupportTicket.Reporter.builder()
                        .profileId(reporter.getProfileId())
                        .authUserId(ticket.getReporterAuthUserId())
                        .name(displayName(reporter))
                        .email(account == null ? null : account.email())
                        .build())
                .build();
    }

    private AdminSupportTicketDetail toAdminDetail(SupportTicket ticket) {
        Map<UUID, AuthAccountClient.Account> accountsById = lookupAccounts(List.of(ticket.getReporterAuthUserId()));
        return AdminSupportTicketDetail.builder()
                .ticket(toAdmin(ticket, accountsById))
                .description(ticket.getDescription())
                .messages(conversation(ticket.getTicketId()).stream()
                        .map(message -> AdminSupportTicketDetail.Message.builder()
                                .messageId(message.getMessageId())
                                .authorAuthUserId(message.getAuthorAuthUserId())
                                .authorName(message.getAuthorName())
                                .fromSupport(message.isFromSupport())
                                .body(message.getBody())
                                .createdAt(toInstant(message.getCreatedAt()))
                                .build())
                        .toList())
                .build();
    }
}
