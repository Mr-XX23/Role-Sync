import { Bot, Building2, KeyRound } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { AdminService } from '../../api/adminApi';

export const AUDIT_SERVICE_META: Record<AdminService, { label: string; icon: LucideIcon; iconClass: string }> = {
  auth: { label: 'Accounts', icon: KeyRound, iconClass: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20' },
  workspace: {
    label: 'Workspaces & plans',
    icon: Building2,
    iconClass: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
  },
  agent: { label: 'Sales agent', icon: Bot, iconClass: 'bg-violet-500/10 text-violet-600 dark:text-violet-300 border-violet-500/20' },
};
