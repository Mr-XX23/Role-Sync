import api from './axiosInstance';
import { getActiveTenantId } from './catalogApi';

// ============================================================================
// Types (mirror backend/sales-agent-engine app/api/skills.py)
// ============================================================================

export type SkillCategory = 'PROSPECT' | 'QUALIFY' | 'ENGAGE' | 'CLOSE' | 'PIPELINE' | 'OTHER';
export type SkillSource = 'BUILTIN' | 'WORKSPACE' | 'PRIVATE';
export type SkillVisibility = 'WORKSPACE' | 'PRIVATE';

export interface SkillUsage {
  total: number;
  mine: number;
  auto: number; // the agent chose it
  picked: number; // a rep picked it in the chat
  delegated: number; // handed to a sub-agent
  last_used_at: string | null;
}

export interface Skill {
  ref: string; // a built-in's key or the skill id: what every call takes
  slug: string; // what the agent calls it
  name: string;
  description: string;
  category: SkillCategory;
  tools: string[];
  apps: string[]; // apps its tools need connected
  source: SkillSource;
  customized: boolean;
  version: number;
  enabled: boolean; // on for my agent
  my_switch: boolean | null; // my own switch; null = never changed
  workspace_enabled: boolean; // false when an admin switched it off for everyone
  editable: boolean;
  updated_at: string | null;
  updated_by_me: boolean;
  usage: SkillUsage;
}

export interface SkillDetail extends Skill {
  instructions: string;
}

export interface SkillList {
  skills: Skill[];
  role: string | null;
  can_create_private: boolean;
  can_manage_workspace: boolean;
  limits: { enabled: number; max_enabled: number; workspace: number; max_workspace: number; private: number; max_private: number };
}

export interface SkillFields {
  name: string;
  description: string;
  instructions: string;
  category: SkillCategory;
  tools: string[];
}

/** A skill read from a SKILL.md file or drafted with AI: not saved yet. */
export interface SkillDraft extends SkillFields {
  warnings: string[];
}

export interface SkillVersion extends SkillFields {
  version: number;
  note: string | null;
  edited_by_me: boolean;
  edited_at: string | null;
}

export interface ArchivedSkill {
  id: string;
  name: string;
  description: string;
  source: SkillSource;
  version: number;
  archived_at: string | null;
}

export interface SkillTool {
  name: string;
  description: string;
  app: string | null;
}

// ============================================================================
// API
// ============================================================================

const BASE = '/sales-agent/skills';

const tenantHeaders = () => ({ 'X-Tenant-Id': getActiveTenantId() });
const path = (ref: string) => `${BASE}/${encodeURIComponent(ref)}`;

export const skillsApi = {
  list: async (): Promise<SkillList> => (await api.get<SkillList>(BASE, { headers: tenantHeaders() })).data,

  get: async (ref: string): Promise<SkillDetail> => (await api.get<SkillDetail>(path(ref), { headers: tenantHeaders() })).data,

  tools: async (): Promise<SkillTool[]> => (await api.get<SkillTool[]>(`${BASE}/tools`, { headers: tenantHeaders() })).data,

  archived: async (): Promise<ArchivedSkill[]> =>
    (await api.get<ArchivedSkill[]>(`${BASE}/archived`, { headers: tenantHeaders() })).data,

  create: async (fields: SkillFields & { visibility: SkillVisibility; note?: string }): Promise<SkillDetail> =>
    (await api.post<SkillDetail>(BASE, fields, { headers: tenantHeaders() })).data,

  /** Saves a new version; ``expectedVersion`` is the version the edit started from. */
  update: async (ref: string, fields: SkillFields, expectedVersion: number): Promise<SkillDetail> =>
    (await api.put<SkillDetail>(path(ref), { ...fields, expected_version: expectedVersion }, { headers: tenantHeaders() })).data,

  /** Archives a skill, or resets a customized built-in to the shipped version. */
  archive: async (ref: string): Promise<ArchivedSkill> =>
    (await api.delete<ArchivedSkill>(path(ref), { headers: tenantHeaders() })).data,

  restoreArchived: async (skillId: string): Promise<SkillDetail> =>
    (await api.post<SkillDetail>(`${BASE}/archived/${encodeURIComponent(skillId)}/restore`, undefined, { headers: tenantHeaders() })).data,

  setEnabled: async (ref: string, enabled: boolean): Promise<Skill> =>
    (await api.put<Skill>(`${path(ref)}/enabled`, { enabled }, { headers: tenantHeaders() })).data,

  setWorkspaceEnabled: async (ref: string, enabled: boolean): Promise<Skill> =>
    (await api.put<Skill>(`${path(ref)}/workspace-enabled`, { enabled }, { headers: tenantHeaders() })).data,

  versions: async (ref: string): Promise<SkillVersion[]> =>
    (await api.get<SkillVersion[]>(`${path(ref)}/versions`, { headers: tenantHeaders() })).data,

  restoreVersion: async (ref: string, version: number, expectedVersion: number): Promise<SkillDetail> =>
    (
      await api.post<SkillDetail>(`${path(ref)}/versions/${version}/restore`, { expected_version: expectedVersion }, { headers: tenantHeaders() })
    ).data,

  previewImport: async (content: string): Promise<SkillDraft> =>
    (await api.post<SkillDraft>(`${BASE}/import/preview`, { content }, { headers: tenantHeaders() })).data,

  draft: async (idea: string): Promise<SkillDraft> =>
    (await api.post<SkillDraft>(`${BASE}/draft`, { idea }, { headers: tenantHeaders() })).data,

  /** The skill as a SKILL.md file, saved through the browser. */
  download: async (skill: Pick<Skill, 'ref' | 'slug'>): Promise<void> => {
    const response = await api.get<Blob>(`${path(skill.ref)}/export`, { headers: tenantHeaders(), responseType: 'blob' });
    const url = URL.createObjectURL(response.data);
    try {
      const link = document.createElement('a');
      link.href = url;
      link.download = `${skill.slug}-SKILL.md`;
      document.body.appendChild(link);
      link.click();
      link.remove();
    } finally {
      setTimeout(() => URL.revokeObjectURL(url), 1_000);
    }
  },
};

/** A readable message for a failed skills request (engine errors, or FastAPI's own validation errors). */
export function describeSkillError(error: unknown, fallback = 'Skills could not be reached.'): string {
  const response = (error as { response?: { status?: number; data?: { message?: string; detail?: unknown } } })?.response;
  if (!response) {
    return error instanceof Error && error.message !== 'Network Error' ? error.message : fallback;
  }
  if (response.data?.message) {
    return response.data.message.charAt(0).toUpperCase() + response.data.message.slice(1);
  }
  const detail = response.data?.detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { loc?: unknown[]; msg?: string };
    const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1]) : 'input';
    return `${field.replace(/_/g, ' ')}: ${first.msg ?? 'is not valid'}`;
  }
  if (response.status === 403) {
    return 'You can’t change skills in this workspace.';
  }
  return fallback;
}
