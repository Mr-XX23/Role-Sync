import React, { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Ban, CircleCheck, Coins, Eye, MinusCircle, PlusCircle, TrendingDown, Wallet } from 'lucide-react';
import { billingApi } from '../../api/billingApi';
import type { AccountFilters, CreditAccount, CreditStatus } from '../../api/billingApi';
import { useBillingQuery } from '../../hooks/useBillingQuery';
import { formatCreditAmount, formatCredits } from '../../utils/billingFormat';
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
import { formatDateTime, formatNumber, initials, shortId, timeAgo } from './adminFormat';
import { useDirectory } from './useDirectory';
import { ACCOUNT_STATUS_META } from './billing/billingMeta';
import { CreditAccountDrawer } from './billing/CreditAccountDrawer';
import { CreditActionDialog } from './billing/CreditActionDialog';
import type { CreditActionKind } from './billing/CreditActionDialog';

const PAGE_SIZE = 20;

/** Every workspace's credit account: find one, see its ledger, and grant, deduct, suspend or reactivate. */
export const AdminCredits: React.FC = () => {
  const location = useLocation();
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<CreditStatus | ''>('');
  const [page, setPage] = useState(0);
  // The Billing overview can open an account here directly.
  const [openId, setOpenId] = useState<string | null>(() => {
    const open = (location.state as { open?: unknown } | null)?.open;
    return typeof open === 'string' ? open : null;
  });
  const [action, setAction] = useState<{ kind: CreditActionKind; account: CreditAccount } | null>(null);
  const directory = useDirectory();

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search.trim());
      setPage(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const filters: AccountFilters = { query, status, page, size: PAGE_SIZE };
  const list = useBillingQuery(() => billingApi.admin.accounts(filters), JSON.stringify(filters), 'admin');
  const overview = useBillingQuery(() => billingApi.admin.overview(30), 'overview:30', 'admin');
  const detail = useBillingQuery(openId ? () => billingApi.admin.account(openId) : null, `account:${openId ?? ''}`, 'admin');

  const nameOf = (workspaceId: string) => directory.workspace(workspaceId)?.name ?? null;
  const refresh = () => {
    list.reload();
    overview.reload();
    if (openId) detail.reload();
  };

  const accounts = list.data?.items ?? [];
  const statsLoading = !overview.data && !overview.error;
  const filtered = Boolean(query || status);

  return (
    <AdminPage
      title="Credits"
      icon={Coins}
      description="Every workspace’s credit account. Grant or deduct credits, or stop a workspace from spending them; each change needs a reason and is kept on the account’s ledger with your name."
      actions={<RefreshButton onClick={refresh} loading={list.loading} label="Refresh credit accounts" />}
    >
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Accounts" icon={Wallet} loading={statsLoading} value={formatNumber(overview.data?.accounts)} />
        <StatCard label="Suspended" icon={Ban} tone="danger" loading={statsLoading} value={formatNumber(overview.data?.suspendedAccounts)} />
        <StatCard
          label="Below zero"
          icon={TrendingDown}
          tone="warning"
          loading={statsLoading}
          value={formatNumber(overview.data?.negativeBalanceAccounts)}
          hint="Repaid by the next top-up"
        />
        <StatCard
          label="Unspent credits"
          icon={Coins}
          tone="info"
          loading={statsLoading}
          value={formatCredits(overview.data?.outstandingCredits)}
          hint="In all balances now"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <SearchInput value={search} onChange={setSearch} placeholder="Search by workspace id…" />
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as CreditStatus | '');
            setPage(0);
          }}
          aria-label="Filter by status"
          className={selectClass}
        >
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="SUSPENDED">Suspended</option>
        </select>
      </div>

      {list.error && !list.data ? (
        <ErrorBlock message={list.error} onRetry={list.errorStatus === 403 ? undefined : list.reload} />
      ) : !list.data ? (
        <LoadingBlock />
      ) : (
        <TableShell
          footer={
            <Pagination
              page={list.data.page}
              totalPages={Math.ceil(list.data.total / Math.max(1, list.data.size))}
              total={list.data.total}
              size={list.data.size}
              onPage={setPage}
              disabled={list.loading}
            />
          }
        >
          <TableHead>
            <Th>Workspace</Th>
            <Th>Balance</Th>
            <Th>Status</Th>
            <Th>Used of credited</Th>
            <Th>Last activity</Th>
            <Th className="text-right">Actions</Th>
          </TableHead>
          <tbody className={`divide-y divide-border/60 ${list.loading ? 'opacity-60' : ''}`}>
            {accounts.map((account) => {
              const name = nameOf(account.workspaceId);
              const meta = ACCOUNT_STATUS_META[account.status];
              const suspended = account.status === 'SUSPENDED';
              return (
                <tr key={account.workspaceId} className={`hover:bg-muted/20 transition-colors ${suspended ? 'bg-red-500/[0.03]' : ''}`}>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => setOpenId(account.workspaceId)}
                      className="flex items-center gap-3 min-w-[13rem] text-left cursor-pointer group"
                    >
                      <Avatar text={name ? initials(name) : '#'} tone={suspended ? 'danger' : 'info'} />
                      <span className="min-w-0">
                        <span className="block font-semibold text-foreground group-hover:underline truncate max-w-[16rem]">
                          {name ?? 'Workspace'}
                        </span>
                        <span className="block font-mono text-[11px] text-muted-foreground" title={account.workspaceId}>
                          {shortId(account.workspaceId)}
                        </span>
                      </span>
                    </button>
                  </td>
                  <td
                    className={`px-4 py-3 tabular-nums font-semibold ${
                      account.balance <= 0 ? 'text-red-600 dark:text-red-400' : 'text-foreground'
                    }`}
                  >
                    {formatCreditAmount(account.balance)}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={meta.tone} title={account.suspendedReason ?? undefined}>
                      {meta.label}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 tabular-nums text-muted-foreground whitespace-nowrap">
                    <span className="text-foreground">{formatCreditAmount(account.lifetimeUsed)}</span> of{' '}
                    {formatCredits(account.lifetimeCredited)}
                    {account.lifetimePurchased > 0 && (
                      <span className="block text-[11px]">{formatCredits(account.lifetimePurchased)} purchased</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap" title={formatDateTime(account.lastActivityAt)}>
                    {account.lastActivityAt ? timeAgo(account.lastActivityAt) : 'Never'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-0.5">
                      <IconAction icon={Eye} label="View account" onClick={() => setOpenId(account.workspaceId)} />
                      <IconAction icon={PlusCircle} label="Grant credits" tone="success" disabled={action !== null} onClick={() => setAction({ kind: 'grant', account })} />
                      <IconAction icon={MinusCircle} label="Deduct credits" disabled={action !== null} onClick={() => setAction({ kind: 'deduct', account })} />
                      {suspended ? (
                        <IconAction icon={CircleCheck} label="Reactivate credits" tone="success" disabled={action !== null} onClick={() => setAction({ kind: 'reactivate', account })} />
                      ) : (
                        <IconAction icon={Ban} label="Suspend credits" tone="danger" disabled={action !== null} onClick={() => setAction({ kind: 'suspend', account })} />
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
          {accounts.length === 0 && (
            <tbody>
              <tr>
                <td colSpan={6}>
                  <EmptyBlock
                    icon={Wallet}
                    title={filtered ? 'No credit accounts match' : 'No credit accounts yet'}
                    description={
                      filtered
                        ? 'Try a different workspace id or clear the status filter.'
                        : 'An account is created the first time a workspace uses billing. Welcome credits go to a workspace its owner opens, once per person.'
                    }
                  />
                </td>
              </tr>
            </tbody>
          )}
        </TableShell>
      )}

      {openId && (
        <CreditAccountDrawer
          workspaceId={openId}
          name={nameOf(openId)}
          detail={detail}
          directory={directory}
          busy={action !== null}
          onAction={(kind, account) => setAction({ kind, account })}
          onClose={() => setOpenId(null)}
        />
      )}
      {action && (
        <CreditActionDialog
          kind={action.kind}
          account={action.account}
          workspaceName={nameOf(action.account.workspaceId) ?? `Workspace ${shortId(action.account.workspaceId)}`}
          onClose={() => setAction(null)}
          onDone={() => {
            setAction(null);
            refresh();
          }}
        />
      )}
    </AdminPage>
  );
};

export default AdminCredits;
