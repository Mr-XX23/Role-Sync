import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, ChevronDown, KeyRound, LogOut, Settings, ShieldCheck, User } from 'lucide-react';
import { useAppDispatch, useAppSelector } from '../../store';
import { logoutUser } from '../../store/authSlice';
import { lastDashboardPath } from './dashboardMemory';

/** The avatar menu in the top bar, shared by the workspace dashboard and the Super Admin Console. */
export const ProfileMenu: React.FC<{ inAdmin?: boolean }> = ({ inAdmin = false }) => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const { user } = useAppSelector((state) => state.auth);
  const { profile } = useAppSelector((state) => state.workspace);
  const isSuperAdmin = user?.platformRole === 'SUPER_ADMIN';
  const [open, setOpen] = useState(false);

  const go = (path: string) => {
    setOpen(false);
    navigate(path);
  };

  const item =
    'w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-all duration-150 cursor-pointer';

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="flex items-center gap-1.5 p-1 rounded-full hover:bg-muted border border-transparent hover:border-border/60 transition-all duration-200 cursor-pointer"
      >
        <div className="relative h-7 w-7 rounded-full overflow-hidden bg-primary/20 border border-primary/15 flex items-center justify-center font-bold text-xs text-primary">
          {profile?.avatarUrl ? (
            <img src={profile.avatarUrl} alt="Avatar" className="w-full h-full object-cover" />
          ) : profile && profile.firstName ? (
            (profile.firstName.slice(0, 1) + (profile.lastName ? profile.lastName.slice(0, 1) : '')).toUpperCase()
          ) : user?.email ? (
            user.email.slice(0, 2).toUpperCase()
          ) : (
            'OP'
          )}
        </div>
        <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            role="menu"
            className="absolute right-0 mt-2.5 w-60 bg-card border border-border rounded-xl shadow-md p-2 z-50 animate-in fade-in slide-in-from-top-2 duration-200"
          >
            <div className="px-3.5 py-2 border-b border-border/60 mb-1.5">
              {profile && profile.firstName ? (
                <div className="mb-1.5">
                  <p className="text-xs font-bold text-foreground truncate leading-none mb-0.5">
                    {profile.displayName || `${profile.firstName} ${profile.lastName || ''}`.trim()}
                  </p>
                  {profile.jobTitle ? (
                    <span className="text-[9px] font-mono text-muted-foreground uppercase tracking-wider leading-none">
                      {profile.jobTitle}
                    </span>
                  ) : null}
                </div>
              ) : (
                <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest leading-none mb-1">operator account</p>
              )}
              <p className="text-[11px] text-muted-foreground font-mono truncate break-all leading-none">
                {user?.email || 'operator@rolesync.ai'}
              </p>
              {isSuperAdmin && (
                <span className="inline-flex items-center gap-1 mt-2 text-[9px] font-mono font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-md border bg-violet-500/10 text-violet-700 dark:text-violet-300 border-violet-500/25">
                  <ShieldCheck className="w-3 h-3" />
                  Platform super admin
                </span>
              )}
            </div>

            <div className="space-y-0.5">
              {isSuperAdmin &&
                (inAdmin ? (
                  <button type="button" role="menuitem" onClick={() => go(lastDashboardPath('workspace'))} className={item}>
                    <Building2 className="w-4 h-4 text-muted-foreground" />
                    <span>Back to workspace</span>
                  </button>
                ) : (
                  <button type="button" role="menuitem" onClick={() => go(lastDashboardPath('admin'))} className={item}>
                    <ShieldCheck className="w-4 h-4 text-muted-foreground" />
                    <span>Super Admin Console</span>
                  </button>
                ))}
              <button type="button" role="menuitem" onClick={() => go('/salesman/profile')} className={item}>
                <User className="w-4 h-4 text-muted-foreground" />
                <span>Profile Panel</span>
              </button>
              <button type="button" role="menuitem" onClick={() => go('/salesman/settings')} className={item}>
                <Settings className="w-4 h-4 text-muted-foreground" />
                <span>System Settings</span>
              </button>
              <button type="button" role="menuitem" onClick={() => go('/change-password')} className={item}>
                <KeyRound className="w-4 h-4 text-muted-foreground" />
                <span>Change Password</span>
              </button>
            </div>

            <div className="border-t border-border/60 my-1.5 pt-1.5">
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  dispatch(logoutUser());
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold text-destructive hover:bg-destructive/10 transition-all duration-150 cursor-pointer"
              >
                <LogOut className="w-4 h-4" />
                <span>Terminate Session</span>
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
