package com.role_sync.workspace.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/** A new support ticket from the Support Desk. */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SupportTicketRequest {

    @NotBlank(message = "subject cannot be blank")
    @Size(max = 200, message = "subject can have at most 200 characters")
    private String subject;

    @NotBlank(message = "description cannot be blank")
    @Size(max = 5000, message = "description can have at most 5000 characters")
    private String description;
}
