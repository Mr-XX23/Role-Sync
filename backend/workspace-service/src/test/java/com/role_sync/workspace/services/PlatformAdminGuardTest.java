package com.role_sync.workspace.services;

import com.role_sync.workspace.clients.AuthAccountClient;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PlatformAdminGuardTest {

    /** auth-service as the guard sees it: one super admin, everyone else not; counts the calls. */
    private static final class FakeAccounts extends AuthAccountClient {
        final UUID superAdmin = UUID.randomUUID();
        final AtomicInteger calls = new AtomicInteger();
        boolean down;

        FakeAccounts() {
            super("http://auth-service.test", "token");
        }

        @Override
        public PlatformAccess platformAccess(UUID authUserId) {
            calls.incrementAndGet();
            if (down) {
                throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "auth-service is down");
            }
            boolean isSuperAdmin = superAdmin.equals(authUserId);
            return new PlatformAccess(authUserId, isSuperAdmin, isSuperAdmin ? "ops@rolesync.ai" : null);
        }
    }

    private static final class TickingClock extends Clock {
        Instant now = Instant.parse("2026-09-15T10:00:00Z");

        @Override
        public ZoneOffset getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(java.time.ZoneId zone) {
            return this;
        }

        @Override
        public Instant instant() {
            return now;
        }
    }

    private final FakeAccounts accounts = new FakeAccounts();
    private final TickingClock clock = new TickingClock();
    private final PlatformAdminGuard guard = new PlatformAdminGuard(accounts, Duration.ofSeconds(30), clock);

    @Test
    void superAdminsGetThroughWithTheirEmailForTheAuditLog() {
        PlatformAdminGuard.Actor actor = guard.requireSuperAdmin(accounts.superAdmin);
        assertEquals(accounts.superAdmin, actor.authUserId());
        assertEquals("ops@rolesync.ai", actor.email());
    }

    @Test
    void everyoneElseIsRefusedAndNobodyIsUnauthorized() {
        ResponseStatusException refused = assertThrows(ResponseStatusException.class, () -> guard.requireSuperAdmin(UUID.randomUUID()));
        assertEquals(HttpStatus.FORBIDDEN, refused.getStatusCode());
        ResponseStatusException anonymous = assertThrows(ResponseStatusException.class, () -> guard.requireSuperAdmin(null));
        assertEquals(HttpStatus.UNAUTHORIZED, anonymous.getStatusCode());
        assertEquals(1, accounts.calls.get(), "an anonymous call never reaches auth-service");
    }

    @Test
    void answersAreKeptForAWhileThenAskedAgain() {
        guard.requireSuperAdmin(accounts.superAdmin);
        guard.requireSuperAdmin(accounts.superAdmin);
        assertEquals(1, accounts.calls.get());
        clock.now = clock.now.plusSeconds(31);
        guard.requireSuperAdmin(accounts.superAdmin);
        assertEquals(2, accounts.calls.get());
    }

    @Test
    void whenAuthServiceCannotBeAskedTheCallFailsClosed() {
        accounts.down = true;
        ResponseStatusException failure = assertThrows(ResponseStatusException.class, () -> guard.requireSuperAdmin(accounts.superAdmin));
        assertEquals(HttpStatus.SERVICE_UNAVAILABLE, failure.getStatusCode());
    }
}
