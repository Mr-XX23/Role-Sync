package com.rolesync.authservice.controllers;

import com.rolesync.authservice.dto.admin.AdminAuditEntry;
import com.rolesync.authservice.dto.admin.AdminPage;
import com.rolesync.authservice.dto.admin.AdminSignOutResponse;
import com.rolesync.authservice.dto.admin.AdminStatsResponse;
import com.rolesync.authservice.dto.admin.AdminUserDetailResponse;
import com.rolesync.authservice.dto.admin.AdminUserResponse;
import com.rolesync.authservice.dto.admin.SuspendUserRequest;
import com.rolesync.authservice.models.AuthUserCredentials;
import com.rolesync.authservice.services.admin.AdminAuditService;
import com.rolesync.authservice.services.admin.AdminStatsService;
import com.rolesync.authservice.services.admin.AdminUserService;
import com.rolesync.authservice.services.admin.PlatformAdminGuard;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

/**
 * Super Admin Console API for sign-in accounts (reached through the gateway at /api/v1/auth/admin).
 * Every endpoint resolves the caller through {@link PlatformAdminGuard} first: 401 without a
 * session, 403 for anyone who is not a platform super admin.
 */
@RestController
@RequestMapping("/api/v1/auth/admin")
@RequiredArgsConstructor
public class AdminController {

    private final PlatformAdminGuard guard;
    private final AdminUserService userService;
    private final AdminStatsService statsService;
    private final AdminAuditService auditService;

    @GetMapping("/stats")
    public AdminStatsResponse stats(@RequestParam(defaultValue = "30") int days, HttpServletRequest request) {
        guard.requireSuperAdmin(request);
        return statsService.stats(days);
    }

    @GetMapping("/audit")
    public List<AdminAuditEntry> audit(@RequestParam(defaultValue = "100") int limit, HttpServletRequest request) {
        guard.requireSuperAdmin(request);
        return auditService.recent(limit);
    }

    @GetMapping("/users")
    public AdminPage<AdminUserResponse> users(@RequestParam(required = false) String q,
                                              @RequestParam(required = false) String status,
                                              @RequestParam(required = false) String verified,
                                              @RequestParam(name = "login_type", required = false) String loginType,
                                              @RequestParam(defaultValue = "0") int page,
                                              @RequestParam(defaultValue = "25") int size,
                                              HttpServletRequest request) {
        guard.requireSuperAdmin(request);
        return userService.list(q, status, verified, loginType, page, size);
    }

    @GetMapping("/users/{userId}")
    public AdminUserDetailResponse user(@PathVariable UUID userId, HttpServletRequest request) {
        guard.requireSuperAdmin(request);
        return userService.detail(userId);
    }

    @PostMapping("/users/{userId}/suspend")
    public AdminUserResponse suspend(@PathVariable UUID userId,
                                     @Valid @RequestBody(required = false) SuspendUserRequest body,
                                     HttpServletRequest request) {
        AuthUserCredentials admin = guard.requireSuperAdmin(request);
        return userService.suspend(admin, userId, body == null ? null : body.getReason(), request);
    }

    @PostMapping("/users/{userId}/reactivate")
    public AdminUserResponse reactivate(@PathVariable UUID userId, HttpServletRequest request) {
        return userService.reactivate(guard.requireSuperAdmin(request), userId);
    }

    @PostMapping("/users/{userId}/unlock")
    public AdminUserResponse unlock(@PathVariable UUID userId, HttpServletRequest request) {
        return userService.unlock(guard.requireSuperAdmin(request), userId);
    }

    @PostMapping("/users/{userId}/sign-out")
    public AdminSignOutResponse signOut(@PathVariable UUID userId, HttpServletRequest request) {
        return userService.signOut(guard.requireSuperAdmin(request), userId);
    }
}
