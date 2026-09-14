import { Bot, FileText, Globe, Layers, Package, Plug } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { UsageCategory } from '../../api/billingApi';

/** How each usage category looks wherever credits are broken down (the label from the API wins when present). */
export const CATEGORY_META: Record<UsageCategory, { label: string; icon: LucideIcon; bar: string; iconClass: string }> = {
  AGENT: {
    label: 'AI assistant',
    icon: Bot,
    bar: 'bg-primary',
    iconClass: 'bg-primary/10 text-primary border-primary/20',
  },
  SEARCH: {
    label: 'Web and knowledge search',
    icon: Globe,
    bar: 'bg-sky-500',
    iconClass: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20',
  },
  DOCUMENTS: {
    label: 'Documents',
    icon: FileText,
    bar: 'bg-amber-500',
    iconClass: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
  },
  CONNECTORS: {
    label: 'Connected apps',
    icon: Plug,
    bar: 'bg-emerald-500',
    iconClass: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
  },
  CATALOG: {
    label: 'Catalog AI',
    icon: Package,
    bar: 'bg-violet-500',
    iconClass: 'bg-violet-500/10 text-violet-600 dark:text-violet-300 border-violet-500/20',
  },
  OTHER: {
    label: 'Other',
    icon: Layers,
    bar: 'bg-slate-400',
    iconClass: 'bg-slate-500/10 text-slate-600 dark:text-slate-300 border-slate-500/20',
  },
};

export function categoryMeta(category: string | null | undefined) {
  return CATEGORY_META[(category ?? 'OTHER') as UsageCategory] ?? CATEGORY_META.OTHER;
}
