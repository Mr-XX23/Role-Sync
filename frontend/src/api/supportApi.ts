import api from './axiosInstance';
import { getActiveTenantId } from './catalogApi';

// ============================================================================
// Support Desk API. Mirrors backend/workspace-service WorkspaceSupportTicketController:
// members file tickets with the RoleSync team and follow the answers; the team replies and
// changes statuses from the Super Admin Console (see adminApi.ts).
// ============================================================================

export type SupportTicketStatus = 'OPEN' | 'IN_PROGRESS' | 'RESOLVED' | 'CLOSED';

export interface SupportTicketMessage {
  messageId: string;
  authorName: string;
  /** Written by the RoleSync team. */
  fromSupport: boolean;
  /** Written by the signed-in person. */
  mine: boolean;
  body: string;
  createdAt: string;
}

export interface SupportTicket {
  ticketId: string;
  workspaceId: string;
  subject: string;
  description: string;
  status: SupportTicketStatus;
  reporter: { profileId: string; name: string; mine: boolean };
  /** Replies on the ticket (the description itself is not one). */
  messageCount: number;
  lastMessageAt: string | null;
  /** The RoleSync team wrote last. */
  lastMessageFromSupport: boolean;
  /** false once the ticket is closed. */
  canReply: boolean;
  createdAt: string;
  updatedAt: string;
  closedAt: string | null;
  /** Only present when one ticket was asked for, not in lists. */
  messages: SupportTicketMessage[] | null;
}

function ticketsPath(): string {
  const workspaceId = getActiveTenantId();
  if (!workspaceId) {
    throw new Error('Pick or create a workspace first.');
  }
  return `/workspaces/${workspaceId}/support-tickets`;
}

export const supportApi = {
  /** Files a new ticket; the answer has no messages yet. */
  create: async (subject: string, description: string): Promise<SupportTicket> =>
    (await api.post<SupportTicket>(ticketsPath(), { subject, description })).data,

  /** The signed-in person's tickets, newest first; `everyone` gives a workspace owner/admin the whole workspace's. */
  list: async (everyone = false, limit = 50): Promise<SupportTicket[]> =>
    (await api.get<SupportTicket[]>(ticketsPath(), { params: { everyone, limit } })).data,

  /** One ticket with its conversation. */
  get: async (ticketId: string): Promise<SupportTicket> =>
    (await api.get<SupportTicket>(`${ticketsPath()}/${encodeURIComponent(ticketId)}`)).data,

  /** Writes back on a ticket; writing on a resolved one reopens it. */
  reply: async (ticketId: string, body: string): Promise<SupportTicket> =>
    (await api.post<SupportTicket>(`${ticketsPath()}/${encodeURIComponent(ticketId)}/messages`, { body })).data,
};

/** A message for the person, whatever went wrong. */
export function describeSupportError(error: unknown): string {
  if (error instanceof Error && !('response' in error) && !('request' in error)) {
    return error.message;
  }
  const response = (error as { response?: { status?: number; data?: { message?: unknown } } })?.response;
  if (!response) {
    return 'The server could not be reached. Check your connection and try again.';
  }
  const message = response.data?.message;
  if (typeof message === 'string' && message.trim()) {
    return message;
  }
  switch (response.status) {
    case 401:
      return 'Your session has expired. Sign in again.';
    case 403:
      return 'You are not a member of this workspace.';
    case 404:
      return 'That ticket no longer exists.';
    case 409:
      return 'This ticket is closed. Open a new one if you still need help.';
    case 429:
      return 'Too many requests. Wait a moment and try again.';
    default:
      return 'Something went wrong. Try again.';
  }
}
