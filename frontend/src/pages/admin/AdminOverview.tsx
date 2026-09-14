import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Bot,
  Building2,
  CheckCircle2,
  CircleDollarSign,
  Coins,
  Cpu,
  Gauge,
  MessageSquareCode,
  PauseCircle,
  ReceiptText,
  ScrollText,
  ServerCog,
  Users,
  XCircle,
} from 'lucide-react';
import { adminApi } from '../../api/adminApi';
import type { AuditEntry } from '../../api/adminApi';
import { AdminPage, Badge, Card, ErrorBlock, LoadingBlock, Notice, RefreshButton, StatCard } from './components/AdminUi';
import { AreaChart, DonutChart, StackedBarChart } from './components/Charts';
import { formatCompact, formatDateTime, formatDay, formatNumber, formatUsd, timeAgo } from './adminFormat';
import { useAdminQuery } from './useAdminQuery';
import { AUDIT_SERVICE_META } from './auditMeta';

const PLAN_COLORS = [
  { colorClass: 'text-primary', dotClass: 'bg-primary' },
  { colorClass: 'text-sky-500', dotClass: 'bg-sky-500' },
  { colorClass: 'text-emerald-500', dotClass: 'bg-emerald-500' },
  { colorClass: 'text-amber-500', dotClass: 'bg-amber-500' },
  { colorClass: 'text-violet-500', dotClass: 'bg-violet-500' },
  { colorClass: 'text-rose-500', dotClass: 'bg-rose-500' },
];

const QUICK_LINKS = [
  { to: '/admin/users', label: 'Manage users', description: 'Suspend, sign out or unlock accounts', icon: Users },
  { to: '/admin/workspaces', label: 'Workspaces', description: 'Plans, members and suspensions', icon: Building2 },
  { to: '/admin/agents', label: 'Agent controls', description: 'Pause the agent, tools and limits', icon: Bot },
  { to: '/admin/models', label: 'Models & pricing', description: 'Which model does what, and its cost', icon: Cpu },
  { to: '/admin/prompts', label: 'Prompts', description: 'Instructions every agent follows', icon: MessageSquareCode },
  { to: '/admin/plans', label: 'Plans', description: 'Limits each workspace gets', icon: ReceiptText },
];

export const AdminOverview: React.FC = () => {
  const auth = useAdminQuery(() => adminApi.authStats(30), 'auth-stats');
  const workspace = useAdminQuery(() => adminApi.workspaceStats(30), 'workspace-stats');
  const agent = useAdminQuery(() => adminApi.agentOverview(), 'agent-overview');
  const audit = useAdminQuery(async () => {
    const results = await Promise.allSettled([adminApi.authAudit(10), adminApi.workspaceAudit(10), adminApi.agentAudit(10)]);
    return results
      .flatMap((result) => (result.status === 'fulfilled' ? result.value : []))
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .slice(0, 8);
  }, 'audit-recent');

  const refreshing = auth.loading || workspace.loading || agent.loading || audit.loading;
  const refreshAll = () => {
    auth.reload();
    workspace.reload();
    agent.reload();
    audit.reload();
  };

  const services = [
    { name: 'Accounts (auth-service)', ok: !auth.error, loading: auth.loading && !auth.data && !auth.error, error: auth.error },
    { name: 'Workspaces (workspace-service)', ok: !workspace.error, loading: workspace.loading && !workspace.data && !workspace.error, error: workspace.error },
    { name: 'Sales agent engine', ok: !agent.error, loading: agent.loading && !agent.data && !agent.error, error: agent.error },
  ];

  const usageBars = useMemo(
    () =>
      (agent.data?.daily ?? []).map((day) => ({
        label: formatDay(day.date),
        values: [day.input_tokens, day.output_tokens],
      })),
    [agent.data]
  );

  const signups = useMemo(() => {
    const signIns = new Map((auth.data?.sign_ins_daily ?? []).map((day) => [day.date, day.count]));
    return (auth.data?.signups_daily ?? []).map((day) => ({
      label: formatDay(day.date),
      values: [day.count, signIns.get(day.date) ?? 0],
    }));
  }, [auth.data]);

  const planSlices = (workspace.data?.plan_distribution ?? []).map((plan, index) => ({
    label: plan.name,
    value: plan.workspace_count,
    ...PLAN_COLORS[index % PLAN_COLORS.length],
  }));

  const today = agent.data?.today;
  const costLast14 = (agent.data?.daily ?? []).reduce((sum, day) => sum + day.cost_usd, 0);

  return (
    <AdminPage
      title="Platform overview"
      icon={Gauge}
      description="Everything happening across RoleSync: people, workspaces, the sales agent and what it costs. Numbers are live from each service."
      actions={<RefreshButton onClick={refreshAll} loading={refreshing} label="Refresh overview" />}
    >
      {agent.data && !agent.data.agent_enabled && (
        <Notice tone="warning" icon={PauseCircle}>
          <span className="font-semibold">The sales agent is paused for everyone.</span>{' '}
          {agent.data.maintenance_message ? `Message shown to reps: “${agent.data.maintenance_message}”. ` : ''}
          <Link to="/admin/agents" className="underline font-semibold">
            Open Agent Manager
          </Link>{' '}
          to turn it back on.
        </Notice>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
        <StatCard
          label="Accounts"
          icon={Users}
          loading={!auth.data && !auth.error}
          value={auth.data ? formatNumber(auth.data.total_users) : '—'}
          hint={auth.data ? `+${auth.data.new_last_7_days} this week · ${auth.data.suspended} suspended` : auth.error ? 'Unavailable' : undefined}
        />
        <StatCard
          label="Workspaces"
          icon={Building2}
          tone="info"
          loading={!workspace.data && !workspace.error}
          value={workspace.data ? formatNumber(workspace.data.workspaces_total) : '—'}
          hint={
            workspace.data
              ? `${workspace.data.workspaces_active} active · ${workspace.data.workspaces_suspended} suspended`
              : workspace.error
                ? 'Unavailable'
                : undefined
          }
        />
        <StatCard
          label="Agent calls today"
          icon={Activity}
          tone="success"
          loading={!agent.data && !agent.error}
          value={today ? formatNumber(today.calls) : '—'}
          hint={today ? `${today.sessions_started} conversations · ${today.active_users} reps` : agent.error ? 'Unavailable' : undefined}
        />
        <StatCard
          label="Tokens today"
          icon={Coins}
          tone="violet"
          loading={!agent.data && !agent.error}
          value={today ? formatCompact(today.input_tokens + today.output_tokens) : '—'}
          hint={today ? `${formatCompact(today.input_tokens)} in · ${formatCompact(today.output_tokens)} out` : undefined}
        />
        <StatCard
          label="Model cost today"
          icon={CircleDollarSign}
          tone="warning"
          loading={!agent.data && !agent.error}
          value={today ? formatUsd(today.cost_usd) : '—'}
          hint={agent.data ? `${formatUsd(costLast14)} over 14 days` : undefined}
        />
        <StatCard
          label="Agent runs now"
          icon={Bot}
          tone={agent.data && !agent.data.agent_enabled ? 'danger' : 'primary'}
          loading={!agent.data && !agent.error}
          value={agent.data ? formatNumber(agent.data.running_sessions) : '—'}
          hint={agent.data ? `${agent.data.awaiting_approval} waiting for approval` : undefined}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card
          className="xl:col-span-2"
          title="Sales agent usage"
          subtitle="Model tokens per day, last 14 days (UTC)"
          icon={Activity}
          actions={
            <Link to="/admin/usage" className="text-[11px] font-semibold text-primary hover:underline flex items-center gap-1">
              Usage & costs <ArrowRight className="w-3 h-3" />
            </Link>
          }
        >
          {agent.error ? (
            <ErrorBlock message={agent.error} onRetry={agent.reload} compact />
          ) : !agent.data ? (
            <LoadingBlock className="py-20" />
          ) : (
            <StackedBarChart
              data={usageBars}
              series={[
                { name: 'Input tokens', className: 'bg-primary/80' },
                { name: 'Output tokens', className: 'bg-sky-500/80' },
              ]}
              height={200}
              formatValue={formatCompact}
            />
          )}
        </Card>

        <Card title="Service health" subtitle="Reachability and configured providers" icon={ServerCog}>
          <ul className="space-y-2">
            {services.map((service) => (
              <li key={service.name} className="flex items-center justify-between gap-3 text-xs" title={service.error ?? undefined}>
                <span className="text-foreground truncate">{service.name}</span>
                {service.loading ? (
                  <Badge>Checking</Badge>
                ) : service.ok ? (
                  <Badge tone="success">
                    <CheckCircle2 className="w-3 h-3" /> Up
                  </Badge>
                ) : (
                  <Badge tone="danger">
                    <XCircle className="w-3 h-3" /> Error
                  </Badge>
                )}
              </li>
            ))}
          </ul>
          {agent.data && (
            <>
              <p className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground mt-5 mb-2">Providers</p>
              <ul className="space-y-2">
                {agent.data.providers.map((provider) => (
                  <li key={provider.name} className="flex items-center justify-between gap-3 text-xs">
                    <span className="text-foreground truncate">{provider.label}</span>
                    {provider.configured ? <Badge tone="success">Configured</Badge> : <Badge tone="warning">Not set</Badge>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card className="xl:col-span-2" title="Sign-ups and sign-ins" subtitle="Last 30 days (UTC)" icon={Users}>
          {auth.error ? (
            <ErrorBlock message={auth.error} onRetry={auth.reload} compact />
          ) : !auth.data ? (
            <LoadingBlock className="py-20" />
          ) : (
            <StackedBarChart
              data={signups}
              series={[
                { name: 'New accounts', className: 'bg-emerald-500/80' },
                { name: 'Sign-ins', className: 'bg-primary/40' },
              ]}
              height={180}
              formatValue={formatNumber}
              emptyLabel="No sign-ups or sign-ins in the last 30 days"
            />
          )}
        </Card>

        <Card title="Workspaces by plan" subtitle="Where every workspace sits today" icon={ReceiptText}>
          {workspace.error ? (
            <ErrorBlock message={workspace.error} onRetry={workspace.reload} compact />
          ) : !workspace.data ? (
            <LoadingBlock className="py-16" />
          ) : (
            <DonutChart
              slices={planSlices}
              centerLabel="workspaces"
              centerValue={formatNumber(workspace.data.workspaces_total)}
              formatValue={formatNumber}
            />
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card
          className="xl:col-span-2"
          title="Recent admin activity"
          subtitle="The latest changes made in this console"
          icon={ScrollText}
          actions={
            <Link to="/admin/audit" className="text-[11px] font-semibold text-primary hover:underline flex items-center gap-1">
              Audit log <ArrowRight className="w-3 h-3" />
            </Link>
          }
          bodyClassName="p-0"
        >
          {!audit.data && !audit.error ? (
            <LoadingBlock className="py-12" />
          ) : (audit.data ?? []).length === 0 ? (
            <p className="text-xs text-muted-foreground px-5 py-10 text-center">No admin changes yet. They’ll appear here.</p>
          ) : (
            <ul className="divide-y divide-border/60">
              {(audit.data ?? []).map((entry: AuditEntry) => {
                const meta = AUDIT_SERVICE_META[entry.service];
                const Icon = meta.icon;
                return (
                  <li key={`${entry.service}-${entry.id}`} className="px-5 py-3 flex items-start gap-3">
                    <div className={`w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 ${meta.iconClass}`}>
                      <Icon className="w-4 h-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs text-foreground leading-snug">{entry.summary}</p>
                      <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
                        {entry.actor_email ?? 'A super admin'} · {meta.label}
                      </p>
                    </div>
                    <span className="text-[11px] text-muted-foreground whitespace-nowrap" title={formatDateTime(entry.created_at)}>
                      {timeAgo(entry.created_at)}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title="Quick actions" icon={ArrowRight} bodyClassName="p-3">
          <ul className="space-y-1">
            {QUICK_LINKS.map(({ to, label, description, icon: Icon }) => (
              <li key={to}>
                <Link to={to} className="group flex items-center gap-3 rounded-xl px-3 py-2.5 hover:bg-muted/60 transition-colors">
                  <div className="w-8 h-8 rounded-lg bg-muted/70 text-muted-foreground group-hover:bg-primary/15 group-hover:text-primary flex items-center justify-center shrink-0 transition-colors">
                    <Icon className="w-4 h-4" />
                  </div>
                  <span className="min-w-0 flex-1">
                    <span className="block text-xs font-semibold text-foreground">{label}</span>
                    <span className="block text-[11px] text-muted-foreground truncate">{description}</span>
                  </span>
                  <ArrowRight className="w-3.5 h-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {agent.data && (
        <Card title="Model cost trend" subtitle="Estimated model spend per day, last 14 days" icon={CircleDollarSign}>
          <AreaChart
            points={agent.data.daily.map((day) => ({ label: formatDay(day.date), value: day.cost_usd }))}
            colorClass="text-amber-500"
            formatValue={formatUsd}
            height={140}
            emptyLabel="No model spend in the last 14 days"
          />
          <p className="text-[11px] text-muted-foreground mt-3 flex items-center gap-1.5">
            <AlertTriangle className="w-3 h-3" />
            Estimates use the rates on the Models page. Free OpenRouter models count as $0.
          </p>
        </Card>
      )}
    </AdminPage>
  );
};

export default AdminOverview;
