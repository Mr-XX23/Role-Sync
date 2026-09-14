import React, { useState } from 'react';
import { CircleDollarSign, Coins, CreditCard, ReceiptText } from 'lucide-react';
import { ORDER_STATUSES, billingApi } from '../../api/billingApi';
import type { OrderStatus, PaymentFilters } from '../../api/billingApi';
import { useBillingQuery } from '../../hooks/useBillingQuery';
import { formatCredits, formatMoney } from '../../utils/billingFormat';
import {
  AdminPage,
  Badge,
  EmptyBlock,
  ErrorBlock,
  LoadingBlock,
  Pagination,
  RefreshButton,
  StatCard,
  TableHead,
  TableShell,
  Th,
  selectClass,
} from './components/AdminUi';
import { formatDateTime, formatNumber, humanize, shortId, timeAgo } from './adminFormat';
import { useDirectory } from './useDirectory';
import { ORDER_STATUS_META, orderStatusMeta, revenueText } from './billing/billingMeta';

const PAGE_SIZE = 20;

/** Every credit purchase across workspaces, newest first. */
export const AdminPayments: React.FC = () => {
  const [status, setStatus] = useState<OrderStatus | ''>('');
  const [page, setPage] = useState(0);
  const directory = useDirectory();

  const filters: PaymentFilters = { status, page, size: PAGE_SIZE };
  const list = useBillingQuery(() => billingApi.admin.payments(filters), JSON.stringify(filters), 'admin');
  const overview = useBillingQuery(() => billingApi.admin.overview(30), 'overview:30', 'admin');

  const refresh = () => {
    list.reload();
    overview.reload();
  };

  const orders = list.data?.items ?? [];
  // billing-service doesn't say which workspace bought an order yet; the column appears once it does.
  const showWorkspace = orders.some((order) => Boolean(order.workspaceId));
  const statsLoading = !overview.data && !overview.error;
  const columns = showWorkspace ? 9 : 8;

  return (
    <AdminPage
      title="Payments"
      icon={CreditCard}
      description="Credit pack purchases from every workspace. An order only succeeds once the payment provider confirms it; pending ones settle by themselves or expire."
      actions={<RefreshButton onClick={refresh} loading={list.loading} label="Refresh payments" />}
    >
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <StatCard
          label="Revenue"
          icon={CircleDollarSign}
          tone="success"
          loading={statsLoading}
          value={revenueText(overview.data)}
          hint="Last 30 days"
        />
        <StatCard
          label="Successful payments"
          icon={ReceiptText}
          loading={statsLoading}
          value={formatNumber(overview.data?.successfulPayments)}
          hint="Last 30 days"
        />
        <StatCard
          label="Credits sold"
          icon={Coins}
          tone="violet"
          loading={statsLoading}
          value={formatCredits(overview.data?.creditsSold)}
          hint="Last 30 days"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as OrderStatus | '');
            setPage(0);
          }}
          aria-label="Filter by status"
          className={selectClass}
        >
          <option value="">All statuses</option>
          {ORDER_STATUSES.map((value) => (
            <option key={value} value={value}>
              {ORDER_STATUS_META[value].label}
            </option>
          ))}
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
            <Th>Order</Th>
            {showWorkspace && <Th>Workspace</Th>}
            <Th>Pack</Th>
            <Th>Credits</Th>
            <Th>Amount</Th>
            <Th>Provider</Th>
            <Th>Status</Th>
            <Th>Started</Th>
            <Th>Paid</Th>
          </TableHead>
          <tbody className={`divide-y divide-border/60 ${list.loading ? 'opacity-60' : ''}`}>
            {orders.map((order) => {
              const meta = orderStatusMeta(order.status);
              return (
                <tr key={order.orderId} className="hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-3 font-mono text-[11px] text-foreground whitespace-nowrap" title={order.orderId}>
                    {shortId(order.orderId)}
                  </td>
                  {showWorkspace && (
                    <td className="px-4 py-3">
                      {order.workspaceId ? (
                        <span className="block min-w-0">
                          <span className="block text-foreground truncate max-w-[14rem]">
                            {directory.workspace(order.workspaceId)?.name ?? 'Workspace'}
                          </span>
                          <span className="block font-mono text-[11px] text-muted-foreground">{shortId(order.workspaceId)}</span>
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                  )}
                  <td className="px-4 py-3 text-foreground whitespace-nowrap">{order.packageCode}</td>
                  <td className="px-4 py-3 tabular-nums text-foreground">{formatCredits(order.credits)}</td>
                  <td className="px-4 py-3 tabular-nums font-semibold text-foreground whitespace-nowrap">
                    {formatMoney(order.amountMinor, order.currency)}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{humanize(order.provider)}</td>
                  <td className="px-4 py-3">
                    <Badge tone={meta.tone} title={meta.description}>
                      {meta.label}
                    </Badge>
                    {order.failureReason && (
                      <span className="block text-[11px] text-muted-foreground mt-1 max-w-[16rem] truncate" title={order.failureReason}>
                        {order.failureReason}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap" title={formatDateTime(order.createdAt)}>
                    {timeAgo(order.createdAt)}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{order.paidAt ? formatDateTime(order.paidAt) : '—'}</td>
                </tr>
              );
            })}
          </tbody>
          {orders.length === 0 && (
            <tbody>
              <tr>
                <td colSpan={columns}>
                  <EmptyBlock
                    icon={CreditCard}
                    title={status ? 'No payments with this status' : 'No payments yet'}
                    description={status ? 'Pick another status or show all.' : 'Credit pack purchases appear here as soon as someone starts a checkout.'}
                  />
                </td>
              </tr>
            </tbody>
          )}
        </TableShell>
      )}
    </AdminPage>
  );
};

export default AdminPayments;
