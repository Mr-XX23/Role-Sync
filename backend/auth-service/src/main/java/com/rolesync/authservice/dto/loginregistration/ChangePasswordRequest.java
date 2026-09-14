package com.rolesync.authservice.dto.loginregistration;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class ChangePasswordRequest {

    @NotBlank(message = "Enter your current password")
    @Size(max = 256, message = "Current password is too long")
    private String currentPassword;

    @NotBlank(message = "Enter a new password")
    @Size(max = 256, message = "New password is too long")
    private String newPassword;
}
