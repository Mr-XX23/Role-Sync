import type { AssignableRole, InviteResult, Member, MemberRole } from '../../../api/membersApi';

export const ROLE_META: Record<MemberRole, { label: string; description: string; badge: string }> = {
  OWNER: {
    label: 'Owner',
    description: 'Created the workspace. Manages everyone, including admins.',
    badge: 'bg-primary/10 text-primary border-primary/20',
  },
  ADMIN: {
    label: 'Admin',
    description: 'Adds and manages members and viewers, edits workspace settings, and does everything a member can.',
    badge: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20',
  },
  MEMBER: {
    label: 'Member',
    description: 'Works with deals, products, documents and the sales agent.',
    badge: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
  },
  VIEWER: {
    label: 'Viewer',
    description: 'Can see the workspace but can’t change anything.',
    badge: 'bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-500/20',
  },
};

export type StatusKey = 'active' | 'pending' | 'expired' | 'deactivated';

export const STATUS_META: Record<StatusKey, { label: string; badge: string }> = {
  active: { label: 'Active', badge: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20' },
  pending: { label: 'Invite pending', badge: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20' },
  expired: { label: 'Invite expired', badge: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20' },
  deactivated: { label: 'Deactivated', badge: 'bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-500/20' },
};

export function memberStatus(member: Member): StatusKey {
  if (!member.active) return 'deactivated';
  if (member.invite_status === 'EXPIRED') return 'expired';
  if (member.invite_status === 'PENDING') return 'pending';
  return 'active';
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  return ((parts[0][0] ?? '') + (parts.length > 1 ? parts[parts.length - 1][0] ?? '' : '')).toUpperCase();
}

/** The services store times in UTC without a zone designator. */
export function parseServerTime(value: string | null | undefined): Date | null {
  if (!value) return null;
  const withZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
  const date = new Date(withZone);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value: string | null | undefined): string {
  const date = parseServerTime(value);
  if (!date) return '—';
  return date.toLocaleDateString([], {
    day: 'numeric',
    month: 'short',
    year: date.getFullYear() === new Date().getFullYear() ? undefined : 'numeric',
  });
}

export function formatDateTime(value: string | null | undefined): string {
  const date = parseServerTime(value);
  if (!date) return '—';
  return date.toLocaleString([], { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/** "just now", "5 min ago", "3 h ago", "2 days ago", then a date. */
export function timeAgo(value: string | null | undefined, now = Date.now()): string {
  const date = parseServerTime(value);
  if (!date) return '—';
  const minutes = Math.round((now - date.getTime()) / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? '' : 's'} ago`;
  return formatDate(value);
}

export const EMAIL_REGEX = /^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

export interface NewUserForm {
  firstName: string;
  lastName: string;
  email: string;
  role: AssignableRole;
}

export type NewUserErrors = Partial<Record<'firstName' | 'lastName' | 'email', string>>;

/** The same limits the server applies. */
export function validateNewUser(form: NewUserForm): NewUserErrors {
  const errors: NewUserErrors = {};
  const firstName = form.firstName.trim();
  const lastName = form.lastName.trim();
  const email = form.email.trim();
  if (!firstName) errors.firstName = 'Enter a first name.';
  else if (firstName.length > 50) errors.firstName = 'First names can be at most 50 characters.';
  if (lastName.length > 50) errors.lastName = 'Last names can be at most 50 characters.';
  if (!email) errors.email = 'Enter an email address.';
  else if (email.length > 100) errors.email = 'Email addresses can be at most 100 characters.';
  else if (!EMAIL_REGEX.test(email)) errors.email = 'Enter a valid email address, like name@company.com.';
  return errors;
}

export type Tone = 'success' | 'warning' | 'info';

/** What to tell the admin after adding someone or resending their sign-in details. */
export function describeInviteResult(result: InviteResult, email: string, resend = false): { tone: Tone; message: string } {
  const role = ROLE_META[result.member.role]?.label ?? 'Member';
  const who = result.member.name && result.member.name !== email ? `${result.member.name} (${email})` : email;
  if (resend) {
    if (result.email_status === 'SENT') return { tone: 'success', message: `New sign-in details were emailed to ${email}.` };
    if (result.email_status === 'PENDING') return { tone: 'info', message: `New sign-in details are on their way to ${email}.` };
    return {
      tone: 'warning',
      message: `The email to ${email} couldn't be sent${result.email_message ? `: ${result.email_message}` : '.'} Try again later.`,
    };
  }
  const added = result.reactivated ? `${who} was added back as ${role}.` : `${who} was added as ${role}.`;
  if (result.email_status === 'FAILED') {
    return {
      tone: 'warning',
      message: result.credentials_sent
        ? `${added} Their sign-in details couldn't be emailed${result.email_message ? ` (${result.email_message})` : ''}. Use “Resend invite” to try again.`
        : `${added} The notification email couldn't be sent${result.email_message ? ` (${result.email_message})` : ''}.`,
    };
  }
  if (result.email_status === 'PENDING') {
    return { tone: 'info', message: `${added} The email is on its way.` };
  }
  return {
    tone: 'success',
    message: result.credentials_sent
      ? `${added} Their sign-in details were emailed to them.`
      : `${added} They already had an account, so we emailed them that they now have access.`,
  };
}
