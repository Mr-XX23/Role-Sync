import React from 'react';
import type { CategoryUsage } from '../../api/billingApi';
import { formatCreditAmount, formatPercent, formatUsd } from '../../utils/billingFormat';
import { categoryMeta } from './categoryMeta';

/** Credits by usage category as shares of the period, largest first; categories with no use stay listed, dimmed. */
export const CategoryUsageBars: React.FC<{
  categories: CategoryUsage[];
  /** Show the provider cost next to the credits (console only). */
  showCost?: boolean;
}> = ({ categories, showCost = false }) => {
  const rows = [...categories].sort((a, b) => b.credits - a.credits);
  return (
    <ul className="space-y-3">
      {rows.map((row) => {
        const meta = categoryMeta(row.category);
        const Icon = meta.icon;
        const percent = Math.min(100, Math.max(0, row.percent));
        const idle = row.credits <= 0;
        return (
          <li key={row.category} className={`flex items-start gap-3 ${idle ? 'opacity-55' : ''}`}>
            <div className={`w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 ${meta.iconClass}`}>
              <Icon className="w-4 h-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-3 text-xs">
                <span className="font-semibold text-foreground truncate">{row.label || meta.label}</span>
                <span className="font-bold text-foreground tabular-nums shrink-0">{formatPercent(percent)}</span>
              </div>
              <div className="mt-1.5 h-2 rounded-full bg-muted overflow-hidden" aria-hidden="true">
                <div
                  className={`h-full rounded-full ${meta.bar} transition-all duration-500`}
                  style={{ width: `${idle ? 0 : Math.max(percent, 1.5)}%` }}
                />
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground tabular-nums">
                {formatCreditAmount(row.credits)} credits
                {showCost && row.costUsd !== undefined ? ` · ${formatUsd(row.costUsd)} cost` : ''}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
};
