import type { LimitKey, SessionStatus } from '../../../api/adminApi';
import type { Tone } from '../components/AdminUi';

export const LIMIT_META: Record<LimitKey, { label: string; help: string; unit: string }> = {
  max_steps_per_turn: {
    label: 'Model steps per request',
    help: 'How many times the agent may think and act while answering one message. Sub-agent steps count too.',
    unit: 'steps',
  },
  max_tool_calls_per_turn: {
    label: 'Tool calls per request',
    help: 'Searches, reads and actions the agent may run for one message.',
    unit: 'calls',
  },
  max_tokens_per_turn: {
    label: 'Tokens per request',
    help: 'The cost cap of a single message: the request stops when it has used this many model tokens.',
    unit: 'tokens',
  },
  max_identical_tool_calls: {
    label: 'Repeats of the same call',
    help: 'Loop protection: the same tool with the same details more often than this stops the request.',
    unit: 'repeats',
  },
  max_concurrent_runs_per_tenant: {
    label: 'Runs at once per workspace',
    help: 'Requests one workspace may have running at the same time. A workspace’s plan can set its own number.',
    unit: 'runs',
  },
  turns_per_minute_per_user: {
    label: 'Messages per minute per rep',
    help: 'Rate limit for each person sending messages to the agent.',
    unit: 'messages',
  },
  tokens_per_day_per_tenant: {
    label: 'Tokens per day per workspace',
    help: 'Daily model budget of a workspace (resets at midnight UTC). 0 means no limit. A plan can set its own number.',
    unit: 'tokens',
  },
};

export const SESSION_STATUS_META: Record<SessionStatus, { label: string; tone: Tone }> = {
  RUNNING: { label: 'Running', tone: 'info' },
  AWAITING_APPROVAL: { label: 'Waiting for approval', tone: 'warning' },
  DONE: { label: 'Done', tone: 'success' },
  FAILED: { label: 'Failed', tone: 'danger' },
  HALTED: { label: 'Stopped', tone: 'neutral' },
};

/** Tools a feature switch turns off regardless of their own toggle. */
export const SWITCHED_TOOLS: Record<string, 'sub_agents_enabled' | 'web_search_enabled'> = {
  delegate: 'sub_agents_enabled',
  web_search: 'web_search_enabled',
  research_prospect: 'web_search_enabled',
};

export const TOOL_KIND_META: Record<string, { label: string; tone: Tone; description: string }> = {
  READ: { label: 'Read', tone: 'info', description: 'Looks things up. Never needs approval.' },
  WRITE: { label: 'Action', tone: 'warning', description: 'Changes something outside the chat. Always pauses for the rep’s approval.' },
  MEMORY: { label: 'Memory', tone: 'violet', description: 'Saves or removes what the agent remembers.' },
  DELEGATE: { label: 'Sub-agents', tone: 'primary', description: 'Hands work to the research, outreach or quote agent.' },
};
