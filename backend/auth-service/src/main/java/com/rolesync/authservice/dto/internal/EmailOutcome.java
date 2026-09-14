package com.rolesync.authservice.dto.internal;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * Whether an account email went out. {@code SENT} and {@code FAILED} are final; {@code PENDING}
 * means the mail server had not answered in time and the email may still arrive.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class EmailOutcome {

    public enum Status { SENT, FAILED, PENDING }

    private Status status;
    private String message;
    /** For temporary passwords: when the emailed password stops working. */
    private LocalDateTime temporaryPasswordExpiresAt;
}
