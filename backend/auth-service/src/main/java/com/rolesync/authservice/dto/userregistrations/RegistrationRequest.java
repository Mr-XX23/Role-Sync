package com.rolesync.authservice.dto.userregistrations;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import lombok.Data;

/**
 * Public sign-up form. The platform role is deliberately absent: self-registered accounts are always
 * {@code USER} (see {@link com.rolesync.authservice.models.Role}). A {@code role} sent by older clients
 * is accepted and ignored, so it can never reach the account.
 */
@Data
@JsonIgnoreProperties(value = "role")
public class RegistrationRequest {

    @NotNull(message = "Username is required")
    @Size(min = 3, max = 24, message = "Username must be between 3 and 50 characters")
    private String username;

    @Email(message = "Email should be valid")
    private String email;

    @Pattern(regexp = "^\\+?[1-9]\\d{1,16}$", message = "Phone format is invalid")
    private String phoneNumber;

    @NotNull(message = "Password is required")
    @Size(min = 8, message = "Password must be at least 8 characters", max = 256)
    private String password;

    @NotNull(message = "Accepting terms and conditions is required")
    @AssertTrue(message = "You must accept the terms and conditions")
    private Boolean acceptTerms;

    @NotNull(message = "Accepting HIPAA privacy notice is required")
    @AssertTrue(message = "You must accept the HIPAA privacy notice")
    private Boolean hipaaPrivacyNotice;

}
