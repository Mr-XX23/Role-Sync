import { useCallback, useEffect, useEffectEvent, useState } from 'react';
import { billingApi, billingErrorStatus, describeBillingError, FINAL_ORDER_STATUSES } from '../../api/billingApi';
import type { PaymentOrder } from '../../api/billingApi';

/** checking: not settled yet · settled: SUCCEEDED, FAILED, EXPIRED or REFUNDED · timeout: still pending when time ran out · failed: can't be read. */
export type OrderPhase = 'checking' | 'settled' | 'timeout' | 'failed';

interface PollState {
  run: string;
  phase: OrderPhase;
  order: PaymentOrder | null;
  error: string | null;
}

/** Answers that won't change by asking again. */
const FINAL_ERRORS = [400, 401, 403, 404];

/**
 * Follows an order after the payment provider sends the buyer back: asks every `intervalMs` until
 * the order settles or `timeoutMs` passes. The redirect itself proves nothing; only the provider's
 * webhook settles an order, usually within seconds. `retry()` starts following it again.
 */
export function useOrderPolling(
  orderId: string | null,
  {
    intervalMs = 2000,
    timeoutMs = 60000,
    onSettled,
  }: { intervalMs?: number; timeoutMs?: number; onSettled?: (order: PaymentOrder) => void } = {}
) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<PollState | null>(null);
  const run = `${orderId ?? ''}#${attempt}`;
  const settled = useEffectEvent((order: PaymentOrder) => onSettled?.(order));

  useEffect(() => {
    if (!orderId) return undefined;
    let cancelled = false;
    let timer: number | undefined;
    const startedAt = Date.now();

    const check = () => {
      billingApi.order(orderId).then(
        (order) => {
          if (cancelled) return;
          if (FINAL_ORDER_STATUSES.includes(order.status)) {
            setState({ run, phase: 'settled', order, error: null });
            settled(order);
            return;
          }
          const timedOut = Date.now() - startedAt >= timeoutMs;
          setState({ run, phase: timedOut ? 'timeout' : 'checking', order, error: null });
          if (!timedOut) timer = window.setTimeout(check, intervalMs);
        },
        (error: unknown) => {
          if (cancelled) return;
          const status = billingErrorStatus(error);
          const final = status !== undefined && FINAL_ERRORS.includes(status);
          if (final || Date.now() - startedAt >= timeoutMs) {
            setState((previous) => ({
              run,
              phase: final ? 'failed' : 'timeout',
              order: previous?.run === run ? previous.order : null,
              error: describeBillingError(error),
            }));
            return;
          }
          // A passing failure (network, 5xx): keep asking until the time is up.
          timer = window.setTimeout(check, intervalMs);
        }
      );
    };

    check();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [orderId, run, intervalMs, timeoutMs]);

  const retry = useCallback(() => setAttempt((count) => count + 1), []);
  const current = state?.run === run ? state : null;
  return {
    phase: current?.phase ?? 'checking',
    order: current?.order ?? null,
    error: current?.error ?? null,
    retry,
  };
}
