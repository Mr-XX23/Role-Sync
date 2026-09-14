import type { AdminBillingOverview, CreditStatus, OrderStatus, TransactionType } from '../../../api/billingApi';
import { formatMoney } from '../../../utils/billingFormat';
import { humanize } from '../adminFormat';
import type { Tone } from '../components/AdminUi';

/** Succeeded revenue per currency: "$120.00 + NPR 1,000.00". */
export function revenueText(overview: AdminBillingOverview | null): string {
  if (!overview) return '—';
  if (overview.revenue.length === 0) return formatMoney(0, 'usd');
  return overview.revenue.map((line) => formatMoney(line.amountMinor, line.currency)).join(' + ');
}

export const ACCOUNT_STATUS_META: Record<CreditStatus, { label: string; tone: Tone }> = {
  ACTIVE: { label: 'Active', tone: 'success' },
  SUSPENDED: { label: 'Suspended', tone: 'danger' },
};

export const ORDER_STATUS_META: Record<OrderStatus, { label: string; tone: Tone; description: string }> = {
  CREATED: { label: 'Created', tone: 'neutral', description: 'Saved, but checkout was never opened' },
  PENDING: { label: 'Pending', tone: 'warning', description: 'Waiting for the payment provider to confirm' },
  SUCCEEDED: { label: 'Succeeded', tone: 'success', description: 'Paid, and the credits were added' },
  FAILED: { label: 'Failed', tone: 'danger', description: 'The payment provider reported a failure' },
  EXPIRED: { label: 'Expired', tone: 'neutral', description: 'Checkout timed out without a payment' },
  REFUNDED: { label: 'Refunded', tone: 'violet', description: 'Refunded after it was paid' },
};

const TRANSACTION_META: Record<TransactionType, { label: string; tone: Tone }> = {
  WELCOME_GRANT: { label: 'Welcome grant', tone: 'primary' },
  PURCHASE: { label: 'Purchase', tone: 'success' },
  ADMIN_GRANT: { label: 'Admin grant', tone: 'info' },
  ADMIN_DEDUCT: { label: 'Admin deduction', tone: 'warning' },
  USAGE: { label: 'Usage', tone: 'neutral' },
  REFUND_CLAWBACK: { label: 'Refund clawback', tone: 'danger' },
  ACCOUNT_SUSPENDED: { label: 'Suspended', tone: 'danger' },
  ACCOUNT_REACTIVATED: { label: 'Reactivated', tone: 'success' },
};

export function orderStatusMeta(status: string) {
  return ORDER_STATUS_META[status as OrderStatus] ?? { label: humanize(status), tone: 'neutral' as Tone, description: status };
}

export function transactionMeta(type: string) {
  return TRANSACTION_META[type as TransactionType] ?? { label: humanize(type), tone: 'neutral' as Tone };
}

export const MAX_ADJUSTMENT = 1_000_000;
export const MAX_REASON = 500;

/** The server's rules for a grant or deduction: more than 0, at most 1,000,000, up to 3 decimals. */
export function parseCreditAmount(raw: string): { value: number | null; error: string | null } {
  const text = raw.trim().replace(/[,\s]/g, '');
  if (!text) return { value: null, error: 'Enter how many credits.' };
  if (!/^\d+(\.\d{1,3})?$/.test(text)) return { value: null, error: 'Use a positive number with at most 3 decimals.' };
  const value = Number(text);
  if (!(value > 0)) return { value: null, error: 'Enter more than 0 credits.' };
  if (value > MAX_ADJUSTMENT) return { value: null, error: 'At most 1,000,000 credits at a time.' };
  return { value, error: null };
}
