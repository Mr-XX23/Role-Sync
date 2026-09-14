package com.rolesync.authservice.dto.internal;

import com.rolesync.authservice.models.AuthUserCredentials;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.UUID;

/** What workspace-service needs to show and manage a member's sign-in account. No secrets. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AccountSummary {

    private UUID authUserId;
    private String email;
    private String username;
    private String status;
    private boolean emailVerified;
    private boolean mustChangePassword;
    private LocalDateTime temporaryPasswordExpiresAt;
    private LocalDateTime lastLoginAt;
    private LocalDateTime createdAt;
    private UUID provisionedBy;
    /** Only in provisioning answers: whether this call created the account. */
    private Boolean created;

    public static AccountSummary of(AuthUserCredentials user) {
        return AccountSummary.builder()
                .authUserId(user.getAuthUserId())
                .email(user.getEmail())
                .username(user.getUsername())
                .status(user.getStatus() == null ? null : user.getStatus().name())
                .emailVerified(user.isEmailVerified())
                .mustChangePassword(user.requiresPasswordChange())
                .temporaryPasswordExpiresAt(user.getTemporaryPasswordExpiresAt())
                .lastLoginAt(user.getLastLoginAt())
                .createdAt(user.getCreatedAt())
                .provisionedBy(user.getProvisionedBy())
                .build();
    }
}
