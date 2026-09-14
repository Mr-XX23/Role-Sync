package com.rolesync.authservice.dto.internal;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

/** A workspace admin adds someone by email: find their account, or create a verified one. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ProvisionAccountRequest {

    @NotBlank(message = "Email is required")
    @Email(message = "Enter a valid email address")
    @Size(max = 100, message = "Email must be at most 100 characters")
    private String email;

    @NotBlank(message = "Name is required")
    @Size(max = 101, message = "Name must be at most 101 characters")
    private String fullName;

    /** The admin's auth user id, recorded on accounts this call creates. */
    private UUID invitedByUserId;
}
