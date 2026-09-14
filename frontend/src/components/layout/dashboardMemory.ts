export type DashboardKind = 'workspace' | 'admin';

const HOME: Record<DashboardKind, string> = { workspace: '/salesman', admin: '/admin' };
const KEY = 'rolesync_last_dashboard_paths';

function read(): Partial<Record<DashboardKind, string>> {
  try {
    return JSON.parse(sessionStorage.getItem(KEY) ?? '{}') as Partial<Record<DashboardKind, string>>;
  } catch {
    return {};
  }
}

/** Remembers the page someone was on in a dashboard, so switching back returns there. */
export function rememberDashboardPath(kind: DashboardKind, path: string): void {
  if (!path.startsWith(HOME[kind])) return;
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ ...read(), [kind]: path }));
  } catch {
    // not remembered: the switch opens the dashboard's first page
  }
}

export function lastDashboardPath(kind: DashboardKind): string {
  const path = read()[kind];
  return path && path.startsWith(HOME[kind]) ? path : HOME[kind];
}
