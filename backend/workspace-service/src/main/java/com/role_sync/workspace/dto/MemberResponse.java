package com.role_sync.workspace.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

/** A workspace member as User Management shows them, with what the caller may do to them. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MemberResponse {

    @JsonProperty("membership_id")
    private UUID membershipId;

    @JsonProperty("profile_id")
    private UUID profileId;

    @JsonProperty("auth_user_id")
    private UUID authUserId;

    private String name;

    @JsonProperty("first_name")
    private String firstName;

    @JsonProperty("last_name")
    private String lastName;

    @JsonProperty("avatar_url")
    private String avatarUrl;

    @JsonProperty("job_title")
    private String jobTitle;

    /** The sign-in email; null when the account service couldn't be reached. */
    private String email;

    /** OWNER, ADMIN, MEMBER or VIEWER. */
    private String role;

    @JsonProperty("is_owner")
    private boolean owner;

    @JsonProperty("is_you")
    private boolean you;

    /** false: deactivated, no access to the workspace. */
    private boolean active;

    @JsonProperty("joined_at")
    private LocalDateTime joinedAt;

    @JsonProperty("invited_by_name")
    private String invitedByName;

    /** The sign-in account's status (ACTIVE, SUSPENDED...); null when unknown. */
    @JsonProperty("account_status")
    private String accountStatus;

    @JsonProperty("last_sign_in_at")
    private LocalDateTime lastSignInAt;

    /** PENDING while the person hasn't replaced their emailed temporary password, EXPIRED once it stopped working. */
    @JsonProperty("invite_status")
    private String inviteStatus;

    @JsonProperty("invite_expires_at")
    private LocalDateTime inviteExpiresAt;

    @JsonProperty("can_change_role")
    private boolean canChangeRole;

    @JsonProperty("can_deactivate")
    private boolean canDeactivate;

    @JsonProperty("can_remove")
    private boolean canRemove;

    @JsonProperty("can_resend_invite")
    private boolean canResendInvite;

    /** Roles the caller may give this member. */
    @JsonProperty("assignable_roles")
    private List<String> assignableRoles;
}
