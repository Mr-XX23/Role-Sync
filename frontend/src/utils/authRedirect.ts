// Where to send someone after they sign in, when a page sent them to sign in first (for example
// /pricing: `/signin?redirect=/pricing`). Sign-up passes through email (and phone) verification
// before the sign-in page, so the destination is also kept in this tab for a while.

const KEY = 'rolesync_redirect_after_sign_in';
const KEEP_MS = 60 * 60 * 1000;
/** Pages that would send someone straight back to signing in. */
const AUTH_PAGES = /^\/(signin|login|register|verify-email|verify-phone|forgot-password|auth\/)/i;

/** Only paths inside this app are followed, so a crafted link can't send someone to another site. */
export function safeRedirectPath(value: string | null | undefined): string | null {
  const path = value?.trim();
  if (!path || !path.startsWith('/') || path.startsWith('//') || path.startsWith('/\\') || AUTH_PAGES.test(path)) {
    return null;
  }
  return path;
}

/** The `redirect` query parameter, if it is safe to follow. */
export function redirectParam(searchParams: URLSearchParams): string | null {
  return safeRedirectPath(searchParams.get('redirect'));
}

/** Links an auth page to another one without losing where the person is headed. */
export function withRedirect(path: string, redirect: string | null): string {
  return redirect ? `${path}?redirect=${encodeURIComponent(redirect)}` : path;
}

/** Keeps (or with null, forgets) the destination while someone signs up and verifies their account. */
export function rememberRedirect(path: string | null): void {
  try {
    if (path) {
      sessionStorage.setItem(KEY, JSON.stringify({ path, at: Date.now() }));
    } else {
      sessionStorage.removeItem(KEY);
    }
  } catch {
    // storage unavailable: after sign-up they land on the dashboard instead
  }
}

export function rememberedRedirect(): string | null {
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY) ?? 'null') as { path?: unknown; at?: unknown } | null;
    if (!saved || typeof saved.at !== 'number' || Date.now() - saved.at > KEEP_MS || typeof saved.path !== 'string') {
      return null;
    }
    return safeRedirectPath(saved.path);
  } catch {
    return null;
  }
}
