import type { SupportTicketStatus } from '../../api/adminApi';
import type { Tone } from './components/AdminUi';

/** How each ticket status reads and colours, shared by the admin queue and its drawer. */
export const TICKET_STATUS_META: Record<SupportTicketStatus, { label: string; tone: Tone; description: string }> = {
  OPEN: { label: 'Open', tone: 'warning', description: 'Waiting for the team’s first answer, or reopened by the reporter.' },
  IN_PROGRESS: { label: 'In progress', tone: 'info', description: 'The team has answered and is on it.' },
  RESOLVED: { label: 'Resolved', tone: 'success', description: 'Answered. The reporter can still write back, which reopens it.' },
  CLOSED: { label: 'Closed', tone: 'neutral', description: 'Final. Nobody can write to it; reopen it to continue.' },
};

export const TICKET_STATUSES: SupportTicketStatus[] = ['OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED'];
