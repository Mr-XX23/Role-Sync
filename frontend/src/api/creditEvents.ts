// ============================================================================
// "Credits needed" signal. Any API answering HTTP 402 means the workspace can't start a paid
// operation: it is out of credits, or a super admin suspended its credits. The shared axios
// instance reports every 402 here; the credits provider refreshes the balance and shows a notice.
// This file imports nothing, so axiosInstance can use it without an import cycle.
// ============================================================================

export type CreditsErrorCode = 'OUT_OF_CREDITS' | 'CREDITS_SUSPENDED';

export interface CreditsRequired {
  code: CreditsErrorCode;
  message: string;
}

export const CREDITS_MESSAGES: Record<CreditsErrorCode, string> = {
  OUT_OF_CREDITS: 'Your workspace is out of credits.',
  CREDITS_SUSPENDED: 'Credits are suspended for this workspace. Contact support.',
};

type Listener = (event: CreditsRequired) => void;

const listeners = new Set<Listener>();

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Object.prototype.toString.call(value) === '[object Object]';
}

/**
 * Reads a 402 body from any service: FastAPI `{"detail": {"code", "message"}}`, Java
 * `{"code", "error"}` or a plain `{"message"}`. A 402 without a known code still means credits are needed.
 */
export function readCreditsRequired(data: unknown): CreditsRequired {
  const body = isPlainObject(data) ? data : {};
  const detail = isPlainObject(body.detail) ? body.detail : {};
  const code: CreditsErrorCode =
    (text(detail.code) ?? text(body.code)) === 'CREDITS_SUSPENDED' ? 'CREDITS_SUSPENDED' : 'OUT_OF_CREDITS';
  const message =
    text(detail.message) ?? text(body.error) ?? text(body.message) ?? text(body.detail) ?? CREDITS_MESSAGES[code];
  return { code, message };
}

/**
 * The 402 body rewritten so every existing error display can show it: they read `message`, `error`
 * or a string `detail`, and FastAPI's object `detail` would otherwise render as "[object Object]"
 * (or break a React render). Binary bodies (downloads) are left as they are.
 */
export function readableCreditsBody(data: unknown, event: CreditsRequired): unknown {
  if (data !== null && data !== undefined && typeof data !== 'string' && !isPlainObject(data)) {
    return data;
  }
  const body = isPlainObject(data) ? data : {};
  return { ...body, code: event.code, message: event.message, error: text(body.error) ?? event.message, detail: event.message };
}

/** Subscribes to 402s; returns the unsubscribe function. */
export function onCreditsRequired(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function reportCreditsRequired(event: CreditsRequired): void {
  listeners.forEach((listener) => {
    try {
      listener(event);
    } catch (error) {
      console.error('[creditEvents] A listener failed', error);
    }
  });
}
