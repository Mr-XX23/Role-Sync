import React, { useState } from 'react';
import { Globe, Network, PauseCircle, PlayCircle, RotateCcw, Save, SlidersHorizontal } from 'lucide-react';
import { adminApi, describeAdminError, LIMIT_KEYS } from '../../../api/adminApi';
import type { AgentControls, AgentControlsInput, LimitKey } from '../../../api/adminApi';
import { Button } from '../../../components/common/Button';
import { useToast } from '../../../context/ToastContext';
import { Badge, Card, ConfirmAction, Notice, Switch, inputClass, labelClass } from '../components/AdminUi';
import { formatDateTime, formatNumber, timeAgo } from '../adminFormat';
import { LIMIT_META } from './agentMeta';

interface Draft {
  version: number; // the saved controls this draft was started from
  sub_agents_enabled: boolean;
  web_search_enabled: boolean;
  maintenance_message: string;
  limits: Record<LimitKey, string>; // '' = use the default
}

function draftFrom(controls: AgentControls): Draft {
  return {
    version: controls.version,
    sub_agents_enabled: controls.sub_agents_enabled,
    web_search_enabled: controls.web_search_enabled,
    maintenance_message: controls.maintenance_message ?? '',
    limits: Object.fromEntries(
      LIMIT_KEYS.map((key) => [key, controls.limits[key].overridden ? String(controls.limits[key].value) : ''])
    ) as Record<LimitKey, string>,
  };
}

function limitProblem(controls: AgentControls, key: LimitKey, raw: string): string | null {
  if (raw.trim() === '') return null;
  if (!/^\d+$/.test(raw.trim())) return 'Enter a whole number, or leave it empty for the default.';
  const value = Number(raw);
  const { min, max } = controls.limits[key];
  if (value < min || value > max) return `Between ${formatNumber(min)} and ${formatNumber(max)}.`;
  return null;
}

function inputFrom(draft: Draft, agentEnabled: boolean): AgentControlsInput {
  return {
    agent_enabled: agentEnabled,
    maintenance_message: draft.maintenance_message.trim() || null,
    sub_agents_enabled: draft.sub_agents_enabled,
    web_search_enabled: draft.web_search_enabled,
    limits: Object.fromEntries(
      LIMIT_KEYS.map((key) => [key, draft.limits[key].trim() === '' ? null : Number(draft.limits[key])])
    ) as Record<LimitKey, number | null>,
  };
}

export const AgentControlsPanel: React.FC<{ controls: AgentControls; onSaved: (controls: AgentControls) => void }> = ({
  controls,
  onSaved,
}) => {
  const toast = useToast();
  const [edited, setEdited] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmPause, setConfirmPause] = useState(false);
  // A draft started from an older version of the controls is dropped once the new ones load.
  const draft = edited && edited.version === controls.version ? edited : draftFrom(controls);
  const saved = draftFrom(controls);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  const problems = Object.fromEntries(LIMIT_KEYS.map((key) => [key, limitProblem(controls, key, draft.limits[key])])) as Record<
    LimitKey,
    string | null
  >;
  const invalid = Object.values(problems).some(Boolean);

  const change = (update: Partial<Draft>) => setEdited({ ...draft, ...update });
  const setLimit = (key: LimitKey, value: string) => change({ limits: { ...draft.limits, [key]: value } });

  const save = async (agentEnabled: boolean, source: Draft, success: string) => {
    setSaving(true);
    try {
      const result = await adminApi.saveControls(inputFrom(source, agentEnabled));
      setEdited(null);
      onSaved(result);
      toast.success(success, 'Agent controls saved');
      return true;
    } catch (error) {
      toast.error(describeAdminError(error), 'Couldn’t save agent controls');
      return false;
    } finally {
      setSaving(false);
    }
  };

  // The kill switch saves on its own, with the saved (not the edited) settings.
  const setAgentEnabled = async (enabled: boolean) => {
    const source = { ...saved, maintenance_message: draft.maintenance_message };
    const ok = await save(
      enabled,
      source,
      enabled ? 'The sales agent is live again for every workspace.' : 'The sales agent is paused for every workspace.'
    );
    if (ok) setConfirmPause(false);
  };

  return (
    <div className="space-y-4">
      <section
        className={`rounded-2xl border p-5 flex flex-col lg:flex-row lg:items-center gap-4 justify-between shadow-2xs ${
          controls.agent_enabled ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-amber-500/40 bg-amber-500/10'
        }`}
      >
        <div className="flex items-start gap-4 min-w-0">
          <div
            className={`w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 ${
              controls.agent_enabled ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400' : 'bg-amber-500/20 text-amber-600 dark:text-amber-400'
            }`}
          >
            {controls.agent_enabled ? <PlayCircle className="w-6 h-6" /> : <PauseCircle className="w-6 h-6" />}
          </div>
          <div className="min-w-0 space-y-1">
            <p className="font-serif text-xl font-bold text-foreground">
              {controls.agent_enabled ? 'The sales agent is live' : 'The sales agent is paused'}
            </p>
            <p className="text-xs text-muted-foreground max-w-2xl">
              {controls.agent_enabled
                ? 'Pausing stops new messages in every workspace and halts running requests at their next step. Approvals already given are kept.'
                : 'Reps see the message below when they try to use the agent. Turn it back on to let requests run again.'}
            </p>
            <div className="pt-2 max-w-xl space-y-1">
              <label htmlFor="maintenance-message" className={labelClass}>
                Message shown to reps while paused
              </label>
              <input
                id="maintenance-message"
                className={inputClass}
                maxLength={500}
                placeholder="The sales agent is paused by the RoleSync team. Try again later."
                value={draft.maintenance_message}
                disabled={saving}
                onChange={(event) => change({ maintenance_message: event.target.value })}
              />
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {controls.agent_enabled ? (
            <Button variant="destructive" className="px-4 py-2.5 w-auto text-xs" icon={<PauseCircle className="w-4 h-4" />} iconPosition="left" disabled={saving} onClick={() => setConfirmPause(true)}>
              Pause for everyone
            </Button>
          ) : (
            <Button className="px-4 py-2.5 w-auto text-xs" icon={<PlayCircle className="w-4 h-4" />} iconPosition="left" isLoading={saving} loadingText="Resuming…" onClick={() => void setAgentEnabled(true)}>
              Resume the agent
            </Button>
          )}
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Sub-agents" subtitle="Research, outreach and quote agents the assistant hands work to" icon={Network}>
          <div className="flex items-start justify-between gap-4">
            <p className="text-xs text-muted-foreground">
              When off, the assistant does every step itself. Useful to cut cost or while debugging a sub-agent.
            </p>
            <Switch
              label="Sub-agents"
              checked={draft.sub_agents_enabled}
              disabled={saving}
              onChange={(checked) => change({ sub_agents_enabled: checked })}
            />
          </div>
        </Card>
        <Card title="Web search" subtitle="Google Search grounding and Tavily" icon={Globe}>
          <div className="flex items-start justify-between gap-4">
            <p className="text-xs text-muted-foreground">
              When off, the agent can’t search the web or research prospects online. The knowledge base, catalog and connected
              apps still work.
            </p>
            <Switch
              label="Web search"
              checked={draft.web_search_enabled}
              disabled={saving}
              onChange={(checked) => change({ web_search_enabled: checked })}
            />
          </div>
        </Card>
      </div>

      <Card
        title="Guardrails and budgets"
        subtitle="Leave a field empty to use the server default. Changes apply to new steps within a few seconds."
        icon={SlidersHorizontal}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {LIMIT_KEYS.map((key) => {
            const setting = controls.limits[key];
            const meta = LIMIT_META[key];
            const problem = problems[key];
            const custom = draft.limits[key].trim() !== '';
            return (
              <div key={key} className="rounded-xl border border-border/70 p-3.5 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <label htmlFor={`limit-${key}`} className="text-xs font-semibold text-foreground">
                    {meta.label}
                  </label>
                  {custom ? <Badge tone="primary">Custom</Badge> : <Badge>Default</Badge>}
                </div>
                <div className="flex items-center gap-2">
                  <input
                    id={`limit-${key}`}
                    inputMode="numeric"
                    className={`${inputClass} tabular-nums ${problem ? 'border-destructive focus:border-destructive focus:ring-destructive/10' : ''}`}
                    placeholder={formatNumber(setting.default)}
                    value={draft.limits[key]}
                    disabled={saving}
                    aria-invalid={Boolean(problem)}
                    onChange={(event) => setLimit(key, event.target.value.replace(/[,\s]/g, ''))}
                  />
                  {custom && (
                    <button
                      type="button"
                      onClick={() => setLimit(key, '')}
                      title="Use the default"
                      aria-label={`Reset ${meta.label} to the default`}
                      className="p-2 rounded-lg border border-border/70 text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
                <p className={`text-[11px] leading-snug ${problem ? 'text-destructive' : 'text-muted-foreground'}`}>
                  {problem ?? `${meta.help} Default ${formatNumber(setting.default)} ${meta.unit}.`}
                </p>
              </div>
            );
          })}
        </div>
      </Card>

      <div
        className={`sticky bottom-0 z-10 rounded-2xl border px-4 py-3 flex flex-wrap items-center justify-between gap-3 shadow-md transition-colors ${
          dirty ? 'bg-card border-primary/40' : 'bg-card/80 border-border/70 backdrop-blur-sm'
        }`}
      >
        <p className="text-xs text-muted-foreground">
          {dirty ? (
            <span className="text-foreground font-semibold">You have unsaved changes.</span>
          ) : controls.updated_at ? (
            <span title={formatDateTime(controls.updated_at)}>
              Last changed {timeAgo(controls.updated_at)}
              {controls.updated_by_email ? ` by ${controls.updated_by_email}` : ''} · version {controls.version}
            </span>
          ) : (
            'Using the server defaults. Nothing has been changed here yet.'
          )}
        </p>
        <div className="flex items-center gap-2">
          {dirty && (
            <button
              type="button"
              onClick={() => setEdited(null)}
              disabled={saving}
              className="px-4 py-2 text-xs font-medium rounded-xl border border-border/70 hover:bg-muted/60 text-muted-foreground hover:text-foreground transition-colors cursor-pointer disabled:opacity-50"
            >
              Discard
            </button>
          )}
          <Button
            className="px-4 py-2 w-auto text-xs"
            icon={<Save className="w-3.5 h-3.5" />}
            iconPosition="left"
            disabled={!dirty || invalid}
            isLoading={saving}
            loadingText="Saving…"
            onClick={() => void save(controls.agent_enabled, draft, 'New settings apply to the agent within a few seconds.')}
          >
            Save changes
          </Button>
        </div>
      </div>

      {invalid && dirty && <Notice tone="warning">Fix the highlighted limits before saving.</Notice>}

      {confirmPause && (
        <ConfirmAction
          destructive
          title="Pause the sales agent for everyone?"
          message={
            <>
              New messages are refused in every workspace, and requests already running stop at their next step. Reps see
              {draft.maintenance_message.trim() ? ` “${draft.maintenance_message.trim()}”` : ' a “paused by the RoleSync team” message'}.
            </>
          }
          confirmLabel="Pause the agent"
          busyLabel="Pausing…"
          busy={saving}
          onConfirm={() => void setAgentEnabled(false)}
          onCancel={() => setConfirmPause(false)}
        />
      )}
    </div>
  );
};
