import React from 'react';
import { AlertTriangle, Ban, Coins } from 'lucide-react';
import type { CreditBalance, UsageSummary } from '../../../api/billingApi';
import { UsageRing } from '../../../components/billing/UsageRing';
import { formatCreditAmount, formatCredits, formatCreditsLabel } from '../../../utils/billingFormat';

const Figure: React.FC<{ label: string; value: string; hint?: string }> = ({ label, value, hint }) => (
  <div className="min-w-0">
    <p className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground">{label}</p>
    <p className="text-lg font-bold text-foreground tabular-nums leading-tight">{value}</p>
    {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
  </div>
);

/**
 * The workspace's balance, its status and how much of everything it was ever given is used up.
 * Works from the live balance, the usage summary, or both.
 */
export const BalanceCard: React.FC<{ credits: CreditBalance | null; summary: UsageSummary | null }> = ({ credits, summary }) => {
  const balance = credits?.balance ?? summary?.balance ?? 0;
  const lifetimeCredited = credits?.lifetimeCredited ?? summary?.lifetimeCredited ?? 0;
  const lifetimeUsed = credits?.lifetimeUsed ?? summary?.lifetimeUsed ?? 0;
  const usedPercent = summary?.usedPercent ?? (lifetimeCredited > 0 ? (lifetimeUsed / lifetimeCredited) * 100 : 0);
  const suspended = credits?.status === 'SUSPENDED';
  const empty = balance <= 0;
  const low = !empty && Boolean(credits?.lowBalance);

  return (
    <section className="bg-card border border-border rounded-2xl shadow-2xs p-6 flex flex-col sm:flex-row sm:items-center gap-6 min-w-0">
      <div className="flex-1 min-w-0 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground">Available balance</span>
          {credits &&
            (suspended ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[10px] font-mono font-bold uppercase bg-red-500/10 text-red-700 dark:text-red-300 border-red-500/25">
                <Ban className="w-3 h-3" /> Suspended
              </span>
            ) : empty ? (
              <span className="px-2 py-0.5 rounded-md border text-[10px] font-mono font-bold uppercase bg-red-500/10 text-red-700 dark:text-red-300 border-red-500/25">
                Out of credits
              </span>
            ) : low ? (
              <span className="px-2 py-0.5 rounded-md border text-[10px] font-mono font-bold uppercase bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/25">
                Running low
              </span>
            ) : (
              <span className="px-2 py-0.5 rounded-md border text-[10px] font-mono font-bold uppercase bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/25">
                Active
              </span>
            ))}
        </div>

        <div className="flex items-center gap-3">
          <div
            className={`w-12 h-12 rounded-xl border flex items-center justify-center shrink-0 ${
              suspended || empty
                ? 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20'
                : low
                  ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
                  : 'bg-primary/10 text-primary border-primary/20'
            }`}
          >
            <Coins className="w-6 h-6" />
          </div>
          <p className="font-serif text-4xl font-bold text-foreground tabular-nums leading-none">
            {formatCredits(balance)}
            <span className="ml-2 font-sans text-base font-semibold text-muted-foreground">
              {Math.floor(balance) === 1 ? 'credit' : 'credits'}
            </span>
          </p>
        </div>

        {suspended ? (
          <p className="flex items-start gap-2 text-xs text-red-700 dark:text-red-300 leading-relaxed">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            The RoleSync team suspended credits for this workspace, so new AI actions can’t start. Contact support to sort it out.
          </p>
        ) : empty ? (
          <p className="flex items-start gap-2 text-xs text-red-700 dark:text-red-300 leading-relaxed">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            New AI actions are paused until credits are added.
            {balance < 0 ? ' The next top-up first covers the credits used past zero.' : ''}
          </p>
        ) : low && credits ? (
          <p className="flex items-start gap-2 text-xs text-amber-700 dark:text-amber-300 leading-relaxed">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            Fewer than {formatCreditsLabel(credits.lowBalanceThreshold)} left. Top up to keep the agent working.
          </p>
        ) : (
          <p className="text-xs text-muted-foreground leading-relaxed">Credits never expire and are shared by everyone in the workspace.</p>
        )}

        <div className="grid grid-cols-2 gap-4 pt-1">
          <Figure label="Credited in total" value={formatCredits(lifetimeCredited)} hint="Free credits, packs and grants" />
          <Figure label="Used in total" value={formatCreditAmount(lifetimeUsed)} hint="Since the workspace started" />
        </div>
      </div>

      <div className="flex sm:flex-col items-center gap-3 sm:w-40 shrink-0">
        <UsageRing
          percent={usedPercent}
          caption="used"
          tone={usedPercent >= 90 ? 'danger' : usedPercent >= 75 ? 'warning' : 'primary'}
        />
        <p className="text-[11px] text-muted-foreground text-left sm:text-center leading-snug">
          {formatCreditAmount(lifetimeUsed)} of {formatCredits(lifetimeCredited)} credits
        </p>
      </div>
    </section>
  );
};
