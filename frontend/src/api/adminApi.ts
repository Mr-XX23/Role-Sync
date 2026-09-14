import api from './axiosInstance';

// ============================================================================
// Super Admin Console API. Mirrors backend/auth-service (…/admin), workspace-service
// (…/workspaces/admin) and sales-agent-engine (…/sales-agent/admin). Every endpoint checks on
// the server that the caller is a platform super admin; the UI only hides what they can't use.
// ============================================================================

export type AdminService = 'auth' | 'workspace' | 'agent';

export interface Page<T> {
  items: T[];
  page: number;
  size: number;
  total: number;
  total_pages: number;
}

export interface DailyCount {
  date: string; // UTC day, "2026-09-14"
  count: number;
}

export interface AuditEntry {
  id: string;
  service: AdminService;
  actor_user_id: string;
  actor_email: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  target_label: string | null;
  summary: string;
  created_at: string;
}

// ----------------------------------------------------------------------------- auth-service

export type AccountStatus = 'ACTIVE' | 'INACTIVE' | 'SUSPENDED' | 'LOCKED';
export type LoginType = 'EMAIL' | 'PHONE' | 'THIRD_PARTY' | 'BOTH';

export interface AdminUser {
  user_id: string;
  email: string;
  username: string;
  phone_number: string | null;
  status: AccountStatus;
  email_verified: boolean;
  phone_verified: boolean;
  login_type: LoginType;
  super_admin: boolean;
  must_change_password: boolean;
  provisioned: boolean;
  locked_out: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface SecurityEvent {
  event_type: string;
  event_time: string;
  ip_address: string | null;
  user_agent: string | null;
}

export interface AdminUserDetail {
  user: AdminUser;
  active_sessions: number;
  recent_events: SecurityEvent[];
}

export interface UserFilters {
  q?: string;
  status?: AccountStatus | '';
  verified?: 'true' | 'false' | '';
  login_type?: LoginType | '';
  page?: number;
  size?: number;
}

export interface AuthStats {
  total_users: number;
  active: number;
  inactive: number;
  suspended: number;
  locked: number;
  email_verified: number;
  new_last_7_days: number;
  new_last_30_days: number;
  login_types: Partial<Record<LoginType, number>>;
  super_admin_emails: string[];
  signups_daily: DailyCount[];
  sign_ins_daily: DailyCount[];
}

// ----------------------------------------------------------------------------- workspace-service

export interface PlanRef {
  plan_id: string;
  code: string;
  name: string;
  is_default: boolean;
}

export interface AdminWorkspace {
  workspace_id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
  owner: { profile_id: string; auth_user_id: string; name: string; email: string | null } | null;
  member_count: number;
  plan: PlanRef;
  plan_assigned: boolean;
}

export interface AdminWorkspaceMember {
  membership_id: string;
  profile_id: string;
  auth_user_id: string;
  name: string;
  email: string | null;
  role: string;
  active: boolean;
  joined_at: string;
}

export interface AdminMemberEvent {
  event_id: string;
  action: string;
  actor_name: string | null;
  target_name: string | null;
  target_email: string | null;
  from_role: string | null;
  to_role: string | null;
  created_at: string;
}

export interface AdminWorkspaceDetail {
  workspace: AdminWorkspace;
  members: AdminWorkspaceMember[];
  counts: { deals: number; open_deals: number; contexts: number; notes: number };
  recent_member_events: AdminMemberEvent[];
}

export interface WorkspaceFilters {
  q?: string;
  status?: 'active' | 'suspended' | '';
  plan_id?: string;
  page?: number;
  size?: number;
}

export interface UserWorkspace {
  workspace_id: string;
  name: string;
  is_active: boolean;
  role: string;
  membership_active: boolean;
  is_owner: boolean;
  joined_at: string;
}

export interface AdminPlan {
  plan_id: string;
  code: string;
  name: string;
  description: string | null;
  price_monthly_cents: number | null;
  currency: string;
  max_members: number | null;
  agent_tokens_per_day: number | null;
  max_concurrent_agent_runs: number | null;
  is_default: boolean;
  is_archived: boolean;
  sort_order: number;
  workspace_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface PlanInput {
  code: string;
  name: string;
  description: string | null;
  price_monthly_cents: number | null;
  currency: string;
  max_members: number | null;
  agent_tokens_per_day: number | null;
  max_concurrent_agent_runs: number | null;
  sort_order: number;
}

export interface WorkspaceStats {
  workspaces_total: number;
  workspaces_active: number;
  workspaces_suspended: number;
  profiles_total: number;
  memberships_active: number;
  new_workspaces_daily: DailyCount[];
  plan_distribution: { plan_id: string; code: string; name: string; workspace_count: number }[];
  deals_total: number;
  deals_open: number;
}

// ----------------------------------------------------------------------------- sales-agent-engine

export interface UsageDay {
  date: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  sessions: number;
}

export interface ProviderStatus {
  name: string;
  label: string;
  configured: boolean;
}

export interface AgentOverview {
  agent_enabled: boolean;
  maintenance_message: string | null;
  running_sessions: number;
  awaiting_approval: number;
  today: {
    calls: number;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    sessions_started: number;
    active_workspaces: number;
    active_users: number;
  };
  daily: UsageDay[];
  providers: ProviderStatus[];
}

export interface TokenUsage {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface UsageReport {
  from: string;
  to: string;
  totals: TokenUsage & { unpriced_calls: number; sessions: number; workspaces: number; users: number; tool_calls: number };
  daily: UsageDay[];
  by_model: (TokenUsage & { provider: string; model: string; priced: boolean })[];
  by_purpose: (TokenUsage & { purpose: string })[];
  by_workspace: (TokenUsage & { workspace_id: string; sessions: number; users: number })[];
  by_user: (TokenUsage & { user_id: string; sessions: number })[];
  tools: { tool: string; calls: number; executed: number; failed: number; denied: number; rejected: number; other: number }[];
}

export type SessionStatus = 'RUNNING' | 'AWAITING_APPROVAL' | 'DONE' | 'FAILED' | 'HALTED';

export interface AdminSession {
  id: string;
  workspace_id: string;
  user_id: string;
  status: SessionStatus;
  mode: string;
  turns: number;
  started_at: string;
  ended_at: string | null;
  updated_at: string | null;
  tokens: number;
  cost_usd: number;
  tool_calls: number;
  stop_requested: boolean;
}

export const LIMIT_KEYS = [
  'max_steps_per_turn',
  'max_tool_calls_per_turn',
  'max_tokens_per_turn',
  'max_identical_tool_calls',
  'max_concurrent_runs_per_tenant',
  'turns_per_minute_per_user',
  'tokens_per_day_per_tenant',
] as const;
export type LimitKey = (typeof LIMIT_KEYS)[number];

export interface LimitSetting {
  value: number;
  default: number;
  overridden: boolean;
  min: number;
  max: number;
}

export interface AgentControls {
  agent_enabled: boolean;
  maintenance_message: string | null;
  sub_agents_enabled: boolean;
  web_search_enabled: boolean;
  limits: Record<LimitKey, LimitSetting>;
  version: number;
  updated_at: string | null;
  updated_by_email: string | null;
}

export interface AgentControlsInput {
  agent_enabled: boolean;
  maintenance_message: string | null;
  sub_agents_enabled: boolean;
  web_search_enabled: boolean;
  limits: Record<LimitKey, number | null>;
}

export interface AdminTool {
  name: string;
  description: string;
  kind: 'READ' | 'WRITE' | 'MEMORY' | 'DELEGATE';
  scope: string;
  category: string;
  enabled: boolean;
  protected: boolean;
  irreversible: boolean;
  available_to: string[];
  calls_30d: number;
  failures_30d: number;
}

export type RouteName = 'complex' | 'simple' | 'failover' | 'web_grounded';

export interface ModelRoute {
  route: RouteName;
  label: string;
  description: string;
  provider: string;
  models: string[];
  default_provider: string;
  default_models: string[];
  overridden: boolean;
  available: boolean;
}

export interface ModelRate {
  provider: string;
  model: string;
  input_per_million_usd: number;
  output_per_million_usd: number;
  request_fee_usd: number;
  source?: 'default' | 'custom';
}

export interface ModelsConfig {
  routes: ModelRoute[];
  providers: (ProviderStatus & { supports_model_list: boolean })[];
  rates: ModelRate[];
  usage_7d: (TokenUsage & { provider: string; model: string })[];
}

export interface ModelTestResult {
  ok: boolean;
  provider: string;
  model: string;
  latency_ms: number;
  reply: string | null;
  input_tokens: number;
  output_tokens: number;
  error: string | null;
}

export type PromptAgent = 'orchestrator' | 'research' | 'outreach' | 'quote';
export type PromptMode = 'APPEND' | 'REPLACE';

export interface PromptVersion {
  version: number;
  mode: PromptMode;
  instructions: string;
  note: string | null;
  created_at: string;
  created_by_email: string | null;
  active?: boolean;
}

export interface AgentPrompt {
  agent: PromptAgent;
  title: string;
  description: string;
  base_prompt: string;
  active: PromptVersion | null;
  versions: PromptVersion[];
}

// ============================================================================
// Calls
// ============================================================================

const AUTH = '/auth/admin';
const WORKSPACE = '/workspaces/admin';
const AGENT = '/sales-agent/admin';

/** Drops empty filters so the server only sees what was chosen. */
function params(filters: object): Record<string, string | number> {
  return Object.fromEntries(
    Object.entries(filters).filter(([, value]) => value !== undefined && value !== null && value !== '')
  ) as Record<string, string | number>;
}

const get = async <T>(url: string, query?: object): Promise<T> =>
  (await api.get<T>(url, query ? { params: params(query) } : undefined)).data;
const post = async <T>(url: string, body?: unknown, timeout?: number): Promise<T> =>
  (await api.post<T>(url, body ?? {}, timeout ? { timeout } : undefined)).data;
const put = async <T>(url: string, body: unknown): Promise<T> => (await api.put<T>(url, body)).data;
const id = (value: string) => encodeURIComponent(value);

export const adminApi = {
  // auth-service
  users: (filters: UserFilters) => get<Page<AdminUser>>(`${AUTH}/users`, filters),
  user: (userId: string) => get<AdminUserDetail>(`${AUTH}/users/${id(userId)}`),
  suspendUser: (userId: string, reason: string | null) => post<AdminUser>(`${AUTH}/users/${id(userId)}/suspend`, { reason }),
  reactivateUser: (userId: string) => post<AdminUser>(`${AUTH}/users/${id(userId)}/reactivate`),
  signOutUser: (userId: string) =>
    post<{ user: AdminUser; revoked_sessions: number }>(`${AUTH}/users/${id(userId)}/sign-out`),
  unlockUser: (userId: string) => post<AdminUser>(`${AUTH}/users/${id(userId)}/unlock`),
  authStats: (days = 30) => get<AuthStats>(`${AUTH}/stats`, { days }),
  authAudit: (limit = 100) => get<AuditEntry[]>(`${AUTH}/audit`, { limit }),

  // workspace-service
  workspaces: (filters: WorkspaceFilters) => get<Page<AdminWorkspace>>(`${WORKSPACE}/workspaces`, filters),
  workspace: (workspaceId: string) => get<AdminWorkspaceDetail>(`${WORKSPACE}/workspaces/${id(workspaceId)}`),
  setWorkspacePlan: (workspaceId: string, planId: string | null) =>
    put<AdminWorkspace>(`${WORKSPACE}/workspaces/${id(workspaceId)}/plan`, { plan_id: planId }),
  setWorkspaceActive: (workspaceId: string, active: boolean, reason: string | null) =>
    put<AdminWorkspace>(`${WORKSPACE}/workspaces/${id(workspaceId)}/status`, { active, reason }),
  userWorkspaces: (authUserId: string) => get<UserWorkspace[]>(`${WORKSPACE}/users/${id(authUserId)}/workspaces`),
  plans: () => get<AdminPlan[]>(`${WORKSPACE}/plans`),
  createPlan: (input: PlanInput) => post<AdminPlan>(`${WORKSPACE}/plans`, input),
  updatePlan: (planId: string, input: PlanInput) => put<AdminPlan>(`${WORKSPACE}/plans/${id(planId)}`, input),
  makePlanDefault: (planId: string) => post<AdminPlan>(`${WORKSPACE}/plans/${id(planId)}/default`),
  archivePlan: (planId: string) => post<AdminPlan>(`${WORKSPACE}/plans/${id(planId)}/archive`),
  restorePlan: (planId: string) => post<AdminPlan>(`${WORKSPACE}/plans/${id(planId)}/restore`),
  workspaceStats: (days = 30) => get<WorkspaceStats>(`${WORKSPACE}/stats`, { days }),
  workspaceAudit: (limit = 100) => get<AuditEntry[]>(`${WORKSPACE}/audit`, { limit }),

  // sales-agent-engine
  agentOverview: () => get<AgentOverview>(`${AGENT}/overview`),
  usage: (days: number) => get<UsageReport>(`${AGENT}/usage`, { days }),
  sessions: (status: SessionStatus | '', limit = 100) => get<AdminSession[]>(`${AGENT}/sessions`, { status, limit }),
  stopSession: (sessionId: string) =>
    post<{ id: string; status: SessionStatus; stop_requested: boolean }>(`${AGENT}/sessions/${id(sessionId)}/stop`),
  controls: () => get<AgentControls>(`${AGENT}/controls`),
  saveControls: (input: AgentControlsInput) => put<AgentControls>(`${AGENT}/controls`, input),
  tools: () => get<AdminTool[]>(`${AGENT}/tools`),
  setToolEnabled: (name: string, enabled: boolean) => put<AdminTool>(`${AGENT}/tools/${id(name)}`, { enabled }),
  models: () => get<ModelsConfig>(`${AGENT}/models`),
  setRoute: (route: RouteName, provider: string, models: string[]) =>
    put<ModelsConfig>(`${AGENT}/models/routes/${route}`, { provider, models }),
  resetRoute: (route: RouteName) => put<ModelsConfig>(`${AGENT}/models/routes/${route}`, { reset: true }),
  saveRates: (rates: ModelRate[]) =>
    put<ModelsConfig>(`${AGENT}/models/rates`, {
      rates: rates.map(({ provider, model, input_per_million_usd, output_per_million_usd, request_fee_usd }) => ({
        provider,
        model,
        input_per_million_usd,
        output_per_million_usd,
        request_fee_usd,
      })),
    }),
  testModel: (provider: string, model: string) =>
    post<ModelTestResult>(`${AGENT}/models/test`, { provider, model }, 90000),
  prompts: () => get<AgentPrompt[]>(`${AGENT}/prompts`),
  publishPrompt: (agent: PromptAgent, mode: PromptMode, instructions: string, note: string | null) =>
    post<AgentPrompt>(`${AGENT}/prompts/${agent}`, { mode, instructions, note }),
  restorePrompt: (agent: PromptAgent, version: number) =>
    post<AgentPrompt>(`${AGENT}/prompts/${agent}/versions/${version}/restore`),
  previewPrompt: (agent: PromptAgent, mode: PromptMode, instructions: string) =>
    post<{ system_prompt: string }>(`${AGENT}/prompts/preview`, { agent, mode, instructions }),
  agentAudit: (limit = 100) => get<AuditEntry[]>(`${AGENT}/audit`, { limit }),
};

// ============================================================================
// Errors
// ============================================================================

export function adminErrorStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } })?.response?.status;
}

/** A message for the admin, whichever service answered (Spring `message`, engine `message`, FastAPI `detail`). */
export function describeAdminError(error: unknown): string {
  const response = (
    error as { response?: { status?: number; data?: { message?: unknown; detail?: unknown } } }
  )?.response;
  if (!response) {
    if ((error as { code?: string })?.code === 'ECONNABORTED') {
      return 'The server took too long to answer. Try again.';
    }
    return 'The server could not be reached. Check that the platform services are running.';
  }
  const data = response.data ?? {};
  if (typeof data.message === 'string' && data.message.trim()) {
    return data.message;
  }
  if (Array.isArray(data.detail)) {
    const first = data.detail[0] as { msg?: string; loc?: unknown[] } | undefined;
    if (first?.msg) {
      const field = Array.isArray(first.loc) ? first.loc.filter((part) => part !== 'body').join('.') : '';
      return field ? `${field}: ${first.msg}` : first.msg;
    }
  }
  if (typeof data.detail === 'string' && data.detail.trim()) {
    return data.detail;
  }
  switch (response.status) {
    case 401:
      return 'Your session has expired. Sign in again.';
    case 403:
      return 'Only platform super admins can do this.';
    case 404:
      return 'That no longer exists. Refresh the page.';
    case 429:
      return 'Too many requests. Wait a moment and try again.';
    case 502:
    case 503:
    case 504:
      return 'A platform service is unavailable right now. Try again shortly.';
    default:
      return 'Something went wrong. Try again.';
  }
}
