import React from 'react';
import type { WorkspaceCreditUsage } from '../../../api/billingApi';
import { formatCreditAmount, formatUsd } from '../../../utils/billingFormat';
import { shortId } from '../adminFormat';
import type { Directory } from '../useDirectory';

/** The workspaces that used the most credits, each opening its credit account. */
export const TopWorkspaces: React.FC<{
  rows: WorkspaceCreditUsage[];
  directory: Directory;
  onOpen: (workspaceId: string) => void;
}> = ({ rows, directory, onOpen }) => {
  if (rows.length === 0) {
    return <p className="text-xs text-muted-foreground py-6 text-center">No workspace used credits in this period.</p>;
  }
  const max = Math.max(0, ...rows.map((row) => row.credits));
  return (
    <ol className="space-y-1.5">
      {rows.map((row, index) => {
        const name = directory.workspace(row.workspaceId)?.name;
        return (
          <li key={row.workspaceId}>
            <button
              type="button"
              onClick={() => onOpen(row.workspaceId)}
              title="Open credit account"
              className="relative w-full rounded-lg overflow-hidden text-left group cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
            >
              <span
                className="absolute inset-y-0 left-0 bg-primary/15 group-hover:bg-primary/25 transition-colors"
                style={{ width: `${max > 0 ? (row.credits / max) * 100 : 0}%` }}
              />
              <span className="relative flex items-center justify-between gap-3 px-2.5 py-1.5 text-xs">
                <span className="min-w-0 flex items-center gap-2">
                  <span className="w-4 shrink-0 text-[10px] font-mono text-muted-foreground tabular-nums">{index + 1}</span>
                  <span className="min-w-0">
                    <span className="block truncate text-foreground font-medium group-hover:underline">
                      {name ?? `Workspace ${shortId(row.workspaceId)}`}
                    </span>
                    <span className="block truncate text-[10px] text-muted-foreground">
                      <span className="font-mono">{shortId(row.workspaceId)}</span> · {formatUsd(row.costUsd)} cost
                    </span>
                  </span>
                </span>
                <span className="tabular-nums text-foreground shrink-0">{formatCreditAmount(row.credits)}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
};
