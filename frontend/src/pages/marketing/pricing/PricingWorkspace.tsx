import React from 'react';
import { Building2, Loader2, LogIn } from 'lucide-react';
import type { EnsuredWorkspace } from '../../../hooks/useEnsureWorkspace';
import { useAppDispatch } from '../../../store';
import { rememberWorkspace, setCurrentWorkspace } from '../../../store/workspaceSlice';

/** Which workspace a purchase tops up (credits belong to a workspace), with a switch for people in several. */
export const PricingWorkspace: React.FC<{ ensured: EnsuredWorkspace }> = ({ ensured }) => {
  const dispatch = useAppDispatch();

  if (!ensured.signedIn) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <LogIn className="w-3.5 h-3.5 shrink-0" />
        You’ll sign in first, then come straight back here to pay.
      </p>
    );
  }
  if (ensured.status === 'failed') {
    return (
      <p role="alert" className="flex flex-wrap items-center gap-2 text-xs text-destructive">
        {ensured.error ?? 'We couldn’t load your workspace.'}
        <button type="button" onClick={ensured.retry} className="font-semibold underline underline-offset-2 cursor-pointer">
          Try again
        </button>
      </p>
    );
  }
  const { workspace, workspaces } = ensured;
  if (ensured.status !== 'ready' || !workspace) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        Loading your workspace…
      </p>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <Building2 className="w-3.5 h-3.5 shrink-0" />
      {workspaces.length > 1 ? (
        <>
          <label htmlFor="pricing-workspace">Credits go to</label>
          <select
            id="pricing-workspace"
            value={workspace.workspaceId}
            onChange={(event) => {
              const chosen = workspaces.find((item) => item.workspaceId === event.target.value);
              if (chosen) {
                dispatch(setCurrentWorkspace(chosen));
                rememberWorkspace(chosen.workspaceId);
              }
            }}
            className="max-w-[14rem] py-1.5 px-2.5 rounded-lg border border-border bg-background text-xs font-semibold text-foreground focus:outline-none focus:ring-2 focus:ring-primary/10 focus:border-primary cursor-pointer"
          >
            {workspaces.map((item) => (
              <option key={item.workspaceId} value={item.workspaceId}>
                {item.name}
                {item.isActive === false ? ' (suspended)' : ''}
              </option>
            ))}
          </select>
        </>
      ) : (
        <span>
          Credits go to <span className="font-semibold text-foreground">{workspace.name}</span>
        </span>
      )}
      {workspace.isActive === false && (
        <span className="text-destructive">This workspace is suspended, so it can’t buy credits.</span>
      )}
    </div>
  );
};
