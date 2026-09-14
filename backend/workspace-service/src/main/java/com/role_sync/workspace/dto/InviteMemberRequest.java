package com.role_sync.workspace.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * An admin adds someone by email. Checked by {@code MemberAccess} (with messages people can
 * read) rather than bean validation.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class InviteMemberRequest {

    private String email;

    @JsonProperty("first_name")
    private String firstName;

    @JsonProperty("last_name")
    private String lastName;

    /** ADMIN, MEMBER or VIEWER; MEMBER when omitted. */
    @JsonProperty("role_name")
    private String roleName;
}
