import React, { useEffect, useId, useRef, useState } from 'react';
import {
  ArrowUp,
  FileText,
  ImageIcon,
  LayoutGrid,
  Loader2,
  Mail,
  Paperclip,
  Search,
  Sheet,
  WandSparkles,
  X,
} from 'lucide-react';
import type { Skill } from '../../../api/skillsApi';
import { matchSkills } from '../skills/skillMeta';
import type { Attachment } from './attachments';
import { ATTACHMENT_ACCEPT, MAX_ATTACHMENTS, formatBytes, toAttachment } from './attachments';
import { SkillMenu } from './SkillMenu';

export type ComposerPhase = 'idle' | 'uploading' | 'indexing' | 'sending';

/** What the rep can type in one message; the engine accepts this plus the note naming attached files. */
const MAX_MESSAGE_CHARS = 100_000;
/** Show the character count once the message gets this close to the limit. */
const COUNTER_FROM = 90_000;

/** Prompt starters for the chips under the input. `{…}` parts are for the rep to fill in. */
const QUICK_ACTIONS: { label: string; icon: React.FC<{ className?: string }>; template: string }[] = [
  {
    label: 'Research a prospect',
    icon: Search,
    template: 'Research {company}: recent news, what we have said to them before, and which of our products fit.',
  },
  {
    label: 'Draft an email',
    icon: Mail,
    template: 'Draft a short follow-up email to {name} at {company} about {topic}.',
  },
  {
    label: 'Build a quote',
    icon: FileText,
    template: 'Create a PDF quote for {company}: {items}, valid for 30 days.',
  },
];

/** Typing "/" and a few words as the whole message searches the skills. */
const SLASH_COMMAND = /^\/([^\n/]{0,60})$/;

const SUGGESTIONS = [
  'Prep me for my call with Acme: recent news, our past emails with them, and which of our products fit.',
  'Email jane@acme.com a short thank-you for today’s demo and book a 30-minute follow-up with her next Tuesday at 3pm.',
  'Create a PDF quote for Acme: 10 seats of our Pro plan with 10% off, valid for 30 days.',
  'Put together a one-page Word summary of what our knowledge base says about competing with Globex.',
  'Log a deal for Acme: 50 Pro seats at about $12,000, closing next month. Next step: send pricing to their CFO, Jane.',
];

interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  attachments: Attachment[];
  onAttachmentsChange: (attachments: Attachment[]) => void;
  onSend: () => void;
  onReject: (message: string) => void;
  /** Sending is blocked (a run is in progress or an approval is pending). */
  blocked: boolean;
  blockedReason?: string;
  phase: ComposerPhase;
  progress?: string | null;
  /** The large first-message version shows prompt starters; the docked one is compact. */
  variant: 'hero' | 'docked';
  autoFocus?: boolean;
  /** Skills switched on for the rep's agent; null while they load, or if they couldn't be. */
  skills: Skill[] | null;
  /** The skill picked for the next message, if any. */
  skill: Skill | null;
  onSkillChange: (skill: Skill | null) => void;
}

const documentIcon = (name: string) => (/\.(xlsx|csv|tsv)$/i.test(name) ? Sheet : FileText);

const PHASE_LABEL: Record<Exclude<ComposerPhase, 'idle'>, string> = {
  uploading: 'Uploading',
  indexing: 'Reading attachments',
  sending: 'Sending',
};

export const Composer: React.FC<ComposerProps> = ({
  value,
  onChange,
  attachments,
  onAttachmentsChange,
  onSend,
  onReject,
  blocked,
  blockedReason,
  phase,
  progress,
  variant,
  autoFocus = false,
  skills,
  skill,
  onSkillChange,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const moreRef = useRef<HTMLDivElement>(null);
  const skillButtonRef = useRef<HTMLButtonElement>(null);
  const skillMenuRef = useRef<HTMLDivElement>(null);
  const skillMenuId = useId();
  const [dragging, setDragging] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false); // opened with the Skills button
  const [skillSearch, setSkillSearch] = useState('');
  const [slashClosed, setSlashClosed] = useState(false); // Esc closed the menu for the "/…" being typed
  const [activeSkill, setActiveSkill] = useState(0);

  const working = phase !== 'idle';
  const disabled = blocked || working;
  const canSend = !disabled && (value.trim().length > 0 || attachments.length > 0 || skill !== null);
  const attachmentsFull = attachments.length >= MAX_ATTACHMENTS;

  const available = skills ?? [];
  const slash = !disabled && !skillsOpen && !slashClosed && available.length > 0 ? SLASH_COMMAND.exec(value) : null;
  const skillQuery = skillsOpen ? skillSearch : (slash?.[1] ?? '');
  const skillMatches = skillsOpen || slash ? matchSkills(available, skillQuery) : [];
  // Once nothing matches and the rep has typed past a single word, a message starting with "/" is just text.
  const skillMenuOpen = (skillsOpen && !disabled) || (slash !== null && (skillMatches.length > 0 || !/\s/.test(slash[1])));
  const active = Math.min(activeSkill, Math.max(skillMatches.length - 1, 0));
  const activeOptionId = skillMenuOpen && skillMatches.length > 0 ? `${skillMenuId}-${active}` : undefined;

  // Grow with the text, up to a comfortable height, then scroll.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    if (!value) {
      // Empty: let rows / min-height decide, so a not-yet-laid-out placeholder can't inflate it.
      el.style.height = '';
      return;
    }
    el.style.height = '0px';
    el.style.height = `${Math.min(el.scrollHeight, variant === 'hero' ? 260 : 200)}px`;
  }, [value, variant]);

  useEffect(() => {
    if (!moreOpen) return;
    const onDown = (event: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(event.target as Node)) setMoreOpen(false);
    };
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setMoreOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [moreOpen]);

  useEffect(() => {
    if (!skillsOpen) return;
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!skillMenuRef.current?.contains(target) && !skillButtonRef.current?.contains(target)) setSkillsOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [skillsOpen]);

  // Straight away rather than on the next frame: the search box is about to go, and keys typed in between would be lost.
  const focusMessage = () => textareaRef.current?.focus();

  const pickSkill = (picked: Skill) => {
    focusMessage();
    onSkillChange(picked);
    if (!skillsOpen) onChange(''); // the "/…" typed to find it isn't part of the message
    setSkillsOpen(false);
    setSkillSearch('');
    setActiveSkill(0);
  };

  const closeSkillMenu = () => {
    if (skillsOpen) {
      focusMessage();
      setSkillsOpen(false);
      setSkillSearch('');
    } else {
      setSlashClosed(true);
    }
    setActiveSkill(0);
  };

  /** Arrow keys, Enter or Tab, and Esc while the skill menu is open. True when the key was used. */
  const onSkillMenuKey = (event: React.KeyboardEvent): boolean => {
    if (!skillMenuOpen) return false;
    if (event.key === 'Escape') {
      event.preventDefault();
      closeSkillMenu();
      return true;
    }
    if (skillMatches.length === 0) return false;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : skillMatches.length - 1;
      setActiveSkill((active + step) % skillMatches.length);
      return true;
    }
    if ((event.key === 'Enter' && !event.shiftKey) || event.key === 'Tab') {
      event.preventDefault();
      pickSkill(skillMatches[active]);
      return true;
    }
    return false;
  };

  const addFiles = (files: FileList | File[]) => {
    const next = [...attachments];
    for (const file of Array.from(files)) {
      if (next.length >= MAX_ATTACHMENTS) {
        onReject(`You can attach up to ${MAX_ATTACHMENTS} files per message.`);
        break;
      }
      if (next.some((existing) => existing.file.name === file.name && existing.file.size === file.size)) {
        continue;
      }
      const result = toAttachment(file);
      if ('error' in result) {
        onReject(result.error);
      } else {
        next.push(result.attachment);
      }
    }
    onAttachmentsChange(next);
  };

  const removeAttachment = (id: string) => {
    onAttachmentsChange(attachments.filter((attachment) => attachment.id !== id));
  };

  const insertTemplate = (template: string) => {
    onChange(value.trim() ? `${value.trimEnd()}\n${template}` : template);
    setMoreOpen(false);
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.focus();
      // Select the first placeholder so the rep can type straight over it.
      const start = el.value.indexOf('{');
      const end = el.value.indexOf('}', start);
      if (start !== -1 && end !== -1) el.setSelectionRange(start, end + 1);
    });
  };

  const skillHint = available.length > 0 ? (variant === 'hero' ? ' Type / for skills.' : ' (/ for skills)') : '';
  const placeholder =
    blocked && blockedReason
      ? blockedReason
      : skill
        ? `Add details for ${skill.name}, or just send`
        : variant === 'hero'
          ? `What do you want to know or get done?${skillHint}`
          : `Reply or ask for something else…${skillHint}`;

  const box = (
    <div
      className={`relative rounded-2xl border bg-card shadow-lg transition-all duration-200 ${
        dragging
          ? 'border-primary ring-4 ring-primary/15'
          : 'border-border/80 focus-within:border-primary/50 focus-within:ring-4 focus-within:ring-primary/10'
      } ${disabled ? 'opacity-90' : ''}`}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        if (!disabled && event.dataTransfer.files.length) addFiles(event.dataTransfer.files);
      }}
    >
      {/* Drop overlay */}
      {dragging && (
        <div className="absolute inset-0 z-10 rounded-2xl bg-primary/5 backdrop-blur-[1px] flex items-center justify-center pointer-events-none">
          <p className="inline-flex items-center gap-2 rounded-full bg-card border border-primary/40 px-4 py-2 text-xs font-semibold text-primary shadow-md">
            <Paperclip className="w-3.5 h-3.5" /> Drop documents or images
          </p>
        </div>
      )}

      {/* Picked skill */}
      {skill && (
        <div className="px-3 pt-3">
          <span
            title={skill.description}
            className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 py-1 pl-2.5 pr-1 text-xs text-primary"
          >
            <WandSparkles className="w-3.5 h-3.5 shrink-0" />
            <span className="font-semibold truncate">{skill.name}</span>
            {working ? (
              <span className="w-1" />
            ) : (
              <button
                type="button"
                aria-label={`Don’t use ${skill.name}`}
                onClick={() => onSkillChange(null)}
                className="w-5 h-5 rounded-full hover:bg-primary/20 flex items-center justify-center transition-colors cursor-pointer shrink-0"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </span>
        </div>
      )}

      {/* Attachments */}
      {attachments.length > 0 && (
        <ul className="flex flex-wrap gap-2 px-3 pt-3">
          {attachments.map((attachment) => {
            const DocIcon = documentIcon(attachment.file.name);
            return (
              <li
                key={attachment.id}
                className="group relative flex items-center gap-2.5 rounded-xl border border-border/80 bg-background pl-1.5 pr-2 py-1.5 max-w-[16rem]"
              >
                {attachment.kind === 'image' && attachment.previewUrl ? (
                  <img
                    src={attachment.previewUrl}
                    alt=""
                    className="w-9 h-9 rounded-lg object-cover border border-border/60 shrink-0"
                  />
                ) : (
                  <span className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
                    <DocIcon className="w-4 h-4" />
                  </span>
                )}
                <span className="min-w-0 leading-tight">
                  <span className="block text-xs font-semibold text-foreground truncate">{attachment.file.name}</span>
                  <span className="block font-mono text-[10px] text-muted-foreground">
                    {attachment.kind === 'image' ? 'Image' : 'Document'} · {formatBytes(attachment.file.size)}
                  </span>
                </span>
                {!working && (
                  <button
                    type="button"
                    aria-label={`Remove ${attachment.file.name}`}
                    onClick={() => removeAttachment(attachment.id)}
                    className="ml-1 w-5 h-5 rounded-full bg-muted text-muted-foreground hover:bg-foreground hover:text-background flex items-center justify-center transition-colors cursor-pointer shrink-0"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {/* Text */}
      <textarea
        ref={textareaRef}
        value={value}
        autoFocus={autoFocus}
        rows={variant === 'hero' ? 3 : 1}
        disabled={disabled}
        placeholder={placeholder}
        maxLength={MAX_MESSAGE_CHARS}
        aria-controls={activeOptionId && !skillsOpen ? skillMenuId : undefined}
        aria-activedescendant={skillsOpen ? undefined : activeOptionId}
        onChange={(event) => {
          const next = event.target.value.slice(0, MAX_MESSAGE_CHARS);
          // A fresh "/" (or any other text) brings the menu back after Esc closed it.
          if (next === '/' || !next.startsWith('/')) setSlashClosed(false);
          setActiveSkill(0);
          onChange(next);
        }}
        onFocus={() => setSlashClosed(false)}
        onBlur={() => slash && setSlashClosed(true)}
        onKeyDown={(event) => {
          if (onSkillMenuKey(event)) return;
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            if (canSend) onSend();
          }
        }}
        onPaste={(event) => {
          const files = Array.from(event.clipboardData?.files ?? []);
          if (files.length && !disabled) {
            event.preventDefault();
            addFiles(files);
            return;
          }
          // The browser cuts a paste off at the limit; say so rather than dropping text silently.
          const field = event.currentTarget;
          const room = MAX_MESSAGE_CHARS - (field.value.length - (field.selectionEnd - field.selectionStart));
          if (event.clipboardData.getData('text').length > room) {
            onReject(`A message can be up to ${MAX_MESSAGE_CHARS.toLocaleString()} characters, so the end of what you pasted was cut off.`);
          }
        }}
        className={`block w-full resize-none bg-transparent px-4 text-sm text-foreground placeholder:text-muted-foreground/70 outline-none border-0 focus:ring-0 disabled:cursor-not-allowed leading-relaxed ${
          variant === 'hero' ? 'pt-4 pb-2 min-h-[5.5rem]' : 'pt-3.5 pb-1.5'
        }`}
      />

      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2 px-2.5 pb-2.5 pt-1">
        <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ATTACHMENT_ACCEPT}
            className="hidden"
            onChange={(event) => {
              if (event.target.files) addFiles(event.target.files);
              event.target.value = '';
            }}
          />
          <button
            type="button"
            title={attachmentsFull ? `You can attach up to ${MAX_ATTACHMENTS} files per message` : 'Attach documents or images'}
            aria-label="Attach documents or images"
            disabled={disabled || attachmentsFull}
            onClick={() => fileInputRef.current?.click()}
            className="w-9 h-9 rounded-full border border-border/80 bg-background text-muted-foreground hover:text-foreground hover:border-foreground/30 flex items-center justify-center transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 shrink-0"
          >
            <Paperclip className="w-4 h-4" />
          </button>
          {skills !== null && (
            <button
              ref={skillButtonRef}
              type="button"
              title="Pick a skill for this request (or type /)"
              aria-haspopup="listbox"
              aria-expanded={skillsOpen}
              disabled={disabled}
              onClick={() => {
                setSkillsOpen((open) => !open);
                setSkillSearch('');
                setActiveSkill(0);
              }}
              className={`h-9 rounded-full border px-3 inline-flex items-center gap-1.5 text-xs font-semibold transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 shrink-0 ${
                skillsOpen
                  ? 'border-primary/40 bg-primary/10 text-primary'
                  : 'border-border/80 bg-background text-muted-foreground hover:text-foreground hover:border-foreground/30'
              }`}
            >
              <WandSparkles className="w-4 h-4" />
              Skills
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {value.length >= COUNTER_FROM && (
            <span
              className={`font-mono text-[11px] tabular-nums ${
                value.length >= MAX_MESSAGE_CHARS ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground'
              }`}
              title={`A message can be up to ${MAX_MESSAGE_CHARS.toLocaleString()} characters`}
            >
              {value.length.toLocaleString()} / {MAX_MESSAGE_CHARS.toLocaleString()}
            </span>
          )}
          {working && (
            <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              {progress || PHASE_LABEL[phase]}…
            </span>
          )}
          {!working && attachments.length > 0 && (
            <span className="hidden sm:inline-flex items-center gap-1 text-[11px] text-muted-foreground">
              <ImageIcon className="w-3.5 h-3.5" />
              {attachments.length} of {MAX_ATTACHMENTS} attached
            </span>
          )}
          <button
            type="button"
            aria-label="Send"
            title="Send (Enter)"
            disabled={!canSend}
            onClick={onSend}
            className="w-9 h-9 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-xs hover:opacity-90 active:scale-95 transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100"
          >
            {working ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowUp className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {skillMenuOpen && (
        <div ref={skillMenuRef}>
          <SkillMenu
            id={skillMenuId}
            matches={skillMatches}
            available={available.length}
            query={skillQuery}
            active={active}
            onActiveChange={setActiveSkill}
            onPick={pickSkill}
            placement={variant === 'hero' ? 'below' : 'above'}
            search={
              skillsOpen ? (
                <div className="px-2 pb-1.5">
                  <label className="relative block">
                    <span className="sr-only">Search skills</span>
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
                    <input
                      autoFocus
                      type="text"
                      value={skillSearch}
                      placeholder="Search skills"
                      aria-controls={activeOptionId ? skillMenuId : undefined}
                      aria-activedescendant={activeOptionId}
                      onChange={(event) => {
                        setSkillSearch(event.target.value);
                        setActiveSkill(0);
                      }}
                      onKeyDown={(event) => {
                        onSkillMenuKey(event);
                      }}
                      className="w-full h-8 rounded-lg border border-border bg-background pl-8 pr-2.5 text-xs text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/10"
                    />
                  </label>
                </div>
              ) : undefined
            }
          />
        </div>
      )}
    </div>
  );

  if (variant !== 'hero') {
    return box;
  }

  const chipClass =
    'inline-flex items-center gap-1.5 rounded-full border border-border/80 bg-card px-3 py-1.5 text-xs font-semibold text-foreground/80 hover:text-foreground hover:border-foreground/30 hover:bg-muted/60 transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50';

  return (
    <div className="space-y-3">
      {box}

      {/* Prompt starters, under the input */}
      <div className="flex flex-wrap items-center justify-center gap-2">
        {QUICK_ACTIONS.map((action) => {
          const Icon = action.icon;
          return (
            <button
              key={action.label}
              type="button"
              disabled={disabled}
              onClick={() => insertTemplate(action.template)}
              className={chipClass}
            >
              <Icon className="w-3.5 h-3.5" />
              {action.label}
            </button>
          );
        })}
        <div ref={moreRef} className="relative">
          <button
            type="button"
            disabled={disabled}
            aria-expanded={moreOpen}
            onClick={() => setMoreOpen((open) => !open)}
            className={chipClass}
          >
            <LayoutGrid className="w-3.5 h-3.5" />
            More
          </button>
          {moreOpen && (
            <div className="absolute right-0 top-full mt-2 w-[22rem] max-w-[80vw] rounded-xl border border-border bg-popover shadow-xl p-1.5 z-20 animate-in fade-in duration-150">
              <p className="px-2.5 pt-1.5 pb-1 font-mono text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
                Try asking
              </p>
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => insertTemplate(suggestion)}
                  className="block w-full text-left rounded-lg px-2.5 py-2 text-xs text-foreground hover:bg-muted transition-colors cursor-pointer leading-snug"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
