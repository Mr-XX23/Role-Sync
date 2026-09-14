import React from 'react';
import type { ModelUsage, OperationUsage } from '../../../api/billingApi';
import { categoryMeta } from '../../../components/billing/categoryMeta';
import { formatCreditAmount, formatUsd } from '../../../utils/billingFormat';
import { formatCompact, formatNumber } from '../adminFormat';

const head = 'text-muted-foreground uppercase text-[10px] tracking-wide border-b border-border/70 bg-muted/40';
const cell = 'px-4 py-2.5 whitespace-nowrap';

const Empty: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p className="text-xs text-muted-foreground px-5 py-10 text-center">{children}</p>
);

/** Charges grouped by operation (agent.model_call, document.ingest…), heaviest first. */
export const OperationTable: React.FC<{ rows: OperationUsage[] }> = ({ rows }) => {
  if (rows.length === 0) return <Empty>No charges in this period.</Empty>;
  const sorted = [...rows].sort((a, b) => b.credits - a.credits);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs text-left">
        <thead className={head}>
          <tr>
            <th className={`${cell} font-semibold`}>Operation</th>
            <th className={`${cell} font-semibold text-right`}>Charges</th>
            <th className={`${cell} font-semibold text-right`}>Credits</th>
            <th className={`${cell} font-semibold text-right`}>Provider cost</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">
          {sorted.map((row) => (
            <tr key={`${row.operation}:${row.category}`} className="hover:bg-muted/20 transition-colors">
              <td className={cell}>
                <span className="block font-mono text-foreground">{row.operation}</span>
                <span className="block text-[10px] text-muted-foreground">{categoryMeta(row.category).label}</span>
              </td>
              <td className={`${cell} text-right tabular-nums text-muted-foreground`}>{formatNumber(row.count)}</td>
              <td className={`${cell} text-right tabular-nums text-foreground font-semibold`}>{formatCreditAmount(row.credits)}</td>
              <td className={`${cell} text-right tabular-nums text-muted-foreground`}>{formatUsd(row.costUsd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

/** Metered model calls by model, with the tokens behind them. */
export const ModelTable: React.FC<{ rows: ModelUsage[] }> = ({ rows }) => {
  if (rows.length === 0) return <Empty>No model calls were charged in this period.</Empty>;
  const sorted = [...rows].sort((a, b) => b.costUsd - a.costUsd);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs text-left">
        <thead className={head}>
          <tr>
            <th className={`${cell} font-semibold`}>Model</th>
            <th className={`${cell} font-semibold text-right`}>Calls</th>
            <th className={`${cell} font-semibold text-right`}>Input tokens</th>
            <th className={`${cell} font-semibold text-right`}>Cached input</th>
            <th className={`${cell} font-semibold text-right`}>Output tokens</th>
            <th className={`${cell} font-semibold text-right`}>Credits</th>
            <th className={`${cell} font-semibold text-right`}>Provider cost</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">
          {sorted.map((row) => (
            <tr key={row.model} className="hover:bg-muted/20 transition-colors">
              <td className={`${cell} font-mono text-foreground`}>{row.model}</td>
              <td className={`${cell} text-right tabular-nums text-muted-foreground`}>{formatNumber(row.calls)}</td>
              <td className={`${cell} text-right tabular-nums text-muted-foreground`}>{formatCompact(row.inputTokens)}</td>
              <td className={`${cell} text-right tabular-nums text-muted-foreground`}>{formatCompact(row.cachedInputTokens)}</td>
              <td className={`${cell} text-right tabular-nums text-muted-foreground`}>{formatCompact(row.outputTokens)}</td>
              <td className={`${cell} text-right tabular-nums text-foreground font-semibold`}>{formatCreditAmount(row.credits)}</td>
              <td className={`${cell} text-right tabular-nums text-muted-foreground`}>{formatUsd(row.costUsd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
