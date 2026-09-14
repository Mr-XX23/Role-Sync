import type { AccountStatus, AdminUser, LoginType } from '../../api/adminApi';
import type { Tone } from './components/AdminUi';

export const STATUS_META: Record<AccountStatus, { label: string; tone: Tone; description: string }> = {
  ACTIVE: { label: 'Active', tone: 'success', description: 'Can sign in.' },
  INACTIVE: { label: 'Not activated', tone: 'neutral', description: 'Signed up but hasn’t verified their email yet.' },
  SUSPENDED: { label: 'Suspended', tone: 'danger', description: 'Blocked by a super admin. Can’t sign in.' },
  LOCKED: { label: 'Locked', tone: 'warning', description: 'Locked after failed sign-ins.' },
};

export const LOGIN_TYPE_LABEL: Record<LoginType, string> = {
  EMAIL: 'Email & password',
  PHONE: 'Phone',
  THIRD_PARTY: 'Google',
  BOTH: 'Email & Google',
};

export const SECURITY_EVENT_LABEL: Record<string, string> = {
  SUCCESSFUL_LOGIN: 'Signed in',
  OAUTH2_LOGIN: 'Signed in with Google',
  FAILED_LOGIN: 'Failed sign-in',
  FAILED_LOGIN_LOCKED: 'Sign-in blocked (locked)',
  TOKEN_REFRESH_SUCCESS: 'Session refreshed',
  FAILED_TOKEN_REFRESH: 'Session refresh failed',
  PASSWORD_CHANGED: 'Changed password',
  PASSWORD_CHANGE_FAILED: 'Password change failed',
  TEMP_PASSWORD_ISSUED: 'Temporary password emailed',
  TEMP_PASSWORD_EXPIRED_LOGIN: 'Tried an expired temporary password',
  ADMIN_ACCOUNT_CREATED: 'Account created by a workspace admin',
  USER_REGISTRATION_SUCCESS: 'Signed up',
  FORCED_LOGOUT: 'Signed out by an admin',
};

export function userDisplayName(user: Pick<AdminUser, 'username' | 'email'>): string {
  return user.username?.trim() || user.email;
}
