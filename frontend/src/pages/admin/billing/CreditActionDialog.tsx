import React, { useId, useState } from 'react';
import { Ban, CircleCheck, MinusCircle, PlusCircle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { billingApi, billingErrorCode, billingErrorStatus, describeBillingError } from '../../../api/billingApi';
import type { CreditAccount } from '../../../api/billingApi';
import { Button } from '../../../components/common/Button';
import { useToast } from '../../../context/ToastContext';
import { formatCreditAmount, formatCredits, formatCreditsLabel } from '../../../utils/billingFormat';
import { ErrorBlock, Modal, Notice, inputClass, labelClass } from '../components/AdminUi';
import { MAX_REASON, parseCreditAmount } from './billingMeta';

export type CreditActionKind = 'grant' | 'deduct' | 'suspend' | 'reactivate';

const COPY: Record<CreditActionKind, { title: string; confirm: string; busy: string; icon: LucideIcon; destructive: boolean }> = {
  grant: { title: 'Grant credits', confirm: 'Grant credits', busy: 'Granting…', icon: PlusCircle, destructive: false },
  deduct: { title: 'Deduct credits', confirm: 'Deduct credits', busy: 'Deducting…', icon: MinusCircle, destructive: true },
  suspend: { title: 'Suspend credits', confirm: 'Suspend credits', busy: 'Suspending…', icon: Ban, destructive: true },
  reactivate: { title: 'Reactivate credits', confirm: 'Reactivate', busy: 'Reactivating…', icon: CircleCheck, destructive: false },
};

/**
 * Grant, deduct, suspend or reactivate one workspace's credits. Every action needs a reason (kept on
 * the ledger with the admin's id); deducting and suspending ask for a second confirmation.
 */
export const CreditActionDialog: React.FC<{
  kind: CreditActionKind;
  account: CreditAccount;
  workspaceName: string;
  onClose: () => void;
  onDone: (account: CreditAccount) => void;
}> = ({ kind, account, workspaceName, onClose, onDone }) => {
  const toast = useToast();
  const amountId = useId();
  const reasonId = useId();
  const negativeId = useId();
  const copy = COPY[kind];
  const withAmount = kind === 'grant' || kind === 'deduct';

  const [amountText, setAmountText] = useState('');
  const [reason, setReason] = useState('');
  const [allowNegative, setAllowNegative] = useState(false);
  const [showErrors, setShowErrors] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const amount = withAmount ? parseCreditAmount(amountText) : { value: null, error: null };
  const reasonError = !reason.trim() ? 'Give a reason; it is kept with the change.' : reason.length > MAX_REASON ? `At most ${MAX_REASON} characters.` : null;
  const valid = !amount.error && !reasonError;
  const after = amount.value === null ? null : kind === 'grant' ? account.balance + amount.value : account.balance - amount.value;
  const overdraws = kind === 'deduct' && amount.value !== null && amount.value > account.balance;
  const name = <span className="font-semibold text-foreground">{workspaceName}</span>;

  const run = async () => {
    setBusy(true);
    setServerError(null);
    const why = reason.trim();
    try {
      let updated: CreditAccount;
      switch (kind) {
        case 'grant':
          updated = await billingApi.admin.grant(account.workspaceId, amount.value ?? 0, why);
          toast.success(`${formatCreditsLabel(amount.value)} added to ${workspaceName}.`, 'Credits granted');
          break;
        case 'deduct':
          updated = await billingApi.admin.deduct(account.workspaceId, amount.value ?? 0, why, allowNegative);
          toast.success(`${formatCreditsLabel(amount.value)} removed from ${workspaceName}.`, 'Credits deducted');
          break;
        case 'suspend':
          updated = await billingApi.admin.suspend(account.workspaceId, why);
          toast.success(`${workspaceName} can’t start paid operations until you reactivate it.`, 'Credits suspended');
          break;
        case 'reactivate':
          updated = await billingApi.admin.reactivate(account.workspaceId, why);
          toast.success(`${workspaceName} can spend credits again.`, 'Credits reactivated');
          break;
      }
      onDone(updated);
    } catch (error) {
      const insufficient = billingErrorCode(error) === 'INSUFFICIENT_BALANCE' || (kind === 'deduct' && billingErrorStatus(error) === 409);
      setServerError(
        insufficient && !allowNegative
          ? `${describeBillingError(error, 'admin')} Tick “Allow a negative balance” to deduct anyway.`
          : describeBillingError(error, 'admin')
      );
      // Back to the form, so the amount or the negative-balance choice can be changed.
      setConfirming(false);
      setBusy(false);
    }
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setShowErrors(true);
    if (!valid) return;
    if (copy.destructive && !confirming) {
      setConfirming(true);
      return;
    }
    void run();
  };

  return (
    <Modal
      title={copy.title}
      subtitle={workspaceName}
      icon={copy.icon}
      onClose={onClose}
      busy={busy}
      width="max-w-md"
      footer={
        <>
          <button
            type="button"
            onClick={confirming ? () => setConfirming(false) : onClose}
            disabled={busy}
            className="px-4 py-2 text-xs font-medium rounded-xl border border-border/70 hover:bg-muted/60 text-muted-foreground hover:text-foreground transition-colors cursor-pointer disabled:opacity-50"
          >
            {confirming ? 'Back' : 'Cancel'}
          </button>
          <Button
            type="submit"
            form={`${amountId}-form`}
            variant={copy.destructive ? 'destructive' : 'primary'}
            className="px-4 py-2 w-auto text-xs"
            isLoading={busy}
            loadingText={copy.busy}
          >
            {confirming ? `Yes, ${copy.confirm.toLowerCase()}` : copy.confirm}
          </Button>
        </>
      }
    >
      <form id={`${amountId}-form`} onSubmit={submit} noValidate className="space-y-4">
        <div className="grid grid-cols-2 gap-3 rounded-xl border border-border/70 bg-muted/20 px-4 py-3">
          <div>
            <p className={labelClass}>Balance now</p>
            <p className="text-sm font-bold text-foreground tabular-nums">{formatCreditAmount(account.balance)}</p>
          </div>
          <div>
            <p className={labelClass}>Status</p>
            <p className="text-sm font-bold text-foreground">{account.status === 'SUSPENDED' ? 'Suspended' : 'Active'}</p>
          </div>
        </div>

        {confirming ? (
          <Notice tone="danger" icon={copy.icon}>
            {kind === 'deduct' ? (
              <>
                Remove <span className="font-semibold">{formatCreditsLabel(amount.value)}</span> from {name}? The balance goes from{' '}
                {formatCreditAmount(account.balance)} to <span className="font-semibold">{formatCreditAmount(after)}</span>
                {after !== null && after < 0 ? ', below zero' : ''}. Nothing is refunded to the customer.
              </>
            ) : (
              <>
                Suspend credits for {name}? Its members can’t start AI actions or other paid operations until you reactivate it.
                Operations already running finish and are still charged.
              </>
            )}
          </Notice>
        ) : (
          <>
            {kind === 'suspend' && (
              <p className="text-sm text-muted-foreground leading-relaxed">
                Members of {name} can’t start paid operations while credits are suspended. The balance stays as it is.
              </p>
            )}
            {kind === 'reactivate' && (
              <p className="text-sm text-muted-foreground leading-relaxed">
                Members of {name} can spend credits again right away.
                {account.suspendedReason ? ` It was suspended because: “${account.suspendedReason}”.` : ''}
              </p>
            )}

            {withAmount && (
              <div className="space-y-1">
                <label htmlFor={amountId} className={labelClass}>
                  Credits to {kind === 'grant' ? 'add' : 'remove'}
                </label>
                <input
                  id={amountId}
                  inputMode="decimal"
                  autoComplete="off"
                  value={amountText}
                  disabled={busy}
                  onChange={(event) => setAmountText(event.target.value)}
                  placeholder="e.g. 500"
                  aria-invalid={showErrors && Boolean(amount.error)}
                  aria-describedby={`${amountId}-hint`}
                  className={inputClass}
                />
                <p id={`${amountId}-hint`} className={`text-[11px] ${showErrors && amount.error ? 'text-destructive' : 'text-muted-foreground'}`}>
                  {showErrors && amount.error
                    ? amount.error
                    : after !== null
                      ? `Balance afterwards: ${formatCreditAmount(after)}`
                      : `More than 0 and at most ${formatCredits(1_000_000)}, up to 3 decimals.`}
                </p>
              </div>
            )}

            {kind === 'deduct' && (
              <div className="space-y-1">
                <label htmlFor={negativeId} className="flex items-start gap-2 text-xs text-foreground cursor-pointer select-none">
                  <input
                    id={negativeId}
                    type="checkbox"
                    checked={allowNegative}
                    disabled={busy}
                    onChange={(event) => setAllowNegative(event.target.checked)}
                    className="mt-0.5 accent-primary"
                  />
                  <span>
                    Allow a negative balance
                    <span className="block text-[11px] text-muted-foreground">
                      Without this, deducting more than the balance is refused. A negative balance is paid back by the next purchase or grant.
                    </span>
                  </span>
                </label>
                {overdraws && !allowNegative && (
                  <p className="text-[11px] text-amber-700 dark:text-amber-300">
                    That’s more than the balance, so it will be refused unless you allow a negative balance.
                  </p>
                )}
              </div>
            )}

            <div className="space-y-1">
              <label htmlFor={reasonId} className={labelClass}>
                Reason
              </label>
              <textarea
                id={reasonId}
                value={reason}
                rows={3}
                maxLength={MAX_REASON}
                disabled={busy}
                onChange={(event) => setReason(event.target.value)}
                placeholder={kind === 'grant' ? 'e.g. Goodwill credit for the outage on Sep 12' : 'Why are you doing this?'}
                aria-invalid={showErrors && Boolean(reasonError)}
                aria-describedby={`${reasonId}-hint`}
                className={`${inputClass} resize-none`}
              />
              <p id={`${reasonId}-hint`} className={`text-[11px] ${showErrors && reasonError ? 'text-destructive' : 'text-muted-foreground'}`}>
                {showErrors && reasonError ? reasonError : `Kept on the account’s ledger with your name. ${reason.length}/${MAX_REASON}`}
              </p>
            </div>
          </>
        )}

        {serverError && <ErrorBlock message={serverError} compact />}
      </form>
    </Modal>
  );
};
