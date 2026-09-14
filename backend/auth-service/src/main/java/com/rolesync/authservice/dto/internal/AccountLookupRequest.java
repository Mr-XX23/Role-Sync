package com.rolesync.authservice.dto.internal;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AccountLookupRequest {

    @NotNull(message = "authUserIds is required")
    @Size(max = 1000, message = "At most 1000 accounts can be looked up at once")
    private List<UUID> authUserIds;
}
