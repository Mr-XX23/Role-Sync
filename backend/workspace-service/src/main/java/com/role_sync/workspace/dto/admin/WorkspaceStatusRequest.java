package com.role_sync.workspace.dto.admin;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/** {"active": false, "reason": "..."} suspends a workspace; {"active": true} reactivates it. */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class WorkspaceStatusRequest {

    private Boolean active;

    /** Optional, at most 500 characters; goes into the audit trail. */
    private String reason;
}
