import api from './axiosInstance';
import { getActiveTenantId } from './catalogApi';

// ============================================================================
// Billing & credits API. Mirrors docs/billing/credit-system-api.md (backend/billing-service).
// Credits belong to a workspace (sent as `X-Tenant-Id`) and are numbers with up to three decimals;
// money is always an integer in the currency's minor unit. Public pricing needs no session; the
// admin calls need a platform super admin, which the server checks.
// ============================================================================

export type CreditStatus = 'ACTIVE' | 'SUSPENDED';
export type UsageCategory = 'AGENT' | 'SEARCH' | 'DOCUMENTS' | 'CONNECTORS' | 'CATALOG' | 'OTHER';
export type OrderStatus = 'CREATED' | 'PENDING' | 'SUCCEEDED' | 'FAILED' | 'EXPIRED' | 'REFUNDED';
export type TransactionType =
  | 'WELCOME_GRANT'
  | 'PURCHASE'
  | 'ADMIN_GRANT'
  | 'ADMIN_DEDUCT'
  | 'USAGE'
  | 'REFUND_CLAWBACK'
  | 'ACCOUNT_SUSPENDED'
  | 'ACCOUNT_REACTIVATED';

export const ORDER_STATUSES: OrderStatus[] = ['CREATED', 'PENDING', 'SUCCEEDED', 'FAILED', 'EXPIRED', 'REFUNDED'];
/** An order in one of these states won't change any more. */
export const FINAL_ORDER_STATUSES: OrderStatus[] = ['SUCCEEDED', 'FAILED', 'EXPIRED', 'REFUNDED'];

export interface CreditPackage {
  code: string;
  name: string;
  credits: number;
  priceMinor: number;
  currency: string;
}

export interface CreditExample {
  label: string;
  credits: number;
}

export interface PublicPricing {
  currency: string;
  signupCredits: number;
  creditPriceUsd: number;
  packages: CreditPackage[];
  examples: CreditExample[];
}

export interface PackageList {
  packages: CreditPackage[];
  providers: string[];
}

export interface CreditBalance {
  workspaceId: string;
  balance: number;
  status: CreditStatus;
  lowBalance: boolean;
  lowBalanceThreshold: number;
  /** Grants, purchases and admin additions. */
  lifetimeCredited: number;
  lifetimeUsed: number;
}

export interface CategoryUsage {
  category: UsageCategory;
  label: string;
  credits: number;
  /** Share of the period's use, 0–100. */
  percent: number;
  /** Provider cost behind these credits (admin reports only). */
  costUsd?: number;
}

export interface UsageSummary {
  workspaceId: string;
  periodDays: number;
  from: string;
  to: string;
  balance: number;
  lifetimeCredited: number;
  lifetimeUsed: number;
  /** lifetimeUsed ÷ lifetimeCredited × 100, one decimal. */
  usedPercent: number;
  periodUsed: number;
  /** Every category, zeros included. */
  categories: CategoryUsage[];
}

export interface PaymentOrder {
  orderId: string;
  packageCode: string;
  credits: number;
  amountMinor: number;
  currency: string;
  provider: string;
  status: OrderStatus;
  checkoutUrl: string | null;
  failureReason: string | null;
  paidAt: string | null;
  createdAt: string;
}

// ----------------------------------------------------------------------------- super admin

export interface BillingPage<T> {
  items: T[];
  page: number;
  size: number;
  total: number;
}

export interface CreditAccount {
  workspaceId: string;
  balance: number;
  status: CreditStatus;
  lifetimeCredited: number;
  lifetimeUsed: number;
  lifetimePurchased: number;
  suspendedReason: string | null;
  /** Sent by billing-service, not in the contract. */
  suspendedAt?: string | null;
  lastActivityAt: string | null;
  createdAt: string;
}

export interface CreditTransaction {
  id: string;
  type: TransactionType;
  /** Signed: positive added credits, negative removed them. */
  credits: number;
  balanceAfter: number;
  operation: string | null;
  category: UsageCategory | null;
  reason: string | null;
  actorUserId: string | null;
  reference: string | null;
  createdAt: string;
}

/** `GET /admin/accounts/{workspaceId}`: the account, its latest ledger lines and the last 30 days by category. */
export interface AdminAccountDetail {
  account: CreditAccount;
  transactions: CreditTransaction[];
  usageByCategory: CategoryUsage[];
}

/**
 * An order in the cross-workspace payments list. billing-service sends the user order shape, which
 * doesn't say which workspace bought it; the page shows the workspace when these arrive.
 */
export interface AdminPaymentOrder extends PaymentOrder {
  workspaceId?: string | null;
  userId?: string | null;
}

export interface RevenueLine {
  currency: string;
  amountMinor: number;
  /** Successful payments in this currency. */
  payments: number;
}

export interface DailyCreditUsage {
  date: string; // UTC day, "2026-09-14"
  credits: number;
  costUsd: number;
}

export interface WorkspaceCreditUsage {
  workspaceId: string;
  credits: number;
  costUsd: number;
}

/** `GET /admin/overview?days=`: everything since `from`. */
export interface AdminBillingOverview {
  periodDays: number;
  from: string;
  /** Succeeded payments per currency. */
  revenue: RevenueLine[];
  /** The USD part of `revenue`, in dollars (margin is worked out from it). */
  revenueUsd: number;
  successfulPayments: number;
  creditsSold: number;
  /** Welcome and admin grants. */
  creditsGranted: number;
  creditsUsed: number;
  providerCostUsd: number;
  /** (revenueUsd − providerCostUsd) ÷ revenueUsd × 100; null without USD revenue. */
  grossMarginPercent: number | null;
  /** Credits still held in positive balances, platform-wide. */
  outstandingCredits: number;
  accounts: number;
  suspendedAccounts: number;
  negativeBalanceAccounts: number;
  usageByCategory: CategoryUsage[];
  dailyUsage: DailyCreditUsage[];
  topWorkspaces: WorkspaceCreditUsage[];
}

export interface OperationUsage {
  operation: string;
  category: UsageCategory;
  count: number;
  credits: number;
  costUsd: number;
}

export interface ModelUsage {
  model: string;
  calls: number;
  inputTokens: number;
  cachedInputTokens: number;
  outputTokens: number;
  credits: number;
  costUsd: number;
}

/** `GET /admin/usage?days=&workspaceId=`: usage by category, by operation and by model. */
export interface AdminBillingUsage {
  periodDays: number;
  workspaceId: string | null;
  byCategory: CategoryUsage[];
  byOperation: OperationUsage[];
  byModel: ModelUsage[];
}

export interface AccountFilters {
  query?: string;
  status?: CreditStatus | '';
  page: number;
  size: number;
}

export interface PaymentFilters {
  status?: OrderStatus | '';
  page: number;
  size: number;
}

// ============================================================================
// Calls
// ============================================================================

const BASE = '/billing';
const ADMIN = '/billing/admin';

/** Billing refuses a workspace call without a workspace, so fail before sending one. */
function inWorkspace(workspaceId?: string): { 'X-Tenant-Id': string } {
  const tenantId = getActiveTenantId(workspaceId);
  if (!tenantId) {
    throw new Error('Pick or create a workspace first.');
  }
  return { 'X-Tenant-Id': tenantId };
}

/** Drops empty filters so the server only sees what was chosen. */
function params(filters: object): Record<string, string | number> {
  return Object.fromEntries(
    Object.entries(filters).filter(([, value]) => value !== undefined && value !== null && value !== '')
  ) as Record<string, string | number>;
}

const id = (value: string) => encodeURIComponent(value);

/**
 * A new idempotency key for one checkout click. `crypto.randomUUID` only exists on secure origins,
 * and the dev server is also opened over plain http on the local network.
 */
export function newIdempotencyKey(): string {
  const cryptoApi = globalThis.crypto;
  if (typeof cryptoApi?.randomUUID === 'function') {
    return cryptoApi.randomUUID();
  }
  const bytes = new Uint8Array(16);
  if (typeof cryptoApi?.getRandomValues === 'function') {
    cryptoApi.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) bytes[index] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export const billingApi = {
  /** Packs, the sign-up offer and example costs. Works without signing in. */
  publicPricing: async (): Promise<PublicPricing> => (await api.get<PublicPricing>(`${BASE}/public/pricing`)).data,

  /** The workspace's balance; the first call creates the account and applies the welcome grant. */
  credits: async (workspaceId?: string): Promise<CreditBalance> =>
    (await api.get<CreditBalance>(`${BASE}/credits`, { headers: inWorkspace(workspaceId) })).data,

  usageSummary: async (days: number): Promise<UsageSummary> =>
    (await api.get<UsageSummary>(`${BASE}/usage/summary`, { params: { days }, headers: inWorkspace() })).data,

  packages: async (): Promise<PackageList> =>
    (await api.get<PackageList>(`${BASE}/packages`, { headers: inWorkspace() })).data,

  /**
   * Starts a purchase for the active workspace; send the browser to the returned `checkoutUrl`. The
   * idempotency key travels in the body: the gateway's CORS allow-list has no `Idempotency-Key` header.
   */
  checkout: async (packageCode: string, idempotencyKey: string = newIdempotencyKey()): Promise<PaymentOrder> =>
    (await api.post<PaymentOrder>(`${BASE}/checkout`, { packageCode, idempotencyKey }, { headers: inWorkspace() })).data,

  /** One order. Billing checks membership of the workspace that bought it, so no active workspace is needed. */
  order: async (orderId: string): Promise<PaymentOrder> => {
    const tenantId = getActiveTenantId();
    return (
      await api.get<PaymentOrder>(`${BASE}/orders/${id(orderId)}`, tenantId ? { headers: { 'X-Tenant-Id': tenantId } } : undefined)
    ).data;
  },

  orders: async (): Promise<PaymentOrder[]> =>
    (await api.get<PaymentOrder[]>(`${BASE}/orders`, { headers: inWorkspace() })).data,

  admin: {
    overview: async (days: number): Promise<AdminBillingOverview> =>
      (await api.get<AdminBillingOverview>(`${ADMIN}/overview`, { params: { days } })).data,

    accounts: async (filters: AccountFilters): Promise<BillingPage<CreditAccount>> =>
      (await api.get<BillingPage<CreditAccount>>(`${ADMIN}/accounts`, { params: params(filters) })).data,

    account: async (workspaceId: string): Promise<AdminAccountDetail> =>
      (await api.get<AdminAccountDetail>(`${ADMIN}/accounts/${id(workspaceId)}`)).data,

    grant: async (workspaceId: string, credits: number, reason: string): Promise<CreditAccount> =>
      (await api.post<CreditAccount>(`${ADMIN}/accounts/${id(workspaceId)}/grant`, { credits, reason })).data,

    deduct: async (workspaceId: string, credits: number, reason: string, allowNegative: boolean): Promise<CreditAccount> =>
      (await api.post<CreditAccount>(`${ADMIN}/accounts/${id(workspaceId)}/deduct`, { credits, reason, allowNegative })).data,

    suspend: async (workspaceId: string, reason: string): Promise<CreditAccount> =>
      (await api.post<CreditAccount>(`${ADMIN}/accounts/${id(workspaceId)}/suspend`, { reason })).data,

    reactivate: async (workspaceId: string, reason: string): Promise<CreditAccount> =>
      (await api.post<CreditAccount>(`${ADMIN}/accounts/${id(workspaceId)}/reactivate`, { reason })).data,

    payments: async (filters: PaymentFilters): Promise<BillingPage<AdminPaymentOrder>> =>
      (await api.get<BillingPage<AdminPaymentOrder>>(`${ADMIN}/payments`, { params: params(filters) })).data,

    usage: async (days: number, workspaceId?: string): Promise<AdminBillingUsage> =>
      (await api.get<AdminBillingUsage>(`${ADMIN}/usage`, { params: params({ days, workspaceId }) })).data,
  },
};

// ============================================================================
// Errors
// ============================================================================

export function billingErrorStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } })?.response?.status;
}

/**
 * The stable code billing-service puts next to its message, e.g. `CREDITS_SUSPENDED` (a 409 from
 * checkout, which is not a 402) or `INSUFFICIENT_BALANCE` (a 409 from an admin deduction).
 */
export function billingErrorCode(error: unknown): string | null {
  const data = (error as { response?: { data?: unknown } })?.response?.data;
  if (!data || typeof data !== 'object') return null;
  const body = data as { code?: unknown; detail?: { code?: unknown } };
  const code = body.code ?? (body.detail && typeof body.detail === 'object' ? body.detail.code : undefined);
  return typeof code === 'string' && code ? code : null;
}

/** Spring's default error body puts the bare reason phrase in `error`; that says less than our own text. */
const REASON_PHRASE = /^(bad request|unauthorized|payment required|forbidden|not found|conflict|internal server error|bad gateway|service unavailable|gateway timeout)$/i;

function readable(value: unknown): string | null {
  return typeof value === 'string' && value.trim() && !REASON_PHRASE.test(value.trim()) ? value.trim() : null;
}

/**
 * A message for whatever went wrong with a billing call. billing-service answers `{"error"}` (and
 * `{"code", "error"}` for credits), Spring's defaults `{"message"}`, FastAPI `{"detail"}`.
 * `audience` picks the wording for a 403.
 */
export function describeBillingError(error: unknown, audience: 'workspace' | 'admin' = 'workspace'): string {
  const response = (error as { response?: { status?: number; data?: unknown } })?.response;
  if (!response) {
    if (error instanceof Error && !('request' in error) && !('response' in error)) {
      return error.message;
    }
    if ((error as { code?: string })?.code === 'ECONNABORTED') {
      return 'Billing took too long to answer. Try again.';
    }
    return 'Billing could not be reached. Check your connection and try again.';
  }
  const data = (response.data && typeof response.data === 'object' ? response.data : {}) as Record<string, unknown>;
  const detail = data.detail && typeof data.detail === 'object' ? (data.detail as Record<string, unknown>) : {};
  const message = readable(data.message) ?? readable(data.error) ?? readable(data.detail) ?? readable(detail.message);
  if (response.status === 403) {
    return audience === 'admin'
      ? message ?? 'Only platform super admins can do this.'
      : message ?? 'You are not a member of this workspace.';
  }
  if (message) {
    return message;
  }
  switch (response.status) {
    case 400:
      return 'Check the details and try again.';
    case 401:
      return 'Your session has expired. Sign in again.';
    case 402:
      return 'Your workspace is out of credits.';
    case 404:
      return 'That no longer exists. Refresh the page.';
    case 409:
      return 'That conflicts with the account as it is now. Refresh and try again.';
    case 429:
      return 'Too many requests. Wait a moment and try again.';
    case 502:
    case 503:
    case 504:
      return 'Billing is unavailable right now. Try again shortly.';
    default:
      return 'Something went wrong. Try again.';
  }
}
