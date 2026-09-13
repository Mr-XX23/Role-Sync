package com.role_sync.workspace.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class InviteMemberResponse {

    private MemberResponse member;

    /** A new sign-in account was created for the email (rather than an existing one added). */
    @JsonProperty("account_created")
    private boolean accountCreated;

    /** A deactivated membership was restored instead of a new one created. */
    private boolean reactivated;

    /** Whether sign-in details were emailed rather than a "you were added" notice. */
    @JsonProperty("credentials_sent")
    private boolean credentialsSent;

    /** SENT, FAILED or PENDING. */
    @JsonProperty("email_status")
    private String emailStatus;

    @JsonProperty("email_message")
    private String emailMessage;

    @JsonProperty("invite_expires_at")
    private LocalDateTime inviteExpiresAt;
}
