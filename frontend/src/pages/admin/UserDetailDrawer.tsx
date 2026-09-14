import React from 'react';
import { Link } from 'react-router-dom';
import { Building2, History, LogOut, ShieldCheck, Unlock, UserCheck, UserX } from 'lucide-react';
import { adminApi } from '../../api/adminApi';
import { Button } from '../../components/common/Button';
import { Avatar, Badge, Drawer, ErrorBlock, KeyValue, LoadingBlock, Notice } from './components/AdminUi';
import { formatCompact, formatDateTime, formatNumber, formatUsd, humanize, initials, timeAgo } from './adminFormat';
import { useAdminQuery } from './useAdminQuery';
import { useUserActions } from './useUserActions';
import { LOGIN_TYPE_LABEL, SECURITY_EVENT_LABEL, STATUS_META, userDisplayName } from './userMeta';

const ROLE_TONE: Record<string, 'primary' | 'info' | 'success' | 'neutral'> = {
  OWNER: 'primary',
  ADMIN: 'info',
  MEMBER: 'success',
  VIEWER: 'neutral',
};

export const UserDetailDrawer: React.FC<{
  userId: string;
  isMe: boolean;
  onClose: () => void;
  onChanged: () => void;
}> = ({ userId, isMe, onClose, onChanged }) => {
  const detail = useAdminQuery(() => adminApi.user(userId), `user:${userId}`);
  const workspaces = useAdminQuery(() => adminApi.userWorkspaces(userId), `user-workspaces:${userId}`);
  const usage = useAdminQuery(() => adminApi.usage(30), 'usage:30');
  const actions = useUserActions(() => {
    detail.reload();
    onChanged();
  });

  const user = detail.data?.user;
  const agentUsage = usage.data?.by_user.find((row) => row.user_id === userId);

  return (
    <Drawer
      title={user ? userDisplayName(user) : 'Account'}
      subtitle={user?.email}
      onClose={onClose}
      footer={
        user && (
          <div className="flex flex-wrap items-center justify-end gap-2">
            {user.locked_out && (
              <Button variant="outline" className="px-3 py-2 w-auto text-xs" icon={<Unlock className="w-3.5 h-3.5" />} iconPosition="left" disabled={actions.busy} onClick={() => actions.ask('unlock', user)}>
                Unlock
              </Button>
            )}
            {!isMe && (
              <Button variant="outline" className="px-3 py-2 w-auto text-xs" icon={<LogOut className="w-3.5 h-3.5" />} iconPosition="left" disabled={actions.busy} onClick={() => actions.ask('sign-out', user)}>
                Sign out everywhere
              </Button>
            )}
            {user.status === 'SUSPENDED' || user.status === 'LOCKED' ? (
              <Button className="px-3 py-2 w-auto text-xs" icon={<UserCheck className="w-3.5 h-3.5" />} iconPosition="left" disabled={actions.busy} onClick={() => actions.ask('reactivate', user)}>
                Reactivate
              </Button>
            ) : (
              !isMe &&
              !user.super_admin && (
                <Button variant="destructive" className="px-3 py-2 w-auto text-xs" icon={<UserX className="w-3.5 h-3.5" />} iconPosition="left" disabled={actions.busy} onClick={() => actions.ask('suspend', user)}>
                  Suspend
                </Button>
              )
            )}
          </div>
        )
      }
    >
      {detail.error && !detail.data ? (
        <ErrorBlock message={detail.error} onRetry={detail.reload} />
      ) : !user || !detail.data ? (
        <LoadingBlock />
      ) : (
        <>
          <div className="flex items-center gap-4">
            <Avatar text={initials(userDisplayName(user))} tone={user.super_admin ? 'violet' : 'primary'} size="lg" />
            <div className="min-w-0 space-y-1.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone={STATUS_META[user.status]?.tone ?? 'neutral'}>{STATUS_META[user.status]?.label ?? user.status}</Badge>
                {user.super_admin && (
                  <Badge tone="violet">
                    <ShieldCheck className="w-3 h-3" /> Super admin
                  </Badge>
                )}
                {user.locked_out && <Badge tone="warning">Locked out</Badge>}
                {user.must_change_password && <Badge tone="info">Hasn’t chosen a password yet</Badge>}
                {isMe && <Badge>You</Badge>}
              </div>
              <p className="text-xs text-muted-foreground">{STATUS_META[user.status]?.description}</p>
            </div>
          </div>

          {user.super_admin && (
            <Notice tone="info" icon={ShieldCheck}>
              Super admins are set on the server (<code className="font-mono">PLATFORM_SUPER_ADMIN_EMAILS</code>), so this
              account can’t be suspended here. Remove the address from that setting first.
            </Notice>
          )}

          <dl className="grid grid-cols-2 gap-x-6 gap-y-4">
            <KeyValue label="Email">
              {user.email}{' '}
              {user.email_verified ? <Badge tone="success">Verified</Badge> : <Badge tone="warning">Not verified</Badge>}
            </KeyValue>
            <KeyValue label="Phone">
              {user.phone_number ?? '—'} {user.phone_number && user.phone_verified && <Badge tone="success">Verified</Badge>}
            </KeyValue>
            <KeyValue label="Signs in with">{LOGIN_TYPE_LABEL[user.login_type] ?? user.login_type}</KeyValue>
            <KeyValue label="Active sessions">{formatNumber(detail.data.active_sessions)}</KeyValue>
            <KeyValue label="Last sign-in">
              <span title={formatDateTime(user.last_login_at)}>{user.last_login_at ? timeAgo(user.last_login_at) : 'Never'}</span>
            </KeyValue>
            <KeyValue label="Created">{formatDateTime(user.created_at)}</KeyValue>
            <KeyValue label="How they joined">{user.provisioned ? 'Added by a workspace admin' : 'Signed up themselves'}</KeyValue>
            <KeyValue label="Account id">
              <span className="font-mono text-xs break-all">{user.user_id}</span>
            </KeyValue>
          </dl>

          <section className="space-y-2">
            <h4 className="text-xs font-bold text-foreground flex items-center gap-2">
              <Building2 className="w-4 h-4 text-muted-foreground" /> Workspaces
            </h4>
            {workspaces.error ? (
              <ErrorBlock message={workspaces.error} onRetry={workspaces.reload} compact />
            ) : !workspaces.data ? (
              <LoadingBlock className="py-6" />
            ) : workspaces.data.length === 0 ? (
              <p className="text-xs text-muted-foreground">Not in any workspace yet.</p>
            ) : (
              <ul className="rounded-xl border border-border/70 divide-y divide-border/60 overflow-hidden">
                {workspaces.data.map((ws) => (
                  <li key={ws.workspace_id} className="px-3 py-2.5 flex items-center justify-between gap-3 text-xs">
                    <span className="min-w-0">
                      <Link to={`/admin/workspaces?open=${ws.workspace_id}`} className="block font-semibold text-foreground truncate hover:underline">
                        {ws.name}
                      </Link>
                      <span className="text-[11px] text-muted-foreground">Joined {timeAgo(ws.joined_at)}</span>
                    </span>
                    <span className="flex items-center gap-1 shrink-0">
                      {!ws.is_active && <Badge tone="danger">Suspended</Badge>}
                      {!ws.membership_active && <Badge>Deactivated</Badge>}
                      <Badge tone={ROLE_TONE[ws.role] ?? 'neutral'}>{ws.is_owner ? 'Owner' : humanize(ws.role)}</Badge>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-2">
            <h4 className="text-xs font-bold text-foreground">Sales agent, last 30 days</h4>
            {usage.error ? (
              <p className="text-xs text-muted-foreground">Usage isn’t available right now.</p>
            ) : !usage.data ? (
              <LoadingBlock className="py-6" />
            ) : agentUsage ? (
              <div className="grid grid-cols-3 gap-2">
                {[
                  { label: 'Conversations', value: formatNumber(agentUsage.sessions) },
                  { label: 'Tokens', value: formatCompact(agentUsage.input_tokens + agentUsage.output_tokens) },
                  { label: 'Model cost', value: formatUsd(agentUsage.cost_usd) },
                ].map((item) => (
                  <div key={item.label} className="rounded-xl border border-border/70 px-3 py-2">
                    <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">{item.label}</p>
                    <p className="text-sm font-bold text-foreground tabular-nums">{item.value}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">No sales agent use in the last 30 days (or not among the 50 heaviest users).</p>
            )}
          </section>

          <section className="space-y-2">
            <h4 className="text-xs font-bold text-foreground flex items-center gap-2">
              <History className="w-4 h-4 text-muted-foreground" /> Recent security events
            </h4>
            {detail.data.recent_events.length === 0 ? (
              <p className="text-xs text-muted-foreground">Nothing recorded yet.</p>
            ) : (
              <ol className="relative border-l border-border/70 ml-1.5 space-y-3">
                {detail.data.recent_events.map((event, index) => (
                  <li key={`${event.event_type}-${event.event_time}-${index}`} className="pl-4 relative">
                    <span
                      className={`absolute -left-[5px] top-1.5 w-2.5 h-2.5 rounded-full border-2 border-card ${
                        event.event_type.includes('FAIL') ? 'bg-red-500' : 'bg-emerald-500'
                      }`}
                    />
                    <p className="text-xs text-foreground">{SECURITY_EVENT_LABEL[event.event_type] ?? humanize(event.event_type)}</p>
                    <p className="text-[11px] text-muted-foreground">
                      <span title={formatDateTime(event.event_time)}>{timeAgo(event.event_time)}</span>
                      {event.ip_address ? ` · ${event.ip_address}` : ''}
                    </p>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
      {actions.dialog}
    </Drawer>
  );
};
