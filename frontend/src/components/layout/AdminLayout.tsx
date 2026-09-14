import React, { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import {
  Bot,
  Building2,
  Coins,
  CreditCard,
  Cpu,
  Gauge,
  LifeBuoy,
  LineChart,
  Menu,
  MessageSquareCode,
  ReceiptText,
  ScrollText,
  ShieldCheck,
  Users,
  Wallet,
} from 'lucide-react';
import { Sidebar } from './Sidebar';
import type { SidebarItem } from './Sidebar';
import { DashboardSwitch } from './DashboardSwitch';
import { ProfileMenu } from './ProfileMenu';
import { ThemeToggle } from '../ThemeToggle';
import { rememberDashboardPath } from './dashboardMemory';

const ITEMS: SidebarItem[] = [
  { id: 'admin-overview', label: 'Overview', icon: Gauge, path: '/admin/overview' },
  { id: 'admin-users', label: 'Users', icon: Users, path: '/admin/users' },
  { id: 'admin-workspaces', label: 'Workspaces', icon: Building2, path: '/admin/workspaces' },
  { id: 'admin-billing', label: 'Billing', icon: Wallet, path: '/admin/billing' },
  { id: 'admin-credits', label: 'Credits', icon: Coins, path: '/admin/credits' },
  { id: 'admin-payments', label: 'Payments', icon: CreditCard, path: '/admin/payments' },
  { id: 'admin-support', label: 'Support Tickets', icon: LifeBuoy, path: '/admin/support' },
  { id: 'admin-agents', label: 'Agent Manager', icon: Bot, path: '/admin/agents' },
  { id: 'admin-models', label: 'Models', icon: Cpu, path: '/admin/models' },
  { id: 'admin-prompts', label: 'Prompts', icon: MessageSquareCode, path: '/admin/prompts' },
  { id: 'admin-usage', label: 'Usage & Costs', icon: LineChart, path: '/admin/usage' },
  { id: 'admin-plans', label: 'Plans', icon: ReceiptText, path: '/admin/plans' },
];

const BOTTOM: SidebarItem[] = [{ id: 'admin-audit', label: 'Audit Log', icon: ScrollText, path: '/admin/audit' }];

/** The Super Admin Console shell: platform-wide pages, not tied to any one workspace. */
export const AdminLayout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => rememberDashboardPath('admin', pathname), [pathname]);

  return (
    <div className="min-h-screen bg-background text-foreground flex overflow-hidden">
      <Sidebar
        logo={{ title: 'RoleSync', subtitle: 'Super Admin' }}
        items={ITEMS}
        bottomItems={BOTTOM}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="flex-1 flex flex-col h-screen relative overflow-hidden">
        <header className="flex justify-between items-center gap-3 px-4 md:px-8 border-b border-border bg-card h-16 shadow-2xs sticky top-0 z-40">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              aria-label="Open navigation"
              className="p-1.5 rounded-lg border border-border/80 text-muted-foreground hover:text-foreground md:hidden active:scale-95 transition-all"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full border border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300 min-w-0">
              <ShieldCheck className="w-3.5 h-3.5 shrink-0" />
              <span className="font-mono text-[10px] font-bold uppercase tracking-wider truncate">
                Super admin · changes apply to every workspace
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3 md:gap-4">
            <DashboardSwitch />
            <ThemeToggle />
            <span className="h-6 w-px bg-border/80 hidden sm:block" />
            <ProfileMenu inAdmin />
          </div>
        </header>

        <main className="flex-1 overflow-y-auto relative p-4 md:p-8 bg-background/50">
          <div className="max-w-[87rem] mx-auto w-full">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
};
