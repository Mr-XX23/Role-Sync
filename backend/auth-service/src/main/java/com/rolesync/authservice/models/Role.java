package com.rolesync.authservice.models;

/**
 * Platform-wide account role ({@code auth_user_credentials.role}). Workspace permissions are separate:
 * they come from workspace-service memberships (OWNER, ADMIN, MEMBER, VIEWER).
 *
 * <p>The server always picks the role; no request can choose one. Where each role comes from:
 * <ul>
 *   <li>{@link #USER}: public sign-up ({@code POST /api/v1/auth/register}) and first Google sign-in.</li>
 *   <li>{@link #SALESMAN}: accounts a workspace admin creates through the internal API
 *       ({@code AccountProvisioningService}, guarded by the internal service token).</li>
 *   <li>{@link #ADMIN}, {@link #SUPER_ADMIN}: no application path. Only an operator with database access can
 *       set them, on an existing account.</li>
 *   <li>{@link #TEACHER}, {@link #STUDENT}: not assigned anywhere.</li>
 * </ul>
 *
 * <p>TODO: if ADMIN/SUPER_ADMIN must be granted in the app, add an audited endpoint that only a SUPER_ADMIN can
 * call and that is outside the gateway's public paths. Never read a role from a public request.
 */
public enum Role {
    USER,
    TEACHER,
    STUDENT,
    SALESMAN,
    ADMIN,
    SUPER_ADMIN
}
