import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Eye, Inbox, LifeBuoy, MessageSquareReply, Timer } from 'lucide-react';
import { adminApi } from '../../api/adminApi';
import type { SupportTicketFilters, SupportTicketStatus } from '../../api/adminApi';
import {
  AdminPage,
  Badge,
  EmptyBlock,
  ErrorBlock,
  IconAction,
  LoadingBlock,
  Pagination,
  RefreshButton,
  SearchInput,
  StatCard,
  Switch,
  TableHead,
  TableShell,
  Th,
  selectClass,
} from './components/AdminUi';
import { formatDate, formatDateTime, formatNumber, timeAgo } from './adminFormat';
import { useAdminQuery } from './useAdminQuery';
import { SupportTicketDrawer } from './SupportTicketDrawer';
import { TICKET_STATUSES, TICKET_STATUS_META } from './supportMeta';

const PAGE_SIZE = 25;

/** The support queue: every ticket workspace members sent to the RoleSync team, across all workspaces. */
export const AdminSupportTickets: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const openTicket = searchParams.get('open');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<SupportTicketStatus | ''>('');
  const [awaiting, setAwaiting] = useState(false);
  const [page, setPage] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search.trim());
      setPage(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const filters: SupportTicketFilters = { q: query, status, awaiting, page, size: PAGE_SIZE };
  const list = useAdminQuery(() => adminApi.supportTickets(filters), JSON.stringify(filters));
  const stats = useAdminQuery(() => adminApi.supportTicketStats(), 'support-stats');

  const refresh = () => {
    list.reload();
    stats.reload();
  };

  const setOpen = (ticketId: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (ticketId) next.set('open', ticketId);
    else next.delete('open');
    setSearchParams(next, { replace: true });
  };

  const tickets = list.data?.items ?? [];
  const statsLoading = !stats.data && !stats.error;

  return (
    <AdminPage
      title="Support Tickets"
      icon={LifeBuoy}
      description="What workspace members sent to the RoleSync team from their Support Desk. Reply here and they see it on their ticket; move a ticket along as you work on it."
      actions={<RefreshButton onClick={refresh} loading={list.loading} label="Refresh tickets" />}
    >
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Awaiting reply"
          icon={MessageSquareReply}
          tone="warning"
          loading={statsLoading}
          value={formatNumber(stats.data?.awaiting_support)}
          hint="Open or in progress, reporter wrote last"
        />
        <StatCard label="Open" tone="warning" loading={statsLoading} value={formatNumber(stats.data?.open)} hint={stats.data ? `${formatNumber(stats.data.opened_last_7_days)} opened in the last 7 days` : undefined} />
        <StatCard label="In progress" tone="info" loading={statsLoading} value={formatNumber(stats.data?.in_progress)} />
        <StatCard label="Resolved" icon={Timer} tone="success" loading={statsLoading} value={formatNumber(stats.data?.resolved)} hint={stats.data ? `${formatNumber(stats.data.closed)} closed · ${formatNumber(stats.data.total)} in all` : undefined} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <SearchInput value={search} onChange={setSearch} placeholder="Search subject, workspace or reporter…" />
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as SupportTicketStatus | '');
            setPage(0);
          }}
          aria-label="Filter by status"
          className={selectClass}
        >
          <option value="">All statuses</option>
          {TICKET_STATUSES.map((value) => (
            <option key={value} value={value}>
              {TICKET_STATUS_META[value].label}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer select-none">
          <Switch
            checked={awaiting}
            onChange={(checked) => {
              setAwaiting(checked);
              setPage(0);
            }}
            label="Only tickets awaiting a reply"
            size="sm"
          />
          Awaiting reply only
        </label>
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
            <Th>Ticket</Th>
            <Th>Reporter</Th>
            <Th>Status</Th>
            <Th>Replies</Th>
            <Th>Last activity</Th>
            <Th>Opened</Th>
            <Th className="text-right">Actions</Th>
          </TableHead>
          <tbody className={`divide-y divide-border/60 ${list.loading ? 'opacity-60' : ''}`}>
            {tickets.map((ticket) => {
              const meta = TICKET_STATUS_META[ticket.status];
              const needsReply = !ticket.last_message_from_support && (ticket.status === 'OPEN' || ticket.status === 'IN_PROGRESS');
              return (
                <tr key={ticket.ticket_id} className={`hover:bg-muted/20 transition-colors ${needsReply ? 'bg-amber-500/[0.03]' : ''}`}>
                  <td className="px-4 py-3">
                    <button type="button" onClick={() => setOpen(ticket.ticket_id)} className="min-w-[16rem] max-w-[26rem] text-left cursor-pointer group">
                      <span className="block font-semibold text-foreground group-hover:underline truncate">{ticket.subject}</span>
                      <span className="block text-[11px] text-muted-foreground truncate">
                        {ticket.workspace.name}
                        {!ticket.workspace.is_active && ' · suspended workspace'}
                      </span>
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <span className="block min-w-0">
                      <span className="block text-foreground truncate">{ticket.reporter.name}</span>
                      <span className="block text-[11px] text-muted-foreground truncate">{ticket.reporter.email ?? 'Email unavailable'}</span>
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={meta.tone} title={meta.description}>
                      {meta.label}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 tabular-nums">
                    <span className="text-foreground">{formatNumber(ticket.message_count)}</span>
                    {needsReply && <span className="block text-[11px] text-amber-700 dark:text-amber-300">Awaiting reply</span>}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap" title={formatDateTime(ticket.updated_at)}>
                    {timeAgo(ticket.updated_at)}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap" title={formatDateTime(ticket.created_at)}>
                    {formatDate(ticket.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-0.5">
                      <IconAction icon={Eye} label="Open ticket" onClick={() => setOpen(ticket.ticket_id)} />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
          {tickets.length === 0 && (
            <tbody>
              <tr>
                <td colSpan={7}>
                  <EmptyBlock
                    icon={Inbox}
                    title={query || status || awaiting ? 'No tickets match' : 'No support tickets yet'}
                    description={query || status || awaiting ? 'Try a different search or clear the filters.' : 'Tickets people send from their Support Desk show up here.'}
                  />
                </td>
              </tr>
            </tbody>
          )}
        </TableShell>
      )}

      {openTicket && <SupportTicketDrawer ticketId={openTicket} onClose={() => setOpen(null)} onChanged={refresh} />}
    </AdminPage>
  );
};

export default AdminSupportTickets;
