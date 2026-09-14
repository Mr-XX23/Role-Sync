import React, { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import type { Skill } from '../../../api/skillsApi';
import { CATEGORY_META } from '../skills/skillMeta';

interface SkillMenuProps {
  /** The list's id; option ids are `${id}-${index}`, for aria-activedescendant. */
  id: string;
  /** The skills that match, best first. */
  matches: Skill[];
  /** How many skills are switched on at all, to tell "none match" apart from "none are on". */
  available: number;
  query: string;
  active: number;
  onActiveChange: (index: number) => void;
  onPick: (skill: Skill) => void;
  placement: 'above' | 'below';
  /** A search box, when the menu was opened with the Skills button rather than by typing "/". */
  search?: React.ReactNode;
}

/** The skills the rep can pick for their next message. Keys are handled by whichever field has the cursor. */
export const SkillMenu: React.FC<SkillMenuProps> = ({
  id,
  matches,
  available,
  query,
  active,
  onActiveChange,
  onPick,
  placement,
  search,
}) => {
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [active, query]);

  return (
    <div
      // Without a search box the cursor stays in the message, so clicks here mustn't take focus from it.
      onMouseDown={search ? undefined : (event) => event.preventDefault()}
      className={`absolute left-0 z-30 w-[26rem] max-w-full rounded-xl border border-border bg-popover shadow-xl animate-in fade-in duration-150 ${
        placement === 'above' ? 'bottom-full mb-2' : 'top-full mt-2'
      }`}
    >
      <div className="flex items-center justify-between gap-2 px-3 pt-2.5 pb-1.5">
        <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70 truncate">
          {query.trim() && !search ? `Skills matching “${query.trim()}”` : 'Use a skill'}
        </p>
        <Link to="/salesman/skills" className="text-[11px] font-semibold text-primary hover:underline shrink-0">
          Manage skills
        </Link>
      </div>
      {search}
      {matches.length > 0 ? (
        <ul ref={listRef} id={id} role="listbox" aria-label="Skills" className="max-h-64 overflow-y-auto px-1.5 pb-1.5">
          {matches.map((skill, index) => {
            const category = CATEGORY_META[skill.category];
            const Icon = category.icon;
            return (
              <li
                key={skill.ref}
                id={`${id}-${index}`}
                data-index={index}
                role="option"
                aria-selected={index === active}
                // Keep the cursor in the search box while clicking.
                onMouseDown={(event) => event.preventDefault()}
                onMouseMove={() => index !== active && onActiveChange(index)}
                onClick={() => onPick(skill)}
                className={`flex items-start gap-2.5 rounded-lg px-2.5 py-2 cursor-pointer transition-colors ${
                  index === active ? 'bg-muted' : ''
                }`}
              >
                <span className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${category.tone}`}>
                  <Icon className="w-3.5 h-3.5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-xs font-semibold text-foreground truncate">{skill.name}</span>
                  <span className="block text-[11px] text-muted-foreground leading-snug line-clamp-2">{skill.description}</span>
                </span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="px-3 pb-3 pt-1 text-xs text-muted-foreground">
          {available === 0 ? 'No skills are switched on for your agent.' : 'No skill matches that.'}
        </p>
      )}
      <p className="border-t border-border/60 px-3 py-1.5 text-[10px] text-muted-foreground/80">
        ↑ ↓ to move · Enter to pick · Esc to close
      </p>
    </div>
  );
};
