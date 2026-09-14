import React from 'react';
import { Ban, CircleCheck, History, ReceiptText, Users } from 'lucide-react';
import { adminApi } from '../../api/adminApi';
import type { AdminPlan, UsageReport } from '../../api/adminApi';
import { Button } from '../../components/common/Button';
import { Avatar, Badge, Drawer, ErrorBlock, KeyValue, LoadingBlock, Notice, labelClass, selectClass } from './components/AdminUi';
import { Meter } from './components/Charts';
import { formatCompact, formatDateTime, formatNumber, formatUsd, humanize, initials, timeAgo } from './adminFormat';
import { useAdminQuery } from './useAdminQuery';
import { useWorkspaceActions } from './useWorkspaceActions';

const ROLE_TONE: Record<string, 'primary' | 'info' | 'success' | 'neutral'> = {
  OWNER: 'primary',
  ADMIN: 'info',
  MEMBER: 'success',
  VIEWER: 'neutral',
};

const EVENT_LABEL: Record<string, string> = {
  MEMBER_ADDED: 'added',
  ROLE_CHANGED: 'changed the role of',
  MEMBER_DEACTIVATED: 'deactivated',
  MEMBER_REACTIVATED: 'reactivated',
  MEMBER_REMOVED: 'removed',
  INVITE_RESENT: 'resent the invite to',
};

function limitText(value: number | null, unit: string): string {
  return value === null ? 'No limit' : `${formatCompact(value)} ${unit}`;
}

export const WorkspaceDetailDrawer: React.FC<{
  workspaceId: string;
  plans: AdminPlan[];
  usage: UsageReport['by_workspace'][number] | undefined;
  usageLoaded: boolean;
  onClose: () => void;
  onChanged: () => void;
}> = ({ workspaceId, plans, usage, usageLoaded, onClose, onChanged }) => {
  const detail = useAdminQuery(() => adminApi.workspace(workspaceId), `workspace:${workspaceId}`);
  const actions = useWorkspaceActions(() => {
    detail.reload();
    onChanged();
  });

  const workspace = detail.data?.workspace;
  const effectivePlan = workspace ? plans.find((plan) => plan.plan_id === workspace.plan.plan_id) : undefined;
  const defaultPlan = plans.find((plan) => plan.is_default);
  const activeMembers = detail.data?.members.filter((member) => member.active).length ?? 0;

  return (
    <Drawer
      title={workspace?.name ?? 'Workspace'}
      subtitle={workspace ? `Created ${formatDateTime(workspace.created_at)}` : undefined}
      onClose={onClose}
      width="max-w-2xl"
      footer={
        workspace && (
          <div className="flex items-center justify-end gap-2">
            {workspace.is_active ? (
              <Button variant="destructive" className="px-3 py-2 w-auto text-xs" icon={<Ban className="w-3.5 h-3.5" />} iconPosition="left" disabled={actions.busy} onClick={() => actions.suspend(workspace)}>
                Suspend workspace
              </Button>
            ) : (
              <Button className="px-3 py-2 w-auto text-xs" icon={<CircleCheck className="w-3.5 h-3.5" />} iconPosition="left" disabled={actions.busy} onClick={() => actions.reactivate(workspace)}>
                Reactivate workspace
              </Button>
            )}
          </div>
        )
      }
    >
      {detail.error && !detail.data ? (
        <ErrorBlock message={detail.error} onRetry={detail.reload} />
      ) : !workspace || !detail.data ? (
        <LoadingBlock />
      ) : (
        <>
          <div className="flex items-center gap-4">
            <Avatar text={initials(workspace.name)} tone={workspace.is_active ? 'info' : 'danger'} size="lg" />
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-1.5">
                {workspace.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="danger">Suspended</Badge>}
                <Badge tone="primary">{workspace.plan.name} plan</Badge>
              </div>
              <p className="text-xs text-muted-foreground">{workspace.description || 'No description'}</p>
            </div>
          </div>

          {!workspace.is_active && (
            <Notice tone="danger" icon={Ban}>
              Suspended: members can’t open this workspace, its data or the sales agent until you reactivate it.
            </Notice>
          )}

          <dl className="grid grid-cols-2 gap-x-6 gap-y-4">
            <KeyValue label="Owner">
              {workspace.owner ? (
                <>
                  {workspace.owner.name}
                  <span className="block text-xs text-muted-foreground">{workspace.owner.email ?? 'Email unavailable'}</span>
                </>
              ) : (
                '—'
              )}
            </KeyValue>
            <KeyValue label="Workspace id">
              <span className="font-mono text-xs break-all">{workspace.workspace_id}</span>
            </KeyValue>
            <KeyValue label="Deals">
              {formatNumber(detail.data.counts.deals)} <span className="text-xs text-muted-foreground">({formatNumber(detail.data.counts.open_deals)} open)</span>
            </KeyValue>
            <KeyValue label="Agent work records">
              {formatNumber(detail.data.counts.contexts)} <span className="text-xs text-muted-foreground">· {formatNumber(detail.data.counts.notes)} notes</span>
            </KeyValue>
          </dl>

          <section className="rounded-2xl border border-border/70 p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h4 className="text-xs font-bold text-foreground flex items-center gap-2">
                <ReceiptText className="w-4 h-4 text-muted-foreground" /> Plan
              </h4>
              {!workspace.plan_assigned && <Badge>Default plan</Badge>}
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1 flex-1 min-w-[12rem]">
                <label htmlFor="workspace-plan" className={labelClass}>
                  Change plan
                </label>
                <select
                  id="workspace-plan"
                  className={`${selectClass} w-full`}
                  value={workspace.plan_assigned ? workspace.plan.plan_id : ''}
                  disabled={actions.busy || plans.length === 0}
                  onChange={(event) => {
                    const chosen = plans.find((plan) => plan.plan_id === event.target.value) ?? null;
                    actions.changePlan(workspace, chosen, defaultPlan);
                  }}
                >
                  <option value="">Default plan{defaultPlan ? ` (${defaultPlan.name})` : ''}</option>
                  {plans
                    .filter((plan) => !plan.is_archived || plan.plan_id === workspace.plan.plan_id)
                    .map((plan) => (
                      <option key={plan.plan_id} value={plan.plan_id}>
                        {plan.name}
                        {plan.is_archived ? ' (archived)' : ''}
                      </option>
                    ))}
                </select>
              </div>
            </div>
            {effectivePlan && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <div className="rounded-xl bg-muted/40 px-3 py-2">
                  <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Members</p>
                  <p className="text-sm font-semibold text-foreground tabular-nums">
                    {activeMembers}
                    {effectivePlan.max_members !== null ? ` / ${effectivePlan.max_members}` : ''}
                  </p>
                  {effectivePlan.max_members !== null && (
                    <Meter
                      value={activeMembers}
                      max={effectivePlan.max_members}
                      className="mt-1.5"
                      tone={activeMembers >= effectivePlan.max_members ? 'danger' : 'primary'}
                    />
                  )}
                </div>
                <div className="rounded-xl bg-muted/40 px-3 py-2">
                  <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Agent tokens / day</p>
                  <p className="text-sm font-semibold text-foreground">{limitText(effectivePlan.agent_tokens_per_day, 'tokens')}</p>
                </div>
                <div className="rounded-xl bg-muted/40 px-3 py-2">
                  <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Agent runs at once</p>
                  <p className="text-sm font-semibold text-foreground">{limitText(effectivePlan.max_concurrent_agent_runs, 'runs')}</p>
                </div>
              </div>
            )}
          </section>

          <section className="space-y-2">
            <h4 className="text-xs font-bold text-foreground">Sales agent, last 30 days</h4>
            {!usageLoaded ? (
              <LoadingBlock className="py-6" />
            ) : usage ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {[
                  { label: 'Conversations', value: formatNumber(usage.sessions) },
                  { label: 'Reps using it', value: formatNumber(usage.users) },
                  { label: 'Tokens', value: formatCompact(usage.input_tokens + usage.output_tokens) },
                  { label: 'Model cost', value: formatUsd(usage.cost_usd) },
                ].map((item) => (
                  <div key={item.label} className="rounded-xl border border-border/70 px-3 py-2">
                    <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">{item.label}</p>
                    <p className="text-sm font-bold text-foreground tabular-nums">{item.value}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">No sales agent use in the last 30 days (or not among the 50 heaviest workspaces).</p>
            )}
          </section>

          <section className="space-y-2">
            <h4 className="text-xs font-bold text-foreground flex items-center gap-2">
              <Users className="w-4 h-4 text-muted-foreground" /> Members ({detail.data.members.length})
            </h4>
            <ul className="rounded-xl border border-border/70 divide-y divide-border/60 overflow-hidden">
              {detail.data.members.map((member) => (
                <li key={member.membership_id} className={`px-3 py-2.5 flex items-center justify-between gap-3 text-xs ${member.active ? '' : 'opacity-60'}`}>
                  <span className="flex items-center gap-2.5 min-w-0">
                    <Avatar text={initials(member.name)} size="sm" />
                    <span className="min-w-0">
                      <span className="block font-semibold text-foreground truncate">{member.name}</span>
                      <span className="block text-[11px] text-muted-foreground truncate">{member.email ?? 'Email unavailable'}</span>
                    </span>
                  </span>
                  <span className="flex items-center gap-1 shrink-0">
                    {!member.active && <Badge>Deactivated</Badge>}
                    <Badge tone={ROLE_TONE[member.role] ?? 'neutral'}>{humanize(member.role)}</Badge>
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <section className="space-y-2">
            <h4 className="text-xs font-bold text-foreground flex items-center gap-2">
              <History className="w-4 h-4 text-muted-foreground" /> Member changes
            </h4>
            {detail.data.recent_member_events.length === 0 ? (
              <p className="text-xs text-muted-foreground">No member changes recorded.</p>
            ) : (
              <ul className="space-y-2">
                {detail.data.recent_member_events.map((event) => (
                  <li key={event.event_id} className="text-xs flex items-start justify-between gap-3">
                    <span className="text-foreground">
                      <span className="font-semibold">{event.actor_name ?? 'Someone'}</span> {EVENT_LABEL[event.action] ?? humanize(event.action)}{' '}
                      <span className="font-semibold">{event.target_name ?? event.target_email ?? 'a member'}</span>
                      {event.to_role && event.action !== 'MEMBER_REMOVED' ? ` (${humanize(event.to_role)})` : ''}
                    </span>
                    <span className="text-[11px] text-muted-foreground whitespace-nowrap" title={formatDateTime(event.created_at)}>
                      {timeAgo(event.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
      {actions.dialog}
    </Drawer>
  );
};
