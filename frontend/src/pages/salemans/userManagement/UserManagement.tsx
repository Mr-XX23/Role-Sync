import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  History,
  Loader2,
  MailPlus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserPlus,
  Users,
  UserX,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Button } from '../../../components/common/Button';
import { useToast } from '../../../context/ToastContext';
import { useAppDispatch, useAppSelector } from '../../../store';
import { fetchWorkspaces } from '../../../store/workspaceSlice';
import { describeMemberError, memberErrorStatus, membersApi } from '../../../api/membersApi';
import type { AssignableRole, InviteResult, Member, MemberList, MemberRole } from '../../../api/membersApi';
import { AddUserModal } from './AddUserModal';
import { ConfirmDialog } from './ConfirmDialog';
import { MemberActivity } from './MemberActivity';
import { RolesGuide } from './RolesGuide';
import {
  ROLE_META,
  STATUS_META,
  describeInviteResult,
  formatDate,
  formatDateTime,
  initials,
  memberStatus,
  timeAgo,
} from './memberFormat';
import type { StatusKey } from './memberFormat';

type Tab = 'members' | 'activity' | 'roles';
type StatusFilter = 'all' | StatusKey;

interface Loaded {
  key: string;
  workspaceId: string | undefined;
  list: MemberList | null;
  error: string | null;
}

/** A member change waiting for confirmation. */
type Pending =
  | { kind: 'role'; member: Member; role: AssignableRole }
  | { kind: 'deactivate' | 'reactivate' | 'remove' | 'resend'; member: Member };

const Stat: React.FC<{ label: string; value: number }> = ({ label, value }) => (
  <div className="bg-card border border-border/70 rounded-xl px-4 py-3 shadow-2xs min-w-0">
    <p className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground">{label}</p>
    <p className="text-lg font-bold text-foreground tabular-nums">{value}</p>
  </div>
);

const Badge: React.FC<{ className: string; children: React.ReactNode }> = ({ className, children }) => (
  <span className={`inline-block text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded-md border whitespace-nowrap ${className}`}>
    {children}
  </span>
);

const IconAction: React.FC<{
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  disabled: boolean;
  danger?: boolean;
}> = ({ icon: Icon, label, onClick, disabled, danger = false }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    title={label}
    aria-label={label}
    className={`p-1.5 rounded-lg transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${
      danger
        ? 'text-muted-foreground hover:text-destructive hover:bg-destructive/10'
        : 'text-muted-foreground hover:text-foreground hover:bg-muted'
    }`}
  >
    <Icon className="w-4 h-4" />
  </button>
);

const TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'members', label: 'Members', icon: Users },
  { id: 'activity', label: 'Activity', icon: History },
  { id: 'roles', label: 'Roles & permissions', icon: ShieldCheck },
];

export const UserManagement: React.FC = () => {
  const toast = useToast();
  const dispatch = useAppDispatch();
  const workspaceId = useAppSelector((state) => state.workspace.currentWorkspace?.workspaceId);
  const workspaceName = useAppSelector((state) => state.workspace.currentWorkspace?.name) ?? 'this workspace';
  const role = useAppSelector((state) => state.workspace.currentWorkspace?.role);
  const isAdmin = role === 'OWNER' || role === 'ADMIN';

  const [tab, setTab] = useState<Tab>('members');
  const [refreshes, setRefreshes] = useState(0);
  const [changes, setChanges] = useState(0); // member changes made here, so the activity tab reloads
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [roleFilter, setRoleFilter] = useState<'all' | MemberRole>('all');
  const [adding, setAdding] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);

  const requestKey = `${workspaceId}:${refreshes}:${changes}`;
  useEffect(() => {
    if (!isAdmin) return;
    let active = true;
    membersApi
      .list()
      .then((list) => {
        if (active) setLoaded({ key: requestKey, workspaceId, list, error: null });
      })
      .catch((error) => {
        if (!active) return;
        setLoaded({ key: requestKey, workspaceId, list: null, error: describeMemberError(error) });
        if (memberErrorStatus(error) === 403) {
          // Our role may have changed since the workspace loaded: refresh it (and the sidebar).
          void dispatch(fetchWorkspaces());
        }
      });
    return () => {
      active = false;
    };
  }, [requestKey, workspaceId, isAdmin, dispatch]);

  const loading = loaded?.key !== requestKey;
  const current = loaded && loaded.workspaceId === workspaceId ? loaded : null;
  const list = current?.list ?? null;
  const members = useMemo(() => list?.members ?? [], [list]);

  const visible = useMemo(() => {
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return members.filter((member) => {
      if (statusFilter !== 'all' && memberStatus(member) !== statusFilter) return false;
      if (roleFilter !== 'all' && member.role !== roleFilter) return false;
      const text = [member.name, member.email, member.job_title].filter(Boolean).join(' ').toLowerCase();
      return words.every((word) => text.includes(word));
    });
  }, [members, query, statusFilter, roleFilter]);

  const stats = useMemo(() => {
    const active = members.filter((member) => member.active);
    return {
      active: active.length,
      pending: active.filter((member) => member.invite_status !== null).length,
      admins: active.filter((member) => member.role === 'OWNER' || member.role === 'ADMIN').length,
      deactivated: members.length - active.length,
    };
  }, [members]);

  const reload = () => setRefreshes((count) => count + 1);
  const changed = () => setChanges((count) => count + 1);
  const cancelPending = useCallback(() => setPending(null), []);

  const showOutcome = (tone: 'success' | 'warning' | 'info', message: string) => {
    if (tone === 'success') toast.success(message, undefined, 6000);
    else if (tone === 'warning') toast.warning(message, 'Check the email', 10000);
    else toast.info(message, undefined, 6000);
  };

  const onAdded = (result: InviteResult, email: string) => {
    setAdding(false);
    const { tone, message } = describeInviteResult(result, email);
    showOutcome(tone, message);
    changed();
  };

  const confirmPending = async () => {
    if (!pending) return;
    const { member } = pending;
    setBusy(true);
    try {
      switch (pending.kind) {
        case 'role': {
          await membersApi.changeRole(member.membership_id, pending.role);
          const label = ROLE_META[pending.role].label;
          toast.success(`${member.name} is now ${label === 'Admin' ? 'an' : 'a'} ${label}.`);
          break;
        }
        case 'deactivate':
          await membersApi.setActive(member.membership_id, false);
          toast.success(`${member.name} was deactivated and can no longer open ${workspaceName}.`);
          break;
        case 'reactivate':
          await membersApi.setActive(member.membership_id, true);
          toast.success(`${member.name} can use ${workspaceName} again.`);
          break;
        case 'remove':
          await membersApi.remove(member.membership_id);
          toast.success(`${member.name} was removed from ${workspaceName}.`);
          break;
        case 'resend': {
          const result = await membersApi.resendInvite(member.membership_id);
          const { tone, message } = describeInviteResult(result, member.email ?? member.name, true);
          showOutcome(tone, message);
          break;
        }
      }
      setPending(null);
      changed();
    } catch (error) {
      const status = memberErrorStatus(error);
      toast.error(describeMemberError(error), 'Couldn’t update member');
      setPending(null);
      if (status === 404 || status === 409 || status === 403) {
        changed(); // the list is out of date; show what's there now
      }
    } finally {
      setBusy(false);
    }
  };

  if (!isAdmin) {
    return (
      <div className="h-full flex flex-col gap-6 pb-4">
        <section className="space-y-2">
          <h2 className="font-serif text-3xl font-bold text-primary">User Management</h2>
        </section>
        <div className="flex flex-col items-center justify-center text-center gap-3 py-16 bg-card border border-border/70 rounded-2xl">
          <div className="w-12 h-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <p className="font-serif text-xl font-bold text-foreground">Only owners and admins can manage users</p>
          <p className="text-xs text-muted-foreground max-w-md">
            Ask the owner or an admin of {workspaceName} if you need someone added or your access changed.
          </p>
        </div>
      </div>
    );
  }

  const renderDialog = () => {
    if (!pending) return null;
    const { member } = pending;
    const name = <span className="font-semibold text-foreground">{member.name}</span>;
    switch (pending.kind) {
      case 'role':
        return (
          <ConfirmDialog
            title="Change role?"
            message={
              <>
                {name} will change from {ROLE_META[member.role].label} to {ROLE_META[pending.role].label}.{' '}
                {ROLE_META[pending.role].description}
              </>
            }
            confirmLabel="Change role"
            busyLabel="Saving…"
            busy={busy}
            onConfirm={() => void confirmPending()}
            onCancel={cancelPending}
          />
        );
      case 'deactivate':
        return (
          <ConfirmDialog
            destructive
            title="Deactivate this member?"
            message={
              <>
                {name} will lose access to {workspaceName} right away. Their deals, notes and documents stay, and you can
                reactivate them later.
              </>
            }
            confirmLabel="Deactivate"
            busyLabel="Deactivating…"
            busy={busy}
            onConfirm={() => void confirmPending()}
            onCancel={cancelPending}
          />
        );
      case 'reactivate':
        return (
          <ConfirmDialog
            title="Reactivate this member?"
            message={
              <>
                {name} will get access to {workspaceName} again as {ROLE_META[member.role].label}.
              </>
            }
            confirmLabel="Reactivate"
            busyLabel="Reactivating…"
            busy={busy}
            onConfirm={() => void confirmPending()}
            onCancel={cancelPending}
          />
        );
      case 'remove':
        return (
          <ConfirmDialog
            destructive
            title="Remove from workspace?"
            message={
              <>
                {name} will lose access to {workspaceName} and disappear from this list. Their deals, notes and documents
                stay. To bring them back, add them again.
              </>
            }
            confirmLabel="Remove"
            busyLabel="Removing…"
            busy={busy}
            onConfirm={() => void confirmPending()}
            onCancel={cancelPending}
          />
        );
      case 'resend':
        return (
          <ConfirmDialog
            title="Send new sign-in details?"
            message={
              <>
                We’ll email a new temporary password to {name}
                {member.email ? ` at ${member.email}` : ''}. The password sent before stops working.
              </>
            }
            confirmLabel="Send"
            busyLabel="Sending…"
            busy={busy}
            onConfirm={() => void confirmPending()}
            onCancel={cancelPending}
          />
        );
    }
  };

  return (
    <div className="h-full flex flex-col gap-6 pb-4">
      <section className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div className="space-y-2">
          <h2 className="font-serif text-3xl font-bold text-primary">User Management</h2>
          <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
            Add people to {workspaceName}, choose what they can do, and remove access when they leave. New people get a
            verified account and their sign-in details by email.
          </p>
        </div>
        {list && (
          <Button className="px-4 py-2.5 w-auto text-xs" onClick={() => setAdding(true)} icon={<UserPlus className="w-4 h-4" />}>
            Add user
          </Button>
        )}
      </section>

      <div className="flex flex-wrap items-center gap-2 border-b border-border/60 pb-3" role="tablist">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-colors cursor-pointer ${
              tab === id ? 'bg-primary text-primary-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {tab === 'activity' && <MemberActivity workspaceId={workspaceId} changes={changes} />}
      {tab === 'roles' && <RolesGuide />}

      {tab === 'members' && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Stat label="Members" value={stats.active} />
            <Stat label="Pending invites" value={stats.pending} />
            <Stat label="Owner & admins" value={stats.admins} />
            <Stat label="Deactivated" value={stats.deactivated} />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[14rem] max-w-md">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/70" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search by name or email…"
                aria-label="Search members"
                className="w-full pl-9 pr-3 py-2 rounded-xl border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/10 focus:border-primary"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
              aria-label="Filter by status"
              className="py-2 px-3 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/10 focus:border-primary cursor-pointer"
            >
              <option value="all">All statuses</option>
              {(Object.keys(STATUS_META) as StatusKey[]).map((key) => (
                <option key={key} value={key}>
                  {STATUS_META[key].label}
                </option>
              ))}
            </select>
            <select
              value={roleFilter}
              onChange={(event) => setRoleFilter(event.target.value as 'all' | MemberRole)}
              aria-label="Filter by role"
              className="py-2 px-3 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/10 focus:border-primary cursor-pointer"
            >
              <option value="all">All roles</option>
              {(Object.keys(ROLE_META) as MemberRole[]).map((key) => (
                <option key={key} value={key}>
                  {ROLE_META[key].label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={reload}
              disabled={loading}
              title="Refresh"
              aria-label="Refresh members"
              className="p-2 rounded-xl border border-border text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors cursor-pointer disabled:cursor-default"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {list && !list.account_details_available && (
            <div className="rounded-xl border border-amber-500/35 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-800 dark:text-amber-200 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              Emails, sign-in times and invitation status couldn’t be loaded right now. The rest of the list is up to date.
            </div>
          )}

          {!current ? (
            <div className="flex-1 flex items-center justify-center py-16 text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin" />
            </div>
          ) : current.error ? (
            <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-5 py-4 text-sm text-red-700 dark:text-red-300 flex items-center justify-between gap-3">
              <span>{current.error}</span>
              <Button variant="outline" className="px-3 py-1.5 text-xs" onClick={reload}>
                Try again
              </Button>
            </div>
          ) : (
            <>
              <div className="rounded-2xl border border-border/80 bg-card overflow-hidden shadow-xs">
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-muted/40 text-muted-foreground uppercase text-[10px] border-b border-border/70">
                      <tr>
                        <th className="px-4 py-3">User</th>
                        <th className="px-4 py-3">Role</th>
                        <th className="px-4 py-3">Status</th>
                        <th className="px-4 py-3">Last sign-in</th>
                        <th className="px-4 py-3">Added</th>
                        <th className="px-4 py-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {visible.map((member) => {
                        const status = memberStatus(member);
                        const roleOptions: MemberRole[] = member.assignable_roles.includes(member.role as AssignableRole)
                          ? member.assignable_roles
                          : [member.role, ...member.assignable_roles];
                        return (
                          <tr key={member.membership_id} className={`hover:bg-muted/20 transition-colors ${member.active ? '' : 'opacity-70'}`}>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-3 min-w-[14rem]">
                                <div className="w-8 h-8 rounded-full overflow-hidden bg-primary/15 border border-primary/15 flex items-center justify-center text-[11px] font-bold text-primary shrink-0">
                                  {member.avatar_url ? (
                                    <img src={member.avatar_url} alt="" className="w-full h-full object-cover" />
                                  ) : (
                                    initials(member.name)
                                  )}
                                </div>
                                <div className="min-w-0">
                                  <p className="font-semibold text-foreground truncate flex items-center gap-1.5">
                                    {member.name}
                                    {member.is_you && <span className="text-[10px] font-normal text-muted-foreground">(you)</span>}
                                  </p>
                                  <p className="text-[11px] text-muted-foreground truncate">
                                    {member.email ?? 'Email unavailable'}
                                    {member.job_title ? ` · ${member.job_title}` : ''}
                                  </p>
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              {member.can_change_role && member.active && roleOptions.length > 1 ? (
                                <select
                                  value={member.role}
                                  onChange={(event) =>
                                    setPending({ kind: 'role', member, role: event.target.value as AssignableRole })
                                  }
                                  aria-label={`Role for ${member.name}`}
                                  className="py-1 px-2 rounded-lg border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/10 focus:border-primary cursor-pointer"
                                >
                                  {roleOptions.map((option) => (
                                    <option key={option} value={option} disabled={option === 'OWNER'}>
                                      {ROLE_META[option].label}
                                    </option>
                                  ))}
                                </select>
                              ) : (
                                <Badge className={ROLE_META[member.role]?.badge ?? ''}>{ROLE_META[member.role]?.label ?? member.role}</Badge>
                              )}
                            </td>
                            <td className="px-4 py-3">
                              <Badge className={STATUS_META[status].badge}>{STATUS_META[status].label}</Badge>
                              {status === 'pending' && member.invite_expires_at && (
                                <p className="text-[10px] text-muted-foreground mt-1" title={formatDateTime(member.invite_expires_at)}>
                                  Expires {formatDate(member.invite_expires_at)}
                                </p>
                              )}
                            </td>
                            <td className="px-4 py-3 text-muted-foreground whitespace-nowrap" title={formatDateTime(member.last_sign_in_at)}>
                              {member.last_sign_in_at ? timeAgo(member.last_sign_in_at) : member.email ? 'Never' : '—'}
                            </td>
                            <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                              <span title={formatDateTime(member.joined_at)}>{formatDate(member.joined_at)}</span>
                              {member.invited_by_name && <p className="text-[10px]">by {member.invited_by_name}</p>}
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center justify-end gap-0.5">
                                {member.can_resend_invite && (
                                  <IconAction
                                    icon={MailPlus}
                                    label="Resend invite"
                                    disabled={busy}
                                    onClick={() => setPending({ kind: 'resend', member })}
                                  />
                                )}
                                {member.can_deactivate &&
                                  (member.active ? (
                                    <IconAction
                                      icon={UserX}
                                      label="Deactivate"
                                      disabled={busy}
                                      onClick={() => setPending({ kind: 'deactivate', member })}
                                    />
                                  ) : (
                                    <IconAction
                                      icon={UserCheck}
                                      label="Reactivate"
                                      disabled={busy}
                                      onClick={() => setPending({ kind: 'reactivate', member })}
                                    />
                                  ))}
                                {member.can_remove && (
                                  <IconAction
                                    icon={Trash2}
                                    label="Remove from workspace"
                                    danger
                                    disabled={busy}
                                    onClick={() => setPending({ kind: 'remove', member })}
                                  />
                                )}
                                {!member.can_resend_invite && !member.can_deactivate && !member.can_remove && (
                                  <span className="text-[11px] text-muted-foreground px-1.5">
                                    {member.is_owner ? 'Owner' : member.is_you ? 'You' : '—'}
                                  </span>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {visible.length === 0 && (
                  <p className="px-4 py-8 text-center text-xs text-muted-foreground">No members match these filters.</p>
                )}
              </div>

              {members.length <= 1 && (
                <div className="flex flex-col items-center justify-center text-center gap-3 py-10 bg-card border border-border/70 rounded-2xl">
                  <div className="w-12 h-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center">
                    <Users className="w-6 h-6" />
                  </div>
                  <p className="font-serif text-xl font-bold text-foreground">It’s just you so far</p>
                  <p className="text-xs text-muted-foreground max-w-md">
                    Add your team so they can work with the same deals, products and knowledge vault. Each person gets their
                    own sign-in.
                  </p>
                  <Button className="px-4 py-2 w-auto text-xs mt-1" onClick={() => setAdding(true)} icon={<UserPlus className="w-4 h-4" />}>
                    Add user
                  </Button>
                </div>
              )}
            </>
          )}
        </>
      )}

      {adding && list && (
        <AddUserModal
          workspaceName={list.workspace_name || workspaceName}
          assignableRoles={list.assignable_roles}
          onClose={() => setAdding(false)}
          onAdded={onAdded}
        />
      )}
      {renderDialog()}
    </div>
  );
};

export default UserManagement;
