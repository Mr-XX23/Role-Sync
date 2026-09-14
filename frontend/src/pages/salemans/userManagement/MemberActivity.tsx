import React, { useEffect, useState } from 'react';
import { History, Loader2, MailPlus, RefreshCw, Shield, Trash2, UserCheck, UserPlus, UserX } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Button } from '../../../components/common/Button';
import { describeMemberError, membersApi } from '../../../api/membersApi';
import type { MemberAction, MemberActivity as ActivityItem, MemberRole } from '../../../api/membersApi';
import { ROLE_META, formatDateTime, timeAgo } from './memberFormat';

const ACTION_ICON: Record<MemberAction, LucideIcon> = {
  MEMBER_ADDED: UserPlus,
  ROLE_CHANGED: Shield,
  MEMBER_DEACTIVATED: UserX,
  MEMBER_REACTIVATED: UserCheck,
  MEMBER_REMOVED: Trash2,
  INVITE_RESENT: MailPlus,
};

const roleLabel = (role: MemberRole | null) => (role ? ROLE_META[role]?.label ?? role : 'a member');

function describe(item: ActivityItem): React.ReactNode {
  const actor = <span className="font-semibold text-foreground">{item.actor_name || 'Someone'}</span>;
  const target = <span className="font-semibold text-foreground">{item.target_name || item.target_email || 'a member'}</span>;
  switch (item.action) {
    case 'MEMBER_ADDED':
      return item.from_role ? (
        <>
          {actor} added {target} back as {roleLabel(item.to_role)}
        </>
      ) : (
        <>
          {actor} added {target} as {roleLabel(item.to_role)}
        </>
      );
    case 'ROLE_CHANGED':
      return (
        <>
          {actor} changed {target}’s role from {roleLabel(item.from_role)} to {roleLabel(item.to_role)}
        </>
      );
    case 'MEMBER_DEACTIVATED':
      return (
        <>
          {actor} deactivated {target}
        </>
      );
    case 'MEMBER_REACTIVATED':
      return (
        <>
          {actor} reactivated {target}
        </>
      );
    case 'MEMBER_REMOVED':
      return (
        <>
          {actor} removed {target} from the workspace
        </>
      );
    case 'INVITE_RESENT':
      return (
        <>
          {actor} sent new sign-in details to {target}
        </>
      );
    default:
      return (
        <>
          {actor} changed {target}’s membership
        </>
      );
  }
}

interface Loaded {
  key: string;
  items: ActivityItem[];
  error: string | null;
}

export const MemberActivity: React.FC<{ workspaceId: string | undefined; changes: number }> = ({ workspaceId, changes }) => {
  const [refreshes, setRefreshes] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const requestKey = `${workspaceId}:${changes}:${refreshes}`;

  useEffect(() => {
    let active = true;
    membersApi
      .activity(100)
      .then((items) => {
        if (active) setLoaded({ key: requestKey, items, error: null });
      })
      .catch((error) => {
        if (active) setLoaded({ key: requestKey, items: [], error: describeMemberError(error) });
      });
    return () => {
      active = false;
    };
  }, [requestKey]);

  const loading = loaded?.key !== requestKey;

  return (
    <section className="bg-card border border-border/70 rounded-2xl shadow-2xs">
      <header className="flex items-center justify-between gap-3 px-5 py-3.5 border-b border-border/60">
        <div>
          <h3 className="text-sm font-bold text-foreground">Activity</h3>
          <p className="text-xs text-muted-foreground">Who added, changed or removed members, newest first.</p>
        </div>
        <button
          type="button"
          onClick={() => setRefreshes((count) => count + 1)}
          disabled={loading}
          title="Refresh"
          aria-label="Refresh activity"
          className="p-2 rounded-xl border border-border text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors cursor-pointer disabled:cursor-default"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </header>

      {!loaded ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      ) : loaded.error ? (
        <div className="m-5 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300 flex items-center justify-between gap-3">
          <span>{loaded.error}</span>
          <Button variant="outline" className="px-3 py-1.5 text-xs" onClick={() => setRefreshes((count) => count + 1)}>
            Try again
          </Button>
        </div>
      ) : loaded.items.length === 0 ? (
        <div className="flex flex-col items-center justify-center text-center gap-2 py-12 px-6">
          <History className="w-6 h-6 text-muted-foreground" />
          <p className="text-sm font-semibold text-foreground">No changes yet</p>
          <p className="text-xs text-muted-foreground max-w-sm">
            Adding people, changing roles, deactivating and removing members will show up here.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-border/60">
          {loaded.items.map((item) => {
            const Icon = ACTION_ICON[item.action] ?? History;
            const destructive = item.action === 'MEMBER_REMOVED' || item.action === 'MEMBER_DEACTIVATED';
            return (
              <li key={item.event_id} className="flex items-start gap-3 px-5 py-3">
                <span
                  className={`mt-0.5 w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
                    destructive ? 'bg-destructive/10 text-destructive' : 'bg-muted text-muted-foreground'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-muted-foreground leading-snug">{describe(item)}</p>
                  {item.target_email && item.target_name && (
                    <p className="text-[11px] text-muted-foreground/80 truncate">{item.target_email}</p>
                  )}
                </div>
                <time
                  dateTime={item.created_at}
                  title={formatDateTime(item.created_at)}
                  className="text-[11px] text-muted-foreground whitespace-nowrap shrink-0"
                >
                  {timeAgo(item.created_at)}
                </time>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
};
