import { useCallback, useEffect, useRef, useState } from 'react';
import { billingApi, describeBillingError } from '../../../api/billingApi';
import type { CreditPackage } from '../../../api/billingApi';

export interface Checkout {
  /** The pack whose checkout is starting (or has started and the browser is leaving). */
  pendingCode: string | null;
  /** Checkout started: the browser is on its way to the payment page. */
  redirecting: boolean;
  error: { code: string; message: string } | null;
  buy: (pkg: CreditPackage) => void;
}

/** Only a web address is followed, never another kind of URL a bad answer could smuggle in. */
function checkoutAddress(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
  } catch {
    return null;
  }
}

/**
 * Buying a credit pack for the active workspace: one checkout at a time, a fresh idempotency key per
 * click, then a full-page redirect to the payment provider.
 */
export function useCheckout(): Checkout {
  const [pendingCode, setPendingCode] = useState<string | null>(null);
  const [redirecting, setRedirecting] = useState(false);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  // Blocks a second click before React has re-rendered the disabled buttons.
  const inFlight = useRef(false);

  // The back button can restore this page from the browser's cache mid-redirect: make it usable again.
  useEffect(() => {
    const onPageShow = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      inFlight.current = false;
      setPendingCode(null);
      setRedirecting(false);
    };
    window.addEventListener('pageshow', onPageShow);
    return () => window.removeEventListener('pageshow', onPageShow);
  }, []);

  const buy = useCallback((pkg: CreditPackage) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setError(null);
    setPendingCode(pkg.code);
    billingApi
      .checkout(pkg.code)
      .then((order) => {
        const address = checkoutAddress(order.checkoutUrl);
        if (!address) {
          throw new Error('Checkout could not be started. Try again in a moment.');
        }
        setRedirecting(true);
        window.location.assign(address);
      })
      .catch((failure: unknown) => {
        inFlight.current = false;
        setPendingCode(null);
        setError({ code: pkg.code, message: describeBillingError(failure) });
      });
  }, []);

  return { pendingCode, redirecting, error, buy };
}
