package com.role_sync.workspace.dto.admin;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/** A super admin moving a ticket to another status; the note goes to the audit log, not to the reporter. */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SupportTicketStatusRequest {

    @NotBlank(message = "status cannot be blank")
    private String status;

    @Size(max = 500, message = "note can have at most 500 characters")
    private String note;
}
