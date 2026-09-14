package com.rolesync.authservice.controllers;

import com.rolesync.authservice.dto.internal.AccountEmailRequest;
import com.rolesync.authservice.dto.internal.AccountLookupRequest;
import com.rolesync.authservice.dto.internal.AccountSummary;
import com.rolesync.authservice.dto.internal.EmailOutcome;
import com.rolesync.authservice.dto.internal.PlatformAccess;
import com.rolesync.authservice.dto.internal.ProvisionAccountRequest;
import com.rolesync.authservice.services.admin.PlatformAdminGuard;
import com.rolesync.authservice.services.user.AccountProvisioningService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

/**
 * Service-to-service API used by workspace-service when workspace admins manage their team.
 * Not routed by the gateway; every call must carry the internal service token
 * (see {@code InternalApiTokenFilter}). Workspace roles are checked by the caller.
 */
@RestController
@RequestMapping("/internal/v1/accounts")
@RequiredArgsConstructor
public class InternalAccountController {

    private final AccountProvisioningService provisioningService;
    private final PlatformAdminGuard platformAdminGuard;

    /** Finds the account for an email, or creates a verified one for it. */
    @PostMapping("/provision")
    public ResponseEntity<AccountSummary> provision(@Valid @RequestBody ProvisionAccountRequest request,
                                                    HttpServletRequest httpRequest) {
        return ResponseEntity.ok(provisioningService.provision(request, httpRequest));
    }

    /** Sets a new temporary password and emails the sign-in details. */
    @PostMapping("/{authUserId}/temporary-password")
    public ResponseEntity<EmailOutcome> issueTemporaryPassword(@PathVariable UUID authUserId,
                                                               @Valid @RequestBody AccountEmailRequest request,
                                                               HttpServletRequest httpRequest) {
        return ResponseEntity.ok(provisioningService.issueTemporaryPassword(authUserId, request, httpRequest));
    }

    /** Emails an existing account holder that they were added to a workspace. */
    @PostMapping("/{authUserId}/workspace-access-email")
    public ResponseEntity<EmailOutcome> sendWorkspaceAccessEmail(@PathVariable UUID authUserId,
                                                                 @Valid @RequestBody AccountEmailRequest request) {
        return ResponseEntity.ok(provisioningService.sendWorkspaceAccessEmail(authUserId, request));
    }

    /**
     * Whether an account is a platform super admin, for the Super Admin Console guards of other
     * services (workspace-service's support ticket console). An unknown account is simply not one.
     */
    @GetMapping("/{authUserId}/platform-access")
    public ResponseEntity<PlatformAccess> platformAccess(@PathVariable UUID authUserId) {
        return ResponseEntity.ok(platformAdminGuard.accessFor(authUserId));
    }

    /** Sign-in details (email, status, last sign-in, pending temporary password) for many accounts. */
    @PostMapping("/lookup")
    public ResponseEntity<List<AccountSummary>> lookup(@Valid @RequestBody AccountLookupRequest request) {
        return ResponseEntity.ok(provisioningService.lookup(request.getAuthUserIds()));
    }
}
