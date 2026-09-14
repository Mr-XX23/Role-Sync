import React, { useState } from 'react';
import { Menu, ChevronDown, Building2, Check } from 'lucide-react';
// import { Search } from 'lucide-react'; // hidden for now (header search box)
import { useAppDispatch, useAppSelector } from '../../store';
// import { setModalOpen } from '../../store/taskSlice'; // hidden for now (Deploy Agent button)
import { rememberWorkspace, setCurrentWorkspace } from '../../store/workspaceSlice';
import { ThemeToggle } from '../ThemeToggle';
import { DashboardSwitch } from './DashboardSwitch';
import { ProfileMenu } from './ProfileMenu';

const ROLE_LABEL: Record<string, string> = { OWNER: 'Owner', ADMIN: 'Admin', MEMBER: 'Member', VIEWER: 'Viewer' };

interface HeaderProps {
  onMenuToggle: () => void;
  /** Placeholder for the header search box. The box is hidden for now, so this is currently unused. */
  searchPlaceholder?: string;
}

export const Header: React.FC<HeaderProps> = ({
  onMenuToggle,
  // searchPlaceholder = 'Search synchronization mesh...', // hidden for now (header search box)
}) => {
  const dispatch = useAppDispatch();
  const { workspaces, currentWorkspace } = useAppSelector((state) => state.workspace);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);

  return (
    <header className="flex justify-between items-center px-4 md:px-8 border-b border-border bg-card h-16 shadow-2xs sticky top-0 z-40">
      {/* Mobile Toggle & Search */}
      <div className="flex items-center gap-4 flex-1">
        <button
          onClick={onMenuToggle}
          className="p-1.5 rounded-lg border border-border/80 text-muted-foreground hover:text-foreground md:hidden active:scale-95 transition-all"
        >
          <Menu className="w-5 h-5" />
        </button>

        {/* Header search box — hidden for now (it was never wired to a search) */}
        {/*
        <div className="relative max-w-xs md:max-w-md w-full hidden sm:block">
          <input
            type="text"
            placeholder={searchPlaceholder}
            className="w-full pl-9 pr-4 py-1.5 text-xs bg-muted/65 border border-border/80 rounded-full focus:outline-none focus:border-primary/40 focus:ring-4 focus:ring-primary/5 transition-all duration-300 font-sans"
          />
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/80" />
        </div>
        */}
      </div>

      {/* Action Mesh and Operator Section */}
      <div className="flex items-center gap-3 md:gap-4">
        {/* Workspace dashboard ↔ Super Admin Console (platform super admins only) */}
        <DashboardSwitch />

        {/* Live Vector Mesh Node Status — hidden for now */}
        {/*
        <div className="hidden xl:flex items-center gap-2 px-3 py-1.5 bg-emerald-500/10 dark:bg-emerald-500/5 rounded-full border border-emerald-500/25">
          <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span>
          <span className="font-mono text-[9px] text-emerald-700 dark:text-emerald-400 font-bold uppercase tracking-wider">
            pgvector Node: ACTIVE
          </span>
        </div>
        */}

        {/* Workspace Switcher (only for people in more than one workspace) */}
        {workspaces.length > 1 && currentWorkspace && (
          <div className="relative">
            <button
              type="button"
              onClick={() => setWorkspaceOpen(!workspaceOpen)}
              aria-haspopup="menu"
              aria-expanded={workspaceOpen}
              title="Switch workspace"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-border/80 text-xs font-semibold text-foreground hover:bg-muted transition-colors cursor-pointer max-w-[12rem]"
            >
              <Building2 className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
              <span className="truncate">{currentWorkspace.name}</span>
              <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground shrink-0 transition-transform ${workspaceOpen ? 'rotate-180' : ''}`} />
            </button>
            {workspaceOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setWorkspaceOpen(false)} />
                <div role="menu" className="absolute right-0 mt-2.5 w-64 bg-card border border-border rounded-xl shadow-md p-1.5 z-50">
                  <p className="px-3 py-1.5 text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground">
                    Switch workspace
                  </p>
                  {workspaces.map((ws) => {
                    const selected = ws.workspaceId === currentWorkspace.workspaceId;
                    const suspended = ws.isActive === false;
                    return (
                      <button
                        key={ws.workspaceId}
                        type="button"
                        role="menuitemradio"
                        aria-checked={selected}
                        onClick={() => {
                          setWorkspaceOpen(false);
                          if (!selected) {
                            dispatch(setCurrentWorkspace(ws));
                            rememberWorkspace(ws.workspaceId);
                          }
                        }}
                        className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-left transition-colors cursor-pointer ${
                          selected ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                        }`}
                      >
                        <span className="flex-1 min-w-0">
                          <span className="block font-semibold truncate">{ws.name}</span>
                          <span className="block text-[10px] text-muted-foreground">
                            {suspended ? 'Suspended' : ROLE_LABEL[ws.role ?? ''] ?? 'Member'}
                            {ws.plan && !suspended ? ` · ${ws.plan.name} plan` : ''}
                          </span>
                        </span>
                        {selected && <Check className="w-3.5 h-3.5 text-primary shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        )}

        {/* Deploy Trigger — hidden for now */}
        {/*
        <button
          onClick={() => dispatch(setModalOpen(true))}
          className="hidden lg:block text-primary font-bold text-xs bg-primary/10 border border-primary/20 px-3.5 py-1.5 rounded-xl hover:bg-primary/20 active:scale-95 transition-all cursor-pointer shadow-2xs"
        >
          Deploy Agent
        </button>
        */}

        {/* Theme Mode Selector */}
        <ThemeToggle />

        {/* Separator */}
        <span className="h-6 w-px bg-border/80 hidden sm:block" />

        {/* Profile Control Grid */}
        <ProfileMenu />
      </div>
    </header>
  );
};
