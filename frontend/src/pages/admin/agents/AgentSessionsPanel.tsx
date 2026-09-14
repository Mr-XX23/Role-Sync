import React, { useEffect, useState } from 'react';
import { MessagesSquare, OctagonX } from 'lucide-react';
import { adminApi, adminErrorStatus, describeAdminError } from '../../../api/adminApi';
import type { AdminSession, SessionStatus } from '../../../api/adminApi';
import { Button } from '../../../components/common/Button';
import { useToast } from '../../../context/ToastContext';
import {
  Badge,
  ConfirmAction,
  EmptyBlock,
  ErrorBlock,
  LoadingBlock,
  Notice,
  RefreshButton,
  Switch,
  TableHead,
  TableShell,
  Th,
  selectClass,
} from '../components/AdminUi';
import { formatCompact, formatDateTime, formatNumber, formatUsd, shortId, timeAgo } from '../adminFormat';
import { useAdminQuery } from '../useAdminQuery';
import { useDirectory } from '../useDirectory';
import { SESSION_STATUS_META } from './agentMeta';
import { userDisplayName } from '../userMeta';

const LIVE: SessionStatus[] = ['RUNNING', 'AWAITING_APPROVAL'];

export const AgentSessionsPanel: React.FC = () => {
  const toast = useToast();
  const directory = useDirectory();
  const [status, setStatus] = useState<SessionStatus | ''>('');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [stopping, setStopping] = useState<AdminSession | null>(null);
  const [busy, setBusy] = useState(false);
  const sessions = useAdminQuery(() => adminApi.sessions(status, 100), `sessions:${status}`);
  const { reload } = sessions;

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = setInterval(reload, 10000);
    return () => clearInterval(timer);
  }, [autoRefresh, reload]);

  const stop = async () => {
    if (!stopping) return;
    setBusy(true);
    try {
      await adminApi.stopSession(stopping.id);
      toast.success('The request stops at its next step. The rep sees that an administrator stopped it.', 'Stopping the request');
      setStopping(null);
      reload();
    } catch (error) {
      toast.error(describeAdminError(error), 'Couldn’t stop the request');
      setStopping(null);
      if (adminErrorStatus(error) === 409) reload();
    } finally {
      setBusy(false);
    }
  };

  const rows = sessions.data ?? [];
  const live = rows.filter((row) => LIVE.includes(row.status)).length;

  return (
    <div className="space-y-4">
      <Notice tone="info" icon={MessagesSquare}>
        Conversations are private to the rep who started them, so only their status, size and cost are shown here, never what
        was said.
      </Notice>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <select value={status} onChange={(event) => setStatus(event.target.value as SessionStatus | '')} aria-label="Filter by status" className={selectClass}>
            <option value="">All statuses</option>
            {(Object.keys(SESSION_STATUS_META) as SessionStatus[]).map((key) => (
              <option key={key} value={key}>
                {SESSION_STATUS_META[key].label}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <Switch size="sm" label="Refresh every 10 seconds" checked={autoRefresh} onChange={setAutoRefresh} />
            Live refresh
          </label>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            {formatNumber(live)} in progress of {formatNumber(rows.length)} shown
          </span>
          <RefreshButton onClick={reload} loading={sessions.loading} label="Refresh conversations" />
        </div>
      </div>

      {sessions.error && !sessions.data ? (
        <ErrorBlock message={sessions.error} onRetry={reload} />
      ) : !sessions.data ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <div className="rounded-2xl border border-border/80 bg-card">
          <EmptyBlock icon={MessagesSquare} title="No conversations" description="Agent conversations appear here as reps use the sales agent." />
        </div>
      ) : (
        <TableShell>
          <TableHead>
            <Th>Conversation</Th>
            <Th>Workspace</Th>
            <Th>Rep</Th>
            <Th>Status</Th>
            <Th>Requests</Th>
            <Th>Tokens</Th>
            <Th>Cost</Th>
            <Th>Tool calls</Th>
            <Th>Last activity</Th>
            <Th className="text-right">Actions</Th>
          </TableHead>
          <tbody className="divide-y divide-border/60">
            {rows.map((row) => {
              const workspace = directory.workspace(row.workspace_id);
              const user = directory.user(row.user_id);
              const meta = SESSION_STATUS_META[row.status] ?? { label: row.status, tone: 'neutral' as const };
              const canStop = LIVE.includes(row.status) && !row.stop_requested;
              return (
                <tr key={row.id} className="hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-3">
                    <span className="font-mono text-foreground" title={row.id}>
                      {shortId(row.id)}
                    </span>
                    <span className="block text-[10px] text-muted-foreground">
                      {row.mode === 'AUTONOMOUS' ? 'Autonomous' : 'Chat'} · started {timeAgo(row.started_at)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="block text-foreground truncate max-w-[12rem]" title={row.workspace_id}>
                      {workspace?.name ?? shortId(row.workspace_id)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="block text-foreground truncate max-w-[12rem]" title={user?.email ?? row.user_id}>
                      {user ? userDisplayName(user) : shortId(row.user_id)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-1">
                      <Badge tone={meta.tone}>{meta.label}</Badge>
                      {row.stop_requested && LIVE.includes(row.status) && <Badge tone="danger">Stopping</Badge>}
                    </div>
                  </td>
                  <td className="px-4 py-3 tabular-nums">{formatNumber(row.turns)}</td>
                  <td className="px-4 py-3 tabular-nums">{formatCompact(row.tokens)}</td>
                  <td className="px-4 py-3 tabular-nums">{formatUsd(row.cost_usd)}</td>
                  <td className="px-4 py-3 tabular-nums">{formatNumber(row.tool_calls)}</td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap" title={formatDateTime(row.updated_at ?? row.started_at)}>
                    {timeAgo(row.updated_at ?? row.started_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {canStop ? (
                      <Button variant="outline" className="px-2.5 py-1.5 w-auto text-[11px] text-destructive hover:text-destructive" icon={<OctagonX className="w-3.5 h-3.5" />} iconPosition="left" onClick={() => setStopping(row)}>
                        Stop
                      </Button>
                    ) : (
                      <span className="text-[11px] text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </TableShell>
      )}

      {stopping && (
        <ConfirmAction
          destructive
          title="Stop this request?"
          message={
            stopping.status === 'AWAITING_APPROVAL' ? (
              <>
                This conversation is waiting for the rep’s approval. Stopping it expires the pending approvals, so nothing more
                happens, and the rep is told an administrator stopped it.
              </>
            ) : (
              <>The agent stops at its next step, before running anything else. Actions it already completed stay done.</>
            )
          }
          confirmLabel="Stop request"
          busyLabel="Stopping…"
          busy={busy}
          onConfirm={() => void stop()}
          onCancel={() => setStopping(null)}
        />
      )}
    </div>
  );
};
