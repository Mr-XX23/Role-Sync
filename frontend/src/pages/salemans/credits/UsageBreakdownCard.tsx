import React from 'react';
import { AlertTriangle, Loader2, PieChart } from 'lucide-react';
import type { UsageSummary } from '../../../api/billingApi';
import { CategoryUsageBars } from '../../../components/billing/CategoryUsageBars';
import { PeriodPicker } from '../../../components/billing/PeriodPicker';
import type { PeriodDays } from '../../../components/billing/PeriodPicker';
import { formatCreditAmount } from '../../../utils/billingFormat';
import { formatDate } from '../userManagement/memberFormat';

/** What the workspace's credits went on over a period, as shares by category. */
export const UsageBreakdownCard: React.FC<{
  days: PeriodDays;
  onDaysChange: (days: PeriodDays) => void;
  summary: UsageSummary | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}> = ({ days, onDaysChange, summary: current, loading, error, onRetry }) => {
  return (
    <section className="bg-card border border-border rounded-2xl shadow-2xs min-w-0">
      <header className="px-6 pt-5 pb-4 border-b border-border/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-start gap-2.5 min-w-0">
          <PieChart className="w-5 h-5 text-primary shrink-0 mt-0.5" />
          <div className="min-w-0">
            <h3 className="font-serif text-lg font-bold text-foreground leading-tight">What credits were used for</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              {current
                ? `${formatCreditAmount(current.periodUsed)} credits used in the last ${current.periodDays} days`
                : `Credits used in the last ${days} days`}
            </p>
          </div>
        </div>
        <PeriodPicker value={days} onChange={onDaysChange} />
      </header>

      <div className={`px-6 py-5 transition-opacity ${loading && current ? 'opacity-60' : ''}`}>
        {error && !current ? (
          <div role="alert" className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">
            <span className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              {error}
            </span>
            <button
              type="button"
              onClick={onRetry}
              className="px-3 py-1.5 rounded-lg border border-border bg-background text-xs font-semibold text-foreground hover:bg-muted transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
            >
              Try again
            </button>
          </div>
        ) : !current ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading usage…
          </div>
        ) : current.periodUsed <= 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
            <div className="w-11 h-11 rounded-2xl bg-muted/70 text-muted-foreground flex items-center justify-center">
              <PieChart className="w-5 h-5" />
            </div>
            <p className="text-sm font-semibold text-foreground">No credits used in the last {current.periodDays} days</p>
            <p className="text-xs text-muted-foreground max-w-sm">
              Credits are used when the AI assistant answers, documents are read, the web is searched or connected apps sync.
            </p>
          </div>
        ) : (
          <CategoryUsageBars categories={current.categories} />
        )}
      </div>

      {current && (
        <footer className="px-6 py-3 border-t border-border/60 text-[11px] text-muted-foreground">
          {formatDate(current.from)} – {formatDate(current.to)} · shares of the credits used in this period
        </footer>
      )}
    </section>
  );
};
