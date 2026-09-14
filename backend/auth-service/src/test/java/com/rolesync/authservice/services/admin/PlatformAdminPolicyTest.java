package com.rolesync.authservice.services.admin;

import com.rolesync.authservice.models.AuthUserCredentials;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PlatformAdminPolicyTest {

    private static AuthUserCredentials account(String email, boolean verified, AuthUserCredentials.Status status) {
        return AuthUserCredentials.builder()
                .authUserId(UUID.randomUUID())
                .email(email)
                .username("Someone")
                .isEmailVerified(verified)
                .status(status)
                .build();
    }

    @Test
    void allowlistIsTrimmedLowerCasedAndDeduplicated() {
        PlatformAdminPolicy policy = new PlatformAdminPolicy(" Ops@Acme.com, ops@acme.com ,, root@acme.com ");
        assertEquals(List.of("ops@acme.com", "root@acme.com"), policy.configuredEmails());
    }

    @Test
    void onlyVerifiedActiveAllowlistedAccountsAreSuperAdmins() {
        PlatformAdminPolicy policy = new PlatformAdminPolicy("ops@acme.com");
        assertTrue(policy.isSuperAdmin(account("OPS@acme.com", true, AuthUserCredentials.Status.ACTIVE)));
        assertFalse(policy.isSuperAdmin(account("ops@acme.com", false, AuthUserCredentials.Status.ACTIVE)));
        assertFalse(policy.isSuperAdmin(account("ops@acme.com", true, AuthUserCredentials.Status.SUSPENDED)));
        assertFalse(policy.isSuperAdmin(account("someone@acme.com", true, AuthUserCredentials.Status.ACTIVE)));
        assertFalse(policy.isSuperAdmin(null));
    }

    @Test
    void platformRoleIsSuperAdminOrNothing() {
        PlatformAdminPolicy policy = new PlatformAdminPolicy("ops@acme.com");
        assertEquals("SUPER_ADMIN", policy.platformRole(account("ops@acme.com", true, AuthUserCredentials.Status.ACTIVE)));
        assertNull(policy.platformRole(account("someone@acme.com", true, AuthUserCredentials.Status.ACTIVE)));
        assertNull(new PlatformAdminPolicy("").platformRole(account("ops@acme.com", true, AuthUserCredentials.Status.ACTIVE)));
    }
}
