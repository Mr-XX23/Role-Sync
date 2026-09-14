package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

/**
 * {"plan_id": "uuid"} puts a workspace on a plan; {"plan_id": null} puts it back on the default
 * plan. A body without plan_id is refused rather than read as null.
 */
@Data
@NoArgsConstructor
public class WorkspacePlanRequest {

    private UUID planId;

    /** Whether the body named plan_id at all. */
    @JsonIgnore
    private boolean planIdSent;

    public WorkspacePlanRequest(UUID planId) {
        setPlanId(planId);
    }

    @JsonProperty("plan_id")
    public UUID getPlanId() {
        return planId;
    }

    @JsonProperty("plan_id")
    public void setPlanId(UUID planId) {
        this.planId = planId;
        this.planIdSent = true;
    }
}
