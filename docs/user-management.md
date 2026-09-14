# User Management

Workspace owners and admins add people to their workspace, choose their role, and remove access
when they leave. Everything runs through existing services: workspace-service decides who may do
what, and auth-service owns sign-in accounts and sends the emails.

## What admins can do

The **User Management** page (`/salesman/users`) appears in the sidebar for the workspace's OWNER and
ADMINs only.

| Action | Who | Notes |
|---|---|---|
| Add a user by email | Owner, admins | Admins can add members and viewers; only the owner can add admins. |
| Change a role | Owner, admins | Nobody changes their own role; only the owner changes an admin's role; the owner can't be changed. |
| Deactivate / reactivate | Owner, admins | Deactivated members keep their work in the workspace but can't open it. |
| Remove from workspace | Owner, admins | Deletes the membership. The account and the person's deals, notes and documents stay. |
| Resend invite | Owner, admins | Only for people whose sign-in details this workspace sent and who haven't chosen a password yet. |
| Activity | Owner, admins | Who added, changed, deactivated or removed whom. |

The **Roles & permissions** tab lists what each role can do, matching what the services enforce.

## Adding someone

1. The admin enters a name, an email and a role.
2. workspace-service checks the admin's role, then asks auth-service for the account with that email.
   - **No account:** auth-service creates one that is already verified and active (role `SALESMAN`,
     email lowercased) with an unknown random password, then emails a **temporary password**
     (16 characters, valid for 7 days). Only its hash is stored and it is never logged.
   - **Account never signed in with** (still on a temporary password): new sign-in details are sent.
   - **Account in use:** nothing about the account changes. The person gets a "you were added" email and
     can switch to the workspace from the header's workspace menu.
3. The membership is created (or a deactivated one restored) and the change is logged.
4. The page shows whether the email was sent. If sending failed, the person is still added and the
   admin can use **Resend invite**.

## First sign-in

- Sign-in with a temporary password works, and the response has `mustChangePassword: true`. The app
  then only shows **Choose your password** until they pick their own password (min. 12 characters,
  upper and lower case, a number and a symbol).
- `POST /api/v1/auth/change-password` (`currentPassword`, `newPassword`) checks the current password,
  counts wrong ones towards the sign-in lockout, and signs out every other session.
- After the temporary password expires, sign-in is refused with a message asking for a new invitation.
- Accounts created by an admin only work in workspaces they are added to. No personal workspace is
  created for them, so someone deactivated or removed everywhere sees "You don't have access to any
  workspace right now".

## API

workspace-service, through the gateway (caller must be OWNER or ADMIN of the workspace):

| Method | Path | Body |
|---|---|---|
| GET | `/api/v1/workspaces/{id}/members` | |
| POST | `/api/v1/workspaces/{id}/members/invite` | `email`, `first_name`, `last_name`, `role_name` |
| PUT | `/api/v1/workspaces/{id}/members/{membershipId}/role` | `role_name` |
| PUT | `/api/v1/workspaces/{id}/members/{membershipId}/status` | `active` |
| DELETE | `/api/v1/workspaces/{id}/members/{membershipId}` | |
| POST | `/api/v1/workspaces/{id}/members/{membershipId}/resend-invite` | |
| GET | `/api/v1/workspaces/{id}/members/activity?limit=50` | |

`POST /api/v1/workspaces/{id}/members` (add an existing profile by `profile_id`) still exists and
follows the same rules.

auth-service internal API, used only by workspace-service: `/internal/v1/accounts/**` (`provision`,
`{id}/temporary-password`, `{id}/workspace-access-email`, `lookup`). The gateway does not route
`/internal`, and every call must carry the `X-Internal-Token` header.

## Configuration

Add to `backend/.env` (both services read it) and recreate `auth-service` and `workspace-service`:

```
INTERNAL_SERVICE_TOKEN=<long random value, e.g. 64 hex characters>
```

Without it the internal API is off and adding users answers "User management isn't set up yet".

Optional:

| Variable | Default | Used by |
|---|---|---|
| `TEMP_PASSWORD_VALIDITY_DAYS` | `7` | auth-service |
| `AUTH_SERVICE_INTERNAL_URL` | `http://auth-service:8082` | workspace-service |

Emails go out through the existing SMTP settings, and their links point at `FRONTEND_URL`.

Schema changes are applied by Hibernate (`ddl-auto=update`) and every new column is nullable:
`auth_user_credentials.must_change_password`, `temp_password_expires_at`, `provisioned_by`;
`workspace_memberships.invited_by_profile_id`, `account_created`; `workspace_profiles.managed_account`;
and the new table `workspace_member_events`.

## Known limits

- The gateway and sales-agent-engine don't check token revocation, so the "sign out other sessions"
  step on password change is enforced by auth-service only. Workspace access itself is re-checked on
  every request (data-pipeline caches memberships for up to 60 seconds).
- The platform-level `role` column in auth-service (`ADMIN`, `SUPER_ADMIN`…) is not used for any of
  this. Workspace roles are.
