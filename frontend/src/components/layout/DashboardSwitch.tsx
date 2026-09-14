import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Building2, ShieldCheck } from 'lucide-react';
import { useAppSelector } from '../../store';
import { lastDashboardPath } from './dashboardMemory';
import type { DashboardKind } from './dashboardMemory';

const OPTIONS: { kind: DashboardKind; label: string; short: string; icon: typeof Building2 }[] = [
  { kind: 'workspace', label: 'Workspace', short: 'Workspace', icon: Building2 },
  { kind: 'admin', label: 'Super Admin', short: 'Admin', icon: ShieldCheck },
];

/**
 * Switches between the workspace dashboard and the Super Admin Console, returning to the page last
 * open in each. Only platform super admins see it (the console's APIs check that on the server too).
 */
export const DashboardSwitch: React.FC = () => {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const isSuperAdmin = useAppSelector((state) => state.auth.user?.platformRole === 'SUPER_ADMIN');
  if (!isSuperAdmin) return null;
  const current: DashboardKind = pathname.startsWith('/admin') ? 'admin' : 'workspace';

  return (
    <div
      role="radiogroup"
      aria-label="Dashboard"
      className="flex items-center p-0.5 rounded-xl border border-border/80 bg-muted/50 shadow-2xs"
    >
      {OPTIONS.map(({ kind, label, short, icon: Icon }) => {
        const selected = current === kind;
        const adminTone = kind === 'admin';
        return (
          <button
            key={kind}
            type="button"
            role="radio"
            aria-checked={selected}
            title={kind === 'admin' ? 'Open the Super Admin Console' : 'Open your workspace'}
            onClick={() => !selected && navigate(lastDashboardPath(kind))}
            className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-[10px] text-xs font-semibold transition-all duration-200 cursor-pointer ${
              selected
                ? adminTone
                  ? 'bg-violet-600 text-white shadow-xs'
                  : 'bg-card text-foreground shadow-xs border border-border/70'
                : 'text-muted-foreground hover:text-foreground border border-transparent'
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">{label}</span>
            <span className="sm:hidden">{short}</span>
          </button>
        );
      })}
    </div>
  );
};
