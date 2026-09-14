import api from './axiosInstance';
import { getActiveTenantId } from './catalogApi';

// ============================================================================
// Types (mirror backend/workspace-service dto/MemberResponse.java, MemberListResponse.java,
// InviteMemberResponse.java, MemberActivityResponse.java)
// ============================================================================

export const MEMBER_ROLES = ['OWNER', 'ADMIN', 'MEMBER', 'VIEWER'] as const;
export type MemberRole = (typeof MEMBER_ROLES)[number];
export type AssignableRole = Exclude<MemberRole, 'OWNER'>;

export interface Member {
  membership_id: string;
  profile_id: string;
  auth_user_id: string;
  name: string;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  job_title: string | null;
  email: string | null; // null when sign-in details couldn't be loaded
  role: MemberRole;
  is_owner: boolean;
  is_you: boolean;
  active: boolean; // false: deactivated
  joined_at: string;
  invited_by_name: string | null;
  account_status: string | null;
  last_sign_in_at: string | null;
  invite_status: 'PENDING' | 'EXPIRED' | null; // still on the emailed temporary password
  invite_expires_at: string | null;
  can_change_role: boolean;
  can_deactivate: boolean;
  can_remove: boolean;
  can_resend_invite: boolean;
  assignable_roles: AssignableRole[];
}

export interface MemberList {
  workspace_id: string;
  workspace_name: string;
  your_role: MemberRole;
  assignable_roles: AssignableRole[]; // roles you can give people you add
  account_details_available: boolean;
  members: Member[];
}

export interface NewMemberInput {
  email: string;
  first_name: string;
  last_name: string | null;
  role_name: AssignableRole;
}

export type EmailStatus = 'SENT' | 'FAILED' | 'PENDING';

export interface InviteResult {
  member: Member;
  account_created: boolean; // a new sign-in account was created
  reactivated: boolean; // a deactivated member was restored
  credentials_sent: boolean; // sign-in details were emailed (not just a "you were added" notice)
  email_status: EmailStatus;
  email_message: string | null;
  invite_expires_at: string | null;
}

export type MemberAction =
  | 'MEMBER_ADDED'
  | 'ROLE_CHANGED'
  | 'MEMBER_DEACTIVATED'
  | 'MEMBER_REACTIVATED'
  | 'MEMBER_REMOVED'
  | 'INVITE_RESENT';

export interface MemberActivity {
  event_id: string;
  action: MemberAction;
  actor_name: string | null;
  target_name: string | null;
  target_email: string | null;
  from_role: MemberRole | null;
  to_role: MemberRole | null;
  created_at: string;
}

// ============================================================================
// API
// ============================================================================

function membersPath(): string {
  const workspaceId = getActiveTenantId();
  if (!workspaceId) {
    throw new Error('Pick or create a workspace first.');
  }
  return `/workspaces/${workspaceId}/members`;
}

export const membersApi = {
  list: async (): Promise<MemberList> => {
    const response = await api.get<MemberList>(membersPath());
    return response.data;
  },

  /** Adds someone by email. Without an account they get a verified one and sign-in details by email. */
  invite: async (input: NewMemberInput): Promise<InviteResult> => {
    // Creating the account and sending the email can take a while when the mail server is slow.
    const response = await api.post<InviteResult>(`${membersPath()}/invite`, input, { timeout: 60000 });
    return response.data;
  },

  changeRole: async (membershipId: string, role: AssignableRole): Promise<void> => {
    await api.put(`${membersPath()}/${encodeURIComponent(membershipId)}/role`, { role_name: role });
  },

  setActive: async (membershipId: string, active: boolean): Promise<Member> => {
    const response = await api.put<Member>(`${membersPath()}/${encodeURIComponent(membershipId)}/status`, { active });
    return response.data;
  },

  remove: async (membershipId: string): Promise<void> => {
    await api.delete(`${membersPath()}/${encodeURIComponent(membershipId)}`);
  },

  resendInvite: async (membershipId: string): Promise<InviteResult> => {
    const response = await api.post<InviteResult>(
      `${membersPath()}/${encodeURIComponent(membershipId)}/resend-invite`,
      null,
      { timeout: 60000 }
    );
    return response.data;
  },

  activity: async (limit = 100): Promise<MemberActivity[]> => {
    const response = await api.get<MemberActivity[]>(`${membersPath()}/activity`, { params: { limit } });
    return response.data;
  },
};

export function memberErrorStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } })?.response?.status;
}

/** Human-readable message for a user management error response. */
export function describeMemberError(error: unknown): string {
  const response = (error as { response?: { status?: number; data?: { message?: string } } })?.response;
  if (!response) {
    if ((error as { code?: string })?.code === 'ECONNABORTED') {
      return 'The server took too long to answer. Check the member list before trying again.';
    }
    return error instanceof Error && error.message !== 'Network Error' ? error.message : 'User management could not be reached.';
  }
  if (response.status === 403) {
    return response.data?.message || 'You need to be a workspace owner or admin to manage users.';
  }
  return response.data?.message || 'Something went wrong. Try again.';
}
