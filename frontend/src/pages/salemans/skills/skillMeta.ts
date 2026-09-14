import { Blocks, ClipboardCheck, Handshake, SquareKanban, MessagesSquare, Radar } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { Skill, SkillCategory, SkillSource } from '../../../api/skillsApi';

export const CATEGORY_META: Record<SkillCategory, { label: string; icon: LucideIcon; tone: string }> = {
  PROSPECT: { label: 'Prospect', icon: Radar, tone: 'bg-sky-500/10 text-sky-700 dark:text-sky-300' },
  QUALIFY: { label: 'Qualify', icon: ClipboardCheck, tone: 'bg-violet-500/10 text-violet-700 dark:text-violet-300' },
  ENGAGE: { label: 'Engage', icon: MessagesSquare, tone: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' },
  CLOSE: { label: 'Close', icon: Handshake, tone: 'bg-amber-500/10 text-amber-800 dark:text-amber-300' },
  PIPELINE: { label: 'Pipeline', icon: SquareKanban, tone: 'bg-rose-500/10 text-rose-700 dark:text-rose-300' },
  OTHER: { label: 'Other', icon: Blocks, tone: 'bg-muted text-muted-foreground' },
};

export const CATEGORIES = Object.keys(CATEGORY_META) as SkillCategory[];

export function sourceLabel(skill: Pick<Skill, 'source' | 'customized'>): string {
  if (skill.source === 'BUILTIN') return skill.customized ? 'Customized' : 'Built-in';
  return skill.source === 'WORKSPACE' ? 'Workspace' : 'Only me';
}

export const SOURCE_HINT: Record<SkillSource, string> = {
  BUILTIN: 'Ships with RoleSync. Owners and admins can customize it for the workspace.',
  WORKSPACE: 'Written for everyone in the workspace by an owner or admin.',
  PRIVATE: 'Your own skill. Only your agent uses it, and nobody else can see it.',
};

/** "3 days ago", "just now": when a skill was last used or changed. */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '';
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (Number.isNaN(seconds)) return '';
  if (seconds < 60) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? '' : 's'} ago`;
  return new Date(iso).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' });
}

export function usageLine(skill: Skill): string {
  const { total, last_used_at } = skill.usage;
  if (!total) return 'Not used yet';
  return `Used ${total} time${total === 1 ? '' : 's'} · ${timeAgo(last_used_at)}`;
}

/** Why a skill is off for my agent, if it is. */
export function offReason(skill: Skill): string | null {
  if (!skill.workspace_enabled) return 'Switched off for everyone by a workspace admin';
  if (!skill.enabled) return 'Off for your agent';
  return null;
}

/** A skill id as a readable name ("discovery-call-prep" → "Discovery call prep"), where only the id is known. */
export function skillTitle(slug: string): string {
  const words = slug.replace(/-/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The skills a search matches, best first: names or ids starting with it, then ones containing it, then descriptions. */
export function matchSkills(skills: Skill[], query: string): Skill[] {
  const wanted = query.trim().toLowerCase();
  if (!wanted) return skills;
  const rank = (skill: Skill) => {
    const name = skill.name.toLowerCase();
    if (name.startsWith(wanted) || skill.slug.startsWith(wanted)) return 0;
    if (name.includes(wanted) || skill.slug.includes(wanted)) return 1;
    return skill.description.toLowerCase().includes(wanted) ? 2 : -1;
  };
  return skills
    .map((skill) => ({ skill, rank: rank(skill) }))
    .filter((entry) => entry.rank >= 0)
    .sort((a, b) => a.rank - b.rank)
    .map((entry) => entry.skill);
}
