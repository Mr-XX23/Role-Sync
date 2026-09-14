import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { billingApi, billingErrorStatus, describeBillingError } from '../api/billingApi';
import type { CreditBalance } from '../api/billingApi';
import { onCreditsRequired } from '../api/creditEvents';
import { useAppSelector } from '../store';
import { CreditsContext } from './creditsContext';
import type { CreditsNotice, CreditsState } from './creditsContext';

const REFRESH_EVERY_MS = 30_000;
/** Focus and visibility events arrive in bursts, and a poll may have just run: one request covers them. */
const MIN_GAP_MS = 5_000;
/** Answers meaning the balance can't be seen at all, rather than a passing failure. */
const ACCESS_ERRORS = [401, 403, 404];

interface Loaded {
  workspaceId: string;
  credits: CreditBalance | null;
  error: string | null;
  errorStatus: number | null;
}

/** A refused operation stops being a problem once the account can spend again. */
function resolves(notice: CreditsNotice, credits: CreditBalance): boolean {
  if (credits.status === 'SUSPENDED') return false;
  return notice.code === 'CREDITS_SUSPENDED' || credits.balance > 0;
}

/**
 * Keeps the active workspace's credit balance fresh: when it becomes active, every 30 s while the
 * tab is visible, when the window regains focus, straight after any 402 and on demand.
 */
export const CreditsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const workspaceId = useAppSelector((state) =>
    state.auth.isAuthenticated && state.workspace.workspaceStatus === 'ready'
      ? (state.workspace.currentWorkspace?.workspaceId ?? null)
      : null
  );
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [notice, setNotice] = useState<CreditsNotice | null>(null);
  // An answer is only used while its workspace is still active and no newer request was sent.
  const latest = useRef<{ workspaceId: string | null; request: number; startedAt: number }>({
    workspaceId: null,
    request: 0,
    startedAt: 0,
  });

  const load = useCallback((force: boolean) => {
    const { workspaceId: target, request, startedAt } = latest.current;
    if (!target || (!force && Date.now() - startedAt < MIN_GAP_MS)) return;
    const thisRequest = request + 1;
    latest.current = { workspaceId: target, request: thisRequest, startedAt: Date.now() };
    const stillWanted = () => latest.current.workspaceId === target && latest.current.request === thisRequest;

    billingApi.credits(target).then(
      (credits) => {
        if (!stillWanted()) return;
        setLoaded({ workspaceId: target, credits, error: null, errorStatus: null });
        setNotice((shown) => (shown && shown.workspaceId === target && resolves(shown, credits) ? null : shown));
      },
      (error: unknown) => {
        if (!stillWanted()) return;
        const status = billingErrorStatus(error) ?? null;
        setLoaded((previous) => ({
          workspaceId: target,
          // Keep the last balance through a passing failure; drop it once access is gone.
          credits:
            previous?.workspaceId === target && !ACCESS_ERRORS.includes(status ?? 0) ? previous.credits : null,
          error: describeBillingError(error),
          errorStatus: status,
        }));
      }
    );
  }, []);

  // Follow the active workspace; answers still on their way for the previous one are ignored.
  useEffect(() => {
    latest.current = { workspaceId, request: latest.current.request + 1, startedAt: 0 };
    load(true);
  }, [workspaceId, load]);

  useEffect(() => {
    if (!workspaceId) return undefined;
    const whenVisible = () => {
      if (document.visibilityState === 'visible') load(false);
    };
    const timer = window.setInterval(whenVisible, REFRESH_EVERY_MS);
    window.addEventListener('focus', whenVisible);
    document.addEventListener('visibilitychange', whenVisible);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', whenVisible);
      document.removeEventListener('visibilitychange', whenVisible);
    };
  }, [workspaceId, load]);

  // A 402 from any API: say why, and reload the balance right away.
  useEffect(
    () =>
      onCreditsRequired((event) => {
        const target = latest.current.workspaceId;
        if (!target) return;
        setNotice({ id: Date.now(), workspaceId: target, code: event.code, message: event.message });
        load(true);
      }),
    [load]
  );

  const refresh = useCallback(() => load(true), [load]);
  const dismissNotice = useCallback(() => setNotice(null), []);
  const mine = loaded !== null && loaded.workspaceId === workspaceId ? loaded : null;
  const shownNotice = notice !== null && notice.workspaceId === workspaceId ? notice : null;

  const value = useMemo<CreditsState>(
    () => ({
      workspaceId,
      credits: mine?.credits ?? null,
      loading: workspaceId !== null && mine === null,
      error: mine?.error ?? null,
      errorStatus: mine?.errorStatus ?? null,
      refresh,
      notice: shownNotice,
      dismissNotice,
    }),
    [workspaceId, mine, refresh, shownNotice, dismissNotice]
  );

  return <CreditsContext.Provider value={value}>{children}</CreditsContext.Provider>;
};
