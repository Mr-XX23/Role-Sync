import React from 'react';
import { Lock, MessageSquarePlus, Users } from 'lucide-react';
import type { Skill } from '../../../api/skillsApi';
import { Switch } from '../../../components/common/Switch';
import { CATEGORY_META, offReason, sourceLabel, usageLine } from './skillMeta';

interface SkillCardProps {
  skill: Skill;
  busy: boolean;
  onOpen: () => void;
  onToggle: (enabled: boolean) => void;
  onTry: () => void;
}

export const SkillCard: React.FC<SkillCardProps> = ({ skill, busy, onOpen, onToggle, onTry }) => {
  const category = CATEGORY_META[skill.category];
  const Icon = category.icon;
  const off = offReason(skill);
  const SourceIcon = skill.source === 'PRIVATE' ? Lock : skill.source === 'WORKSPACE' ? Users : null;

  return (
    <article
      className={`group relative flex flex-col gap-3 rounded-2xl border bg-card p-4 shadow-2xs transition-all hover:shadow-xs ${
        skill.enabled ? 'border-border/70 hover:border-primary/40' : 'border-border/50 opacity-80'
      }`}
    >
      <div className="flex items-start gap-3">
        <span className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${category.tone}`}>
          <Icon className="w-4 h-4" />
        </span>
        <button type="button" onClick={onOpen} className="min-w-0 flex-1 text-left cursor-pointer">
          <h3 className="text-sm font-bold text-foreground leading-snug line-clamp-2 group-hover:text-primary transition-colors">
            {skill.name}
          </h3>
          <p className="mt-0.5 flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
            {SourceIcon && <SourceIcon className="w-3 h-3" />}
            {sourceLabel(skill)} · {category.label}
          </p>
        </button>
        <Switch
          checked={skill.enabled}
          disabled={busy || !skill.workspace_enabled}
          onChange={onToggle}
          label={`Use ${skill.name}`}
          title={off ?? 'On for your agent'}
        />
      </div>

      <button type="button" onClick={onOpen} className="text-left cursor-pointer">
        <p className="text-xs text-muted-foreground leading-relaxed line-clamp-3">{skill.description}</p>
      </button>

      {skill.apps.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Apps this skill uses">
          {skill.apps.map((app) => (
            <li key={app} className="rounded-md border border-border/70 bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {app}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-auto flex items-center justify-between gap-2 pt-2.5 border-t border-border/50">
        <span className="text-[11px] text-muted-foreground truncate" title={off ?? undefined}>
          {off && !skill.workspace_enabled ? off : usageLine(skill)}
        </span>
        <button
          type="button"
          onClick={onTry}
          disabled={!skill.enabled}
          title={skill.enabled ? 'Open the agent with this skill picked' : 'Switch it on to use it'}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-semibold text-primary hover:bg-primary/10 transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-40 shrink-0"
        >
          <MessageSquarePlus className="w-3.5 h-3.5" />
          Try in chat
        </button>
      </div>
    </article>
  );
};
