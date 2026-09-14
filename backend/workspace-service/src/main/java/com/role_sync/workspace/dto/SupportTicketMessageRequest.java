package com.role_sync.workspace.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/** A reply on a support ticket, from the reporter or from the RoleSync team. */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SupportTicketMessageRequest {

    @NotBlank(message = "body cannot be blank")
    @Size(max = 5000, message = "body can have at most 5000 characters")
    private String body;
}
