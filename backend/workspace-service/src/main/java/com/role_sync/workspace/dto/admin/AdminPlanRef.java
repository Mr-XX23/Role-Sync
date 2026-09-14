package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminPlanRef {

    @JsonProperty("plan_id")
    private UUID planId;

    private String code;

    private String name;

    @JsonProperty("is_default")
    private boolean defaultPlan;
}
