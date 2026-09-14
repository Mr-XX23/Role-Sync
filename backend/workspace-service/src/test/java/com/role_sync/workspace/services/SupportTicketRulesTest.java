package com.role_sync.workspace.services;

import com.role_sync.workspace.models.SupportTicket;
import com.role_sync.workspace.services.WorkspaceAuthorizationService.CallerContext;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.time.LocalDateTime;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SupportTicketRulesTest {

    private final UUID reporter = UUID.randomUUID();
    private final UUID someoneElse = UUID.randomUUID();

    @Test
    void statusesAreNormalizedAndUnknownOnesRefused() {
        assertEquals("IN_PROGRESS", SupportTicketRules.normalizeStatus(" in_progress "));
        ResponseStatusException refused = assertThrows(ResponseStatusException.class, () -> SupportTicketRules.normalizeStatus("DONE"));
        assertEquals(HttpStatus.BAD_REQUEST, refused.getStatusCode());
        assertEquals(HttpStatus.BAD_REQUEST,
                assertThrows(ResponseStatusException.class, () -> SupportTicketRules.normalizeStatus(null)).getStatusCode());
    }

    @Test
    void reportersSeeTheirOwnTicketsAndWorkspaceAdminsSeeAll() {
        assertTrue(SupportTicketRules.canView(new CallerContext(reporter, "MEMBER"), reporter));
        assertFalse(SupportTicketRules.canView(new CallerContext(someoneElse, "MEMBER"), reporter));
        assertFalse(SupportTicketRules.canView(new CallerContext(someoneElse, "VIEWER"), reporter));
        assertTrue(SupportTicketRules.canView(new CallerContext(someoneElse, "ADMIN"), reporter));
        assertTrue(SupportTicketRules.canView(new CallerContext(someoneElse, "OWNER"), reporter));
    }

    @Test
    void onlyClosedTicketsRefuseRepliesFromTheWorkspace() {
        assertTrue(SupportTicketRules.canReporterReply(SupportTicket.OPEN));
        assertTrue(SupportTicketRules.canReporterReply(SupportTicket.IN_PROGRESS));
        assertTrue(SupportTicketRules.canReporterReply(SupportTicket.RESOLVED));
        assertFalse(SupportTicketRules.canReporterReply(SupportTicket.CLOSED));
    }

    @Test
    void aReporterWritingBackReopensAResolvedTicket() {
        assertEquals(SupportTicket.OPEN, SupportTicketRules.statusAfterReporterReply(SupportTicket.RESOLVED));
        assertEquals(SupportTicket.OPEN, SupportTicketRules.statusAfterReporterReply(SupportTicket.OPEN));
        assertEquals(SupportTicket.IN_PROGRESS, SupportTicketRules.statusAfterReporterReply(SupportTicket.IN_PROGRESS));
    }

    @Test
    void theTeamsFirstAnswerMovesANewTicketToInProgress() {
        assertEquals(SupportTicket.IN_PROGRESS, SupportTicketRules.statusAfterSupportReply(SupportTicket.OPEN));
        assertEquals(SupportTicket.IN_PROGRESS, SupportTicketRules.statusAfterSupportReply(SupportTicket.IN_PROGRESS));
        assertEquals(SupportTicket.RESOLVED, SupportTicketRules.statusAfterSupportReply(SupportTicket.RESOLVED));
    }

    @Test
    void closedAtFollowsTheStatus() {
        LocalDateTime earlier = LocalDateTime.of(2026, 9, 1, 10, 0);
        LocalDateTime now = LocalDateTime.of(2026, 9, 15, 12, 0);
        assertEquals(now, SupportTicketRules.closedAt(SupportTicket.OPEN, SupportTicket.RESOLVED, null, now));
        assertEquals(now, SupportTicketRules.closedAt(SupportTicket.IN_PROGRESS, SupportTicket.CLOSED, null, now));
        assertEquals(earlier, SupportTicketRules.closedAt(SupportTicket.RESOLVED, SupportTicket.CLOSED, earlier, now));
        assertNull(SupportTicketRules.closedAt(SupportTicket.RESOLVED, SupportTicket.OPEN, earlier, now));
        assertNull(SupportTicketRules.closedAt(SupportTicket.OPEN, SupportTicket.IN_PROGRESS, null, now));
    }
}
