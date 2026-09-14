import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, ArrowRight, Loader2, Plus, RefreshCw, ShieldCheck, Sparkles } from 'lucide-react';
import { billingApi } from '../../../api/billingApi';
import type { PeriodDays } from '../../../components/billing/PeriodPicker';
import { useCredits } from '../../../context/creditsContext';
import { useBillingQuery } from '../../../hooks/useBillingQuery';
import { useAppSelector } from '../../../store';
import { BalanceCard } from './BalanceCard';
import { UsageBreakdownCard } from './UsageBreakdownCard';

const buyLink =
  'inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-xs font-semibold text-primary-foreground shadow-2xs hover:opacity-90 active:scale-[0.98] transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40';

/**
 * Credits & Usage: the workspace's balance, how much of it is used, and what it was used for by
 * category over 7, 30 or 90 days. Deliberately no list of individual charges.
 */
export const Credits: React.FC = () => {
  const workspaceId = useAppSelector((state) => state.workspace.currentWorkspace?.workspaceId) ?? '';
  const workspaceName = useAppSelector((state) => state.workspace.currentWorkspace?.name) ?? 'this workspace';
  const credits = useCredits();
  const [days, setDays] = useState<PeriodDays>(30);
  const summary = useBillingQuery(workspaceId ? () => billingApi.usageSummary(days) : null, `${workspaceId}:${days}`);

  const refreshAll = () => {
    credits.refresh();
    summary.reload();
  };
  const noAccess = summary.errorStatus === 403 || credits.errorStatus === 403;
  const balanceKnown = credits.credits !== null || summary.data !== null;

  return (
    <div className="flex flex-col gap-6 pb-10 animate-in fade-in duration-300">
      <section className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div className="space-y-2">
          <h2 className="font-serif text-3xl font-bold text-primary">Credits &amp; Usage</h2>
          <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
            Everyone in {workspaceName} shares one credit balance. See how much is left and what it’s being used for.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={refreshAll}
            disabled={summary.loading}
            title="Refresh"
            aria-label="Refresh credits and usage"
            className="p-2 rounded-xl border border-border text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors cursor-pointer disabled:cursor-default bg-card focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
          >
            <RefreshCw className={`w-4 h-4 ${summary.loading ? 'animate-spin' : ''}`} />
          </button>
          <Link to="/pricing" className={buyLink}>
            <Plus className="w-4 h-4" />
            Buy credits
          </Link>
        </div>
      </section>

      {noAccess ? (
        <div className="flex flex-col items-center justify-center text-center gap-3 py-16 bg-card border border-border/70 rounded-2xl">
          <div className="w-12 h-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <p className="font-serif text-xl font-bold text-foreground">You can’t see this workspace’s credits</p>
          <p className="text-xs text-muted-foreground max-w-md">
            Only members of {workspaceName} can see its balance and usage. If you were removed recently, switch to another
            workspace.
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 items-stretch">
            <div className="xl:col-span-2 min-w-0">
              {balanceKnown ? (
                <BalanceCard credits={credits.credits} summary={summary.data} />
              ) : credits.loading || summary.loading ? (
                <div className="h-full min-h-[14rem] flex items-center justify-center gap-2 bg-card border border-border rounded-2xl text-sm text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading your balance…
                </div>
              ) : (
                <div
                  role="alert"
                  className="h-full min-h-[14rem] flex flex-col items-center justify-center gap-3 text-center bg-card border border-border rounded-2xl px-6"
                >
                  <AlertTriangle className="w-6 h-6 text-red-500" />
                  <p className="text-sm text-foreground">{credits.error ?? summary.error ?? 'The balance couldn’t be loaded.'}</p>
                  <button
                    type="button"
                    onClick={refreshAll}
                    className="px-3 py-1.5 rounded-lg border border-border bg-background text-xs font-semibold text-foreground hover:bg-muted transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                  >
                    Try again
                  </button>
                </div>
              )}
            </div>

            <section className="bg-card border border-border rounded-2xl shadow-2xs p-6 flex flex-col gap-4">
              <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary/30 via-primary/15 to-transparent border border-primary/25 text-primary flex items-center justify-center">
                <Sparkles className="w-5 h-5" />
              </div>
              <div className="space-y-1.5 flex-1">
                <h3 className="font-serif text-lg font-bold text-foreground">Need more credits?</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Buy a credit pack for {workspaceName}. It’s a one-time payment through Stripe, credits never expire, and
                  bigger packs cost less per credit.
                </p>
              </div>
              <Link to="/pricing" className={`${buyLink} w-full`}>
                See credit packs
                <ArrowRight className="w-4 h-4" />
              </Link>
            </section>
          </div>

          <UsageBreakdownCard
            days={days}
            onDaysChange={setDays}
            summary={summary.data}
            loading={summary.loading}
            error={summary.error}
            onRetry={summary.reload}
          />
        </>
      )}
    </div>
  );
};

export default Credits;
