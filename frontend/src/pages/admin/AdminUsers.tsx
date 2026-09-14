import React, { useEffect, useState } from 'react';
import { Eye, LogOut, ShieldCheck, Unlock, UserCheck, Users, UserX } from 'lucide-react';
import { adminApi } from '../../api/adminApi';
import type { AccountStatus, LoginType, UserFilters } from '../../api/adminApi';
import { useAppSelector } from '../../store';
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
import { formatDate, formatDateTime, formatNumber, initials, timeAgo } from './adminFormat';
import { useAdminQuery } from './useAdminQuery';
import { LOGIN_TYPE_LABEL, STATUS_META, userDisplayName } from './userMeta';
import { useUserActions } from './useUserActions';
import { UserDetailDrawer } from './UserDetailDrawer';

const PAGE_SIZE = 25;

export const AdminUsers: React.FC = () => {
  const myId = useAppSelector((state) => state.auth.user?.userId);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<AccountStatus | ''>('');
  const [verified, setVerified] = useState<'true' | 'false' | ''>('');
  const [loginType, setLoginType] = useState<LoginType | ''>('');
  const [page, setPage] = useState(0);
  const [openUser, setOpenUser] = useState<string | null>(null);

  // Search as they type, without a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search.trim());
      setPage(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const filters: UserFilters = { q: query, status, verified, login_type: loginType, page, size: PAGE_SIZE };
  const list = useAdminQuery(() => adminApi.users(filters), JSON.stringify(filters));
  const stats = useAdminQuery(() => adminApi.authStats(30), 'auth-stats');

  const refresh = () => {
    list.reload();
    stats.reload();
  };
  const actions = useUserActions(refresh);

  const changeFilter = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value);
    setPage(0);
  };

  const users = list.data?.items ?? [];

  return (
    <AdminPage
      title="Users"
      icon={Users}
      description="Every account on the platform. Suspend someone to block sign-in, end their sessions, or unlock them after too many failed attempts."
      actions={<RefreshButton onClick={refresh} loading={list.loading} label="Refresh users" />}
    >
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="All accounts" loading={!stats.data && !stats.error} value={formatNumber(stats.data?.total_users)} hint={stats.data ? `+${stats.data.new_last_30_days} in 30 days` : undefined} />
        <StatCard label="Active" tone="success" loading={!stats.data && !stats.error} value={formatNumber(stats.data?.active)} hint={stats.data ? `${stats.data.email_verified} verified emails` : undefined} />
        <StatCard label="Suspended" tone="danger" loading={!stats.data && !stats.error} value={formatNumber(stats.data?.suspended)} hint={stats.data ? `${stats.data.locked} locked` : undefined} />
        <StatCard
          label="Super admins"
          tone="violet"
          loading={!stats.data && !stats.error}
          value={formatNumber(stats.data?.super_admin_emails.length)}
          hint={stats.data?.super_admin_emails.join(', ') || 'Set on the server'}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <SearchInput value={search} onChange={setSearch} placeholder="Search name, email or phone…" />
        <select value={status} onChange={(event) => changeFilter(setStatus)(event.target.value as AccountStatus | '')} aria-label="Filter by status" className={selectClass}>
          <option value="">All statuses</option>
          {(Object.keys(STATUS_META) as AccountStatus[]).map((key) => (
            <option key={key} value={key}>
              {STATUS_META[key].label}
            </option>
          ))}
        </select>
        <select value={verified} onChange={(event) => changeFilter(setVerified)(event.target.value as 'true' | 'false' | '')} aria-label="Filter by email verification" className={selectClass}>
          <option value="">Any verification</option>
          <option value="true">Email verified</option>
          <option value="false">Email not verified</option>
        </select>
        <select value={loginType} onChange={(event) => changeFilter(setLoginType)(event.target.value as LoginType | '')} aria-label="Filter by sign-in method" className={selectClass}>
          <option value="">Any sign-in method</option>
          {(Object.keys(LOGIN_TYPE_LABEL) as LoginType[]).map((key) => (
            <option key={key} value={key}>
              {LOGIN_TYPE_LABEL[key]}
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
            <Th>Account</Th>
            <Th>Status</Th>
            <Th>Sign-in</Th>
            <Th>Last sign-in</Th>
            <Th>Created</Th>
            <Th className="text-right">Actions</Th>
          </TableHead>
          <tbody className={`divide-y divide-border/60 ${list.loading ? 'opacity-60' : ''}`}>
            {users.map((user) => {
              const isMe = user.user_id === myId;
              const protectedAccount = isMe || user.super_admin;
              return (
                <tr key={user.user_id} className="hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-3">
                    <button type="button" onClick={() => setOpenUser(user.user_id)} className="flex items-center gap-3 min-w-[15rem] text-left cursor-pointer group">
                      <Avatar text={initials(userDisplayName(user))} tone={user.super_admin ? 'violet' : 'primary'} />
                      <span className="min-w-0">
                        <span className="flex items-center gap-1.5 font-semibold text-foreground group-hover:underline truncate">
                          {userDisplayName(user)}
                          {isMe && <span className="text-[10px] font-normal text-muted-foreground">(you)</span>}
                        </span>
                        <span className="block text-[11px] text-muted-foreground truncate">{user.email}</span>
                      </span>
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-1">
                      <Badge tone={STATUS_META[user.status]?.tone ?? 'neutral'} title={STATUS_META[user.status]?.description}>
                        {STATUS_META[user.status]?.label ?? user.status}
                      </Badge>
                      {user.super_admin && (
                        <Badge tone="violet">
                          <ShieldCheck className="w-3 h-3" /> Super admin
                        </Badge>
                      )}
                      {user.locked_out && <Badge tone="warning">Locked out</Badge>}
                      {!user.email_verified && user.status !== 'INACTIVE' && <Badge tone="neutral">Email unverified</Badge>}
                      {user.must_change_password && <Badge tone="info">Invite pending</Badge>}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                    {LOGIN_TYPE_LABEL[user.login_type] ?? user.login_type}
                    {user.provisioned && <p className="text-[10px]">Added by a workspace admin</p>}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap" title={formatDateTime(user.last_login_at)}>
                    {user.last_login_at ? timeAgo(user.last_login_at) : 'Never'}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap" title={formatDateTime(user.created_at)}>
                    {formatDate(user.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-0.5">
                      <IconAction icon={Eye} label="View details" onClick={() => setOpenUser(user.user_id)} />
                      {user.locked_out && <IconAction icon={Unlock} label="Unlock sign-in" disabled={actions.busy} onClick={() => actions.ask('unlock', user)} />}
                      {!isMe && (
                        <IconAction icon={LogOut} label="Sign out everywhere" disabled={actions.busy} onClick={() => actions.ask('sign-out', user)} />
                      )}
                      {user.status === 'SUSPENDED' || user.status === 'LOCKED' ? (
                        <IconAction icon={UserCheck} label="Reactivate" tone="success" disabled={actions.busy} onClick={() => actions.ask('reactivate', user)} />
                      ) : (
                        !protectedAccount && (
                          <IconAction icon={UserX} label="Suspend" tone="danger" disabled={actions.busy} onClick={() => actions.ask('suspend', user)} />
                        )
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
          {users.length === 0 && (
            <tbody>
              <tr>
                <td colSpan={6}>
                  <EmptyBlock title="No accounts match" description="Try a different search or clear the filters." />
                </td>
              </tr>
            </tbody>
          )}
        </TableShell>
      )}

      {openUser && (
        <UserDetailDrawer
          userId={openUser}
          isMe={openUser === myId}
          onClose={() => setOpenUser(null)}
          onChanged={refresh}
        />
      )}
      {actions.dialog}
    </AdminPage>
  );
};

export default AdminUsers;
