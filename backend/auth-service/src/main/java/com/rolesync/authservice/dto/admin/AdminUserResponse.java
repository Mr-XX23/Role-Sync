package com.rolesync.authservice.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.rolesync.authservice.models.AuthUserCredentials;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

/** A sign-in account as the Super Admin Console shows it. No secrets. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminUserResponse {

    @JsonProperty("user_id")
    private UUID userId;

    private String email;

    private String username;

    @JsonProperty("phone_number")
    private String phoneNumber;

    /** ACTIVE, INACTIVE, SUSPENDED or LOCKED. */
    private String status;

    @JsonProperty("email_verified")
    private boolean emailVerified;

    @JsonProperty("phone_verified")
    private boolean phoneVerified;

    /** EMAIL, PHONE, THIRD_PARTY or BOTH. */
    @JsonProperty("login_type")
    private String loginType;

    @JsonProperty("super_admin")
    private boolean superAdmin;

    @JsonProperty("must_change_password")
    private boolean mustChangePassword;

    /** Created by a workspace admin rather than by the person signing up. */
    private boolean provisioned;

    /** Too many failed sign-ins: sign-in is refused for a while. */
    @JsonProperty("locked_out")
    private boolean lockedOut;

    @JsonProperty("created_at")
    private String createdAt;

    @JsonProperty("last_login_at")
    private String lastLoginAt;

    public static AdminUserResponse of(AuthUserCredentials user, boolean superAdmin, boolean lockedOut) {
        String phone = user.getPhoneNumber();
        return AdminUserResponse.builder()
                .userId(user.getAuthUserId())
                .email(user.getEmail())
                .username(user.getUsername())
                // Email-only sign-ups store an empty phone number.
                .phoneNumber(phone == null || phone.isBlank() ? null : phone)
                .status(user.getStatus() == null ? null : user.getStatus().name())
                .emailVerified(user.isEmailVerified())
                .phoneVerified(user.isPhoneVerified())
                .loginType(user.getLoginType() == null ? null : user.getLoginType().name())
                .superAdmin(superAdmin)
                .mustChangePassword(user.requiresPasswordChange())
                .provisioned(user.getProvisionedBy() != null)
                .lockedOut(lockedOut)
                .createdAt(AdminTimestamps.utc(user.getCreatedAt()))
                .lastLoginAt(AdminTimestamps.utc(user.getLastLoginAt()))
                .build();
    }
}
