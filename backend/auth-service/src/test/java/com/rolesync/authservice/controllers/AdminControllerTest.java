package com.rolesync.authservice.controllers;

import com.rolesync.authservice.exceptions.ForbiddenException;
import com.rolesync.authservice.exceptions.GlobalExceptionsHandler;
import com.rolesync.authservice.models.AuthUserCredentials;
import com.rolesync.authservice.services.admin.AdminAuditService;
import com.rolesync.authservice.services.admin.AdminStatsService;
import com.rolesync.authservice.services.admin.AdminUserService;
import com.rolesync.authservice.services.admin.PlatformAdminGuard;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class AdminControllerTest {

    private final PlatformAdminGuard guard = mock(PlatformAdminGuard.class);
    private final AdminUserService users = mock(AdminUserService.class);
    private final AdminStatsService stats = mock(AdminStatsService.class);
    private final AdminAuditService audit = mock(AdminAuditService.class);
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.standaloneSetup(new AdminController(guard, users, stats, audit))
                .setControllerAdvice(new GlobalExceptionsHandler())
                .build();
    }

    @Test
    void nonSuperAdminsGet403AndNothingRuns() throws Exception {
        when(guard.requireSuperAdmin(any())).thenThrow(new ForbiddenException(PlatformAdminGuard.NOT_SUPER_ADMIN));
        String userPath = "/api/v1/auth/admin/users/" + UUID.randomUUID();

        mvc.perform(get("/api/v1/auth/admin/stats")).andExpect(status().isForbidden());
        mvc.perform(get("/api/v1/auth/admin/audit")).andExpect(status().isForbidden());
        mvc.perform(get("/api/v1/auth/admin/users")).andExpect(status().isForbidden());
        mvc.perform(get(userPath)).andExpect(status().isForbidden());
        mvc.perform(post(userPath + "/suspend").contentType("application/json").content("{\"reason\":\"x\"}"))
                .andExpect(status().isForbidden());
        mvc.perform(post(userPath + "/reactivate")).andExpect(status().isForbidden());
        mvc.perform(post(userPath + "/unlock")).andExpect(status().isForbidden());
        mvc.perform(post(userPath + "/sign-out")).andExpect(status().isForbidden());

        verifyNoInteractions(users, stats, audit);
    }

    @Test
    void superAdminCallsReachTheServices() throws Exception {
        AuthUserCredentials admin = AuthUserCredentials.builder().authUserId(UUID.randomUUID()).build();
        when(guard.requireSuperAdmin(any())).thenReturn(admin);
        when(audit.recent(10)).thenReturn(List.of());
        UUID userId = UUID.randomUUID();

        mvc.perform(get("/api/v1/auth/admin/audit").param("limit", "10")).andExpect(status().isOk());
        mvc.perform(get("/api/v1/auth/admin/users").param("login_type", "EMAIL").param("page", "2").param("size", "50"))
                .andExpect(status().isOk());
        mvc.perform(post("/api/v1/auth/admin/users/" + userId + "/suspend")
                .contentType("application/json").content("{\"reason\":\"spam\"}")).andExpect(status().isOk());

        verify(users).list(null, null, null, "EMAIL", 2, 50);
        verify(users).suspend(eq(admin), eq(userId), eq("spam"), any());
    }

    @Test
    void malformedUserIdIs400AndUnknownPathsAreNot500() throws Exception {
        when(guard.requireSuperAdmin(any())).thenReturn(AuthUserCredentials.builder().build());
        mvc.perform(get("/api/v1/auth/admin/users/not-a-uuid")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/v1/auth/admin/users/" + UUID.randomUUID() + "/suspend"))
                .andExpect(status().isMethodNotAllowed());
    }
}
