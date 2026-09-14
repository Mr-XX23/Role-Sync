import React from 'react';
import { Ban, CircleCheck, History, MinusCircle, PieChart, PlusCircle } from 'lucide-react';
import type { AdminAccountDetail, CreditAccount } from '../../../api/billingApi';
import { CategoryUsageBars } from '../../../components/billing/CategoryUsageBars';
import { categoryMeta } from '../../../components/billing/categoryMeta';
import { Button } from '../../../components/common/Button';
import type { BillingQuery } from '../../../hooks/useBillingQuery';
import { formatCreditAmount, formatCredits } from '../../../utils/billingFormat';
import { formatDateTime, shortId, timeAgo } from '../adminFormat';
import { Badge, Drawer, ErrorBlock, KeyValue, LoadingBlock, Notice } from '../components/AdminUi';
import type { Directory } from '../useDirectory';
import { ACCOUNT_STATUS_META, transactionMeta } from './billingMeta';
import type { CreditActionKind } from './CreditActionDialog';

const TransactionList: React.FC<{ detail: AdminAccountDetail; directory: Directory }> = ({ detail, directory }) => {
  if (detail.transactions.length === 0) {
    return <p className="text-xs text-muted-foreground">Nothing on the ledger yet.</p>;
  }
  return (
    <ul className="rounded-xl border border-border/70 divide-y divide-border/60 overflow-hidden">
      {detail.transactions.map((line) => {
        const meta = transactionMeta(line.type);
        const actor = line.actorUserId ? (directory.user(line.actorUserId)?.email ?? shortId(line.actorUserId)) : null;
        const what = line.operation
          ? `${line.operation}${line.category ? ` · ${categoryMeta(line.category).label}` : ''}`
          : line.reference;
        return (
          <li key={line.id} className="px-3 py-2.5 text-xs flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-0.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone={meta.tone}>{meta.label}</Badge>
                <span className="text-[11px] text-muted-foreground" title={formatDateTime(line.createdAt)}>
                  {timeAgo(line.createdAt)}
                </span>
              </div>
              {what && <p className="text-muted-foreground font-mono text-[11px] truncate">{what}</p>}
              {line.reason && <p className="text-foreground break-words">“{line.reason}”</p>}
              {actor && <p className="text-[11px] text-muted-foreground">by {actor}</p>}
            </div>
            <div className="text-right shrink-0 tabular-nums">
              <p
                className={`font-bold ${
                  line.credits > 0 ? 'text-emerald-600 dark:text-emerald-400' : line.credits < 0 ? 'text-foreground' : 'text-muted-foreground'
                }`}
              >
                {line.credits > 0 ? '+' : ''}
                {formatCreditAmount(line.credits)}
              </p>
              <p className="text-[11px] text-muted-foreground">→ {formatCreditAmount(line.balanceAfter)}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
};

/** One workspace's credit account: balance, lifetime totals, the last 30 days by category and the latest ledger lines. */
export const CreditAccountDrawer: React.FC<{
  workspaceId: string;
  name: string | null;
  detail: BillingQuery<AdminAccountDetail>;
  directory: Directory;
  busy: boolean;
  onAction: (kind: CreditActionKind, account: CreditAccount) => void;
  onClose: () => void;
}> = ({ workspaceId, name, detail, directory, busy, onAction, onClose }) => {
  const account = detail.data?.account ?? null;
  const status = account ? ACCOUNT_STATUS_META[account.status] : null;

  return (
    <Drawer
      title={name ?? `Workspace ${shortId(workspaceId)}`}
      subtitle={<span className="font-mono break-all">{workspaceId}</span>}
      onClose={onClose}
      width="max-w-2xl"
      footer={
        account && (
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              variant="outline"
              className="px-3 py-2 w-auto text-xs"
              icon={<MinusCircle className="w-3.5 h-3.5" />}
              iconPosition="left"
              disabled={busy}
              onClick={() => onAction('deduct', account)}
            >
              Deduct
            </Button>
            {account.status === 'SUSPENDED' ? (
              <Button
                variant="outline"
                className="px-3 py-2 w-auto text-xs"
                icon={<CircleCheck className="w-3.5 h-3.5" />}
                iconPosition="left"
                disabled={busy}
                onClick={() => onAction('reactivate', account)}
              >
                Reactivate
              </Button>
            ) : (
              <Button
                variant="destructive"
                className="px-3 py-2 w-auto text-xs"
                icon={<Ban className="w-3.5 h-3.5" />}
                iconPosition="left"
                disabled={busy}
                onClick={() => onAction('suspend', account)}
              >
                Suspend
              </Button>
            )}
            <Button
              className="px-3 py-2 w-auto text-xs"
              icon={<PlusCircle className="w-3.5 h-3.5" />}
              iconPosition="left"
              disabled={busy}
              onClick={() => onAction('grant', account)}
            >
              Grant credits
            </Button>
          </div>
        )
      }
    >
      {detail.error && !detail.data ? (
        <ErrorBlock message={detail.error} onRetry={detail.errorStatus === 404 ? undefined : detail.reload} />
      ) : !account || !detail.data ? (
        <LoadingBlock />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-1.5">
            {status && <Badge tone={status.tone}>{status.label}</Badge>}
            {account.balance <= 0 && <Badge tone="danger">{account.balance < 0 ? 'Negative balance' : 'No credits left'}</Badge>}
            {detail.loading && <span className="text-[11px] text-muted-foreground">Refreshing…</span>}
          </div>

          {account.status === 'SUSPENDED' && (
            <Notice tone="danger" icon={Ban}>
              Suspended{account.suspendedAt ? ` ${timeAgo(account.suspendedAt)}` : ''}: members can’t start paid operations.
              {account.suspendedReason ? ` Reason: “${account.suspendedReason}”.` : ''}
            </Notice>
          )}

          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-4">
            <KeyValue label="Balance">
              <span className="text-lg font-bold tabular-nums">{formatCreditAmount(account.balance)}</span>
            </KeyValue>
            <KeyValue label="Credited in total">{formatCredits(account.lifetimeCredited)}</KeyValue>
            <KeyValue label="Purchased in total">{formatCredits(account.lifetimePurchased)}</KeyValue>
            <KeyValue label="Used in total">{formatCreditAmount(account.lifetimeUsed)}</KeyValue>
            <KeyValue label="Last activity">
              <span title={formatDateTime(account.lastActivityAt)}>{account.lastActivityAt ? timeAgo(account.lastActivityAt) : 'Never'}</span>
            </KeyValue>
            <KeyValue label="Account created">{formatDateTime(account.createdAt)}</KeyValue>
          </dl>

          <section className="space-y-3">
            <h4 className="text-xs font-bold text-foreground flex items-center gap-2">
              <PieChart className="w-4 h-4 text-muted-foreground" /> Usage by category, last 30 days
            </h4>
            {detail.data.usageByCategory.every((row) => row.credits <= 0) ? (
              <p className="text-xs text-muted-foreground">No usage in the last 30 days.</p>
            ) : (
              <CategoryUsageBars categories={detail.data.usageByCategory} showCost />
            )}
          </section>

          <section className="space-y-2">
            <h4 className="text-xs font-bold text-foreground flex items-center gap-2">
              <History className="w-4 h-4 text-muted-foreground" /> Recent transactions
            </h4>
            <TransactionList detail={detail.data} directory={directory} />
          </section>
        </>
      )}
    </Drawer>
  );
};
