package com.rolesync.authservice.dto.internal;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

/**
 * Whether an account is a platform super admin, for the Super Admin Console guards of other
 * services. An unknown account is simply not one (email null).
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PlatformAccess {

    private UUID authUserId;
    private boolean superAdmin;
    private String email;
}
