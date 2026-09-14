import { createContext, useContext } from 'react';
import type { CreditBalance } from '../api/billingApi';
import type { CreditsErrorCode } from '../api/creditEvents';

/** Why the last paid operation was refused (an HTTP 402), for the notice under the top bar. */
export interface CreditsNotice {
  id: number;
  workspaceId: string;
  code: CreditsErrorCode;
  message: string;
}

export interface CreditsState {
  /** The workspace the balance belongs to; null while none is active. */
  workspaceId: string | null;
  /** The active workspace's balance; null until it loads, or when it can't be loaded. */
  credits: CreditBalance | null;
  /** No answer yet for the active workspace. */
  loading: boolean;
  error: string | null;
  errorStatus: number | null;
  /** Loads the balance again now (after a purchase, for example). */
  refresh: () => void;
  notice: CreditsNotice | null;
  dismissNotice: () => void;
}

const nothing = () => undefined;

export const CreditsContext = createContext<CreditsState>({
  workspaceId: null,
  credits: null,
  loading: false,
  error: null,
  errorStatus: null,
  refresh: nothing,
  notice: null,
  dismissNotice: nothing,
});

/** The active workspace's credits. Outside a CreditsProvider there is simply no balance. */
export function useCredits(): CreditsState {
  return useContext(CreditsContext);
}
