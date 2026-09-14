import { useCallback, useEffect, useEffectEvent, useState } from 'react';
import { billingErrorStatus, describeBillingError } from '../api/billingApi';

interface Loaded<T> {
  key: string; // what was asked for
  request: string; // key + reload counter: the request this answers
  data: T | null;
  error: string | null;
  errorStatus: number | null;
}

export interface BillingQuery<T> {
  data: T | null;
  error: string | null;
  /** HTTP status of the failure (403: no access), when there was a response. */
  errorStatus: number | null;
  /** A request for the current key is in flight (a previous answer for the key stays visible). */
  loading: boolean;
  reload: () => void;
}

/**
 * Loads billing data for a key (the workspace, period or filters it depends on). A new key drops the
 * old answer; `reload()` keeps it visible until the new one arrives; answers to superseded requests
 * are ignored. With `load` null nothing is requested yet.
 */
export function useBillingQuery<T>(
  load: (() => Promise<T>) | null,
  key: string,
  audience: 'workspace' | 'admin' = 'workspace'
): BillingQuery<T> {
  const [reloads, setReloads] = useState(0);
  const [loaded, setLoaded] = useState<Loaded<T> | null>(null);
  const request = `${key}#${reloads}`;
  const enabled = load !== null;
  const fetchData = useEffectEvent(() => (load ? load() : Promise.reject(new Error('Nothing to load'))));

  useEffect(() => {
    if (!enabled) return undefined;
    let current = true;
    fetchData().then(
      (data) => {
        if (current) setLoaded({ key, request, data, error: null, errorStatus: null });
      },
      (error: unknown) => {
        if (!current) return;
        setLoaded((previous) => ({
          key,
          request,
          data: previous?.key === key ? previous.data : null,
          error: describeBillingError(error, audience),
          errorStatus: billingErrorStatus(error) ?? null,
        }));
      }
    );
    return () => {
      current = false;
    };
  }, [key, request, enabled, audience]);

  const reload = useCallback(() => setReloads((count) => count + 1), []);
  const sameKey = loaded?.key === key ? loaded : null;
  return {
    data: sameKey?.data ?? null,
    error: sameKey?.error ?? null,
    errorStatus: sameKey?.errorStatus ?? null,
    loading: enabled && loaded?.request !== request,
    reload,
  };
}
