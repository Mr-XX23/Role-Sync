import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Ban, Building2, CircleCheck, Eye } from 'lucide-react';
import { adminApi } from '../../api/adminApi';
import type { WorkspaceFilters } from '../../api/adminApi';
import {
  AdminPage,
  Avatar,
  Badge,
  EmptyBlock,
  ErrorBlock,
  IconAction,
  LoadingBlock,
  Pagination,
  RefreshButton,
  SearchInput,
  StatCard,
  TableHead,
  TableShell,
  Th,
  selectClass,
} from './components/AdminUi';
import { formatCompact, formatDate, formatDateTime, formatNumber, initials } from './adminFormat';
import { useAdminQuery } from './useAdminQuery';
import { useWorkspaceActions } from './useWorkspaceActions';
import { WorkspaceDetailDrawer } from './WorkspaceDetailDrawer';

const PAGE_SIZE = 25;

export const AdminWorkspaces: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const openWorkspace = searchParams.get('open');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<'active' | 'suspended' | ''>('');
  const [planId, setPlanId] = useState('');
  const [page, setPage] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search.trim());
      setPage(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const filters: WorkspaceFilters = { q: query, status, plan_id: planId, page, size: PAGE_SIZE };
  const list = useAdminQuery(() => adminApi.workspaces(filters), JSON.stringify(filters));
  const stats = useAdminQuery(() => adminApi.workspaceStats(30), 'workspace-stats');
  const plans = useAdminQuery(() => adminApi.plans(), 'plans');
  const usage = useAdminQuery(() => adminApi.usage(30), 'usage:30');

  const refresh = () => {
    list.reload();
    stats.reload();
    usage.reload();
  };
  const actions = useWorkspaceActions(() => refresh());

  const usageByWorkspace = useMemo(
    () => new Map((usage.data?.by_workspace ?? []).map((row) => [row.workspace_id, row])),
    [usage.data]
  );

  const setOpen = (workspaceId: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (workspaceId) next.set('open', workspaceId);
    else next.delete('open');
    setSearchParams(next, { replace: true });
  };

  const workspaces = list.data?.items ?? [];

  return (
    <AdminPage
      title="Workspaces"
      icon={Building2}
      description="Every workspace on the platform with its owner, members and plan. Suspending a workspace blocks its members from its data and the sales agent without deleting anything."
      actions={<RefreshButton onClick={refresh} loading={list.loading} label="Refresh workspaces" />}
    >
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Workspaces" icon={Building2} loading={!stats.data && !stats.error} value={formatNumber(stats.data?.workspaces_total)} hint={stats.data ? `${stats.data.workspaces_active} active` : undefined} />
        <StatCard label="Suspended" icon={Ban} tone="danger" loading={!stats.data && !stats.error} value={formatNumber(stats.data?.workspaces_suspended)} />
        <StatCard label="Active memberships" tone="success" loading={!stats.data && !stats.error} value={formatNumber(stats.data?.memberships_active)} hint={stats.data ? `${stats.data.profiles_total} people with a profile` : undefined} />
        <StatCard label="Deals" tone="info" loading={!stats.data && !stats.error} value={formatNumber(stats.data?.deals_total)} hint={stats.data ? `${stats.data.deals_open} open` : undefined} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <SearchInput value={search} onChange={setSearch} placeholder="Search workspace or owner name…" />
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as 'active' | 'suspended' | '');
            setPage(0);
          }}
          aria-label="Filter by status"
          className={selectClass}
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
        </select>
        <select
          value={planId}
          onChange={(event) => {
            setPlanId(event.target.value);
            setPage(0);
          }}
          aria-label="Filter by plan"
          className={selectClass}
        >
          <option value="">All plans</option>
          {(plans.data ?? []).map((plan) => (
            <option key={plan.plan_id} value={plan.plan_id}>
              {plan.name}
              {plan.is_default ? ' (default)' : ''}
              {plan.is_archived ? ' (archived)' : ''}
            </option>
          ))}
        </select>
      </div>

      {list.error && !list.data ? (
        <ErrorBlock message={list.error} onRetry={list.reload} />
      ) : !list.data ? (
        <LoadingBlock />
      ) : (
        <TableShell
          footer={
            <Pagination
              page={list.data.page}
              totalPages={list.data.total_pages}
              total={list.data.total}
              size={list.data.size}
              onPage={setPage}
              disabled={list.loading}
            />
          }
        >
          <TableHead>
            <Th>Workspace</Th>
            <Th>Owner</Th>
            <Th>Members</Th>
            <Th>Plan</Th>
            <Th>Agent tokens · 30d</Th>
            <Th>Created</Th>
            <Th className="text-right">Actions</Th>
          </TableHead>
          <tbody className={`divide-y divide-border/60 ${list.loading ? 'opacity-60' : ''}`}>
            {workspaces.map((workspace) => {
              const agentUsage = usageByWorkspace.get(workspace.workspace_id);
              return (
                <tr key={workspace.workspace_id} className={`hover:bg-muted/20 transition-colors ${workspace.is_active ? '' : 'bg-red-500/[0.03]'}`}>
                  <td className="px-4 py-3">
                    <button type="button" onClick={() => setOpen(workspace.workspace_id)} className="flex items-center gap-3 min-w-[14rem] text-left cursor-pointer group">
                      <Avatar text={initials(workspace.name)} tone={workspace.is_active ? 'info' : 'danger'} />
                      <span className="min-w-0">
                        <span className="flex items-center gap-1.5 font-semibold text-foreground group-hover:underline truncate">
                          {workspace.name}
                          {!workspace.is_active && <Badge tone="danger">Suspended</Badge>}
                        </span>
                        <span className="block text-[11px] text-muted-foreground truncate max-w-[18rem]">
                          {workspace.description || 'No description'}
                        </span>
                      </span>
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    {workspace.owner ? (
                      <span className="block min-w-0">
                        <span className="block text-foreground truncate">{workspace.owner.name}</span>
                        <span className="block text-[11px] text-muted-foreground truncate">{workspace.owner.email ?? 'Email unavailable'}</span>
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 tabular-nums text-foreground">{formatNumber(workspace.member_count)}</td>
                  <td className="px-4 py-3">
                    <Badge tone={workspace.plan_assigned ? 'primary' : 'neutral'} title={workspace.plan_assigned ? 'Assigned plan' : 'Uses the default plan'}>
                      {workspace.plan.name}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 tabular-nums text-muted-foreground">
                    {usage.data ? (agentUsage ? formatCompact(agentUsage.input_tokens + agentUsage.output_tokens) : '0') : '…'}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap" title={formatDateTime(workspace.created_at)}>
                    {formatDate(workspace.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-0.5">
                      <IconAction icon={Eye} label="View details" onClick={() => setOpen(workspace.workspace_id)} />
                      {workspace.is_active ? (
                        <IconAction icon={Ban} label="Suspend workspace" tone="danger" disabled={actions.busy} onClick={() => actions.suspend(workspace)} />
                      ) : (
                        <IconAction icon={CircleCheck} label="Reactivate workspace" tone="success" disabled={actions.busy} onClick={() => actions.reactivate(workspace)} />
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
          {workspaces.length === 0 && (
            <tbody>
              <tr>
                <td colSpan={7}>
                  <EmptyBlock icon={Building2} title="No workspaces match" description="Try a different search or clear the filters." />
                </td>
              </tr>
            </tbody>
          )}
        </TableShell>
      )}

      {openWorkspace && (
        <WorkspaceDetailDrawer
          workspaceId={openWorkspace}
          plans={plans.data ?? []}
          usage={usageByWorkspace.get(openWorkspace)}
          usageLoaded={Boolean(usage.data)}
          onClose={() => setOpen(null)}
          onChanged={refresh}
        />
      )}
      {actions.dialog}
    </AdminPage>
  );
};

export default AdminWorkspaces;
