import React, { useEffect, useRef, useState } from 'react';
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
  X,
} from 'lucide-react';
import type { Attachment } from './attachments';
import { ATTACHMENT_ACCEPT, MAX_ATTACHMENTS, formatBytes, toAttachment } from './attachments';

export type ComposerPhase = 'idle' | 'uploading' | 'indexing' | 'sending';

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
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const moreRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);

  const working = phase !== 'idle';
  const disabled = blocked || working;
  const canSend = !disabled && (value.trim().length > 0 || attachments.length > 0);

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

  const placeholder =
    blocked && blockedReason ? blockedReason : variant === 'hero' ? 'What do you want to know or get done?' : 'Reply or ask for something else…';

  return (
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
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
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
            title="Attach documents or images"
            aria-label="Attach documents or images"
            disabled={disabled}
            onClick={() => fileInputRef.current?.click()}
            className="w-9 h-9 rounded-full border border-border/80 bg-background text-muted-foreground hover:text-foreground hover:border-foreground/30 flex items-center justify-center transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 shrink-0"
          >
            <Paperclip className="w-4 h-4" />
          </button>

          {variant === 'hero' && (
            <>
              {QUICK_ACTIONS.map((action, index) => {
                const Icon = action.icon;
                return (
                  <button
                    key={action.label}
                    type="button"
                    disabled={disabled}
                    onClick={() => insertTemplate(action.template)}
                    className={`${index === 2 ? 'hidden md:inline-flex' : 'hidden sm:inline-flex'} items-center gap-1.5 rounded-full border border-border/80 bg-background px-3 py-1.5 text-xs font-semibold text-foreground/80 hover:text-foreground hover:border-foreground/30 hover:bg-muted/60 transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50`}
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
                  className="inline-flex items-center gap-1.5 rounded-full border border-border/80 bg-background px-3 py-1.5 text-xs font-semibold text-foreground/80 hover:text-foreground hover:border-foreground/30 hover:bg-muted/60 transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <LayoutGrid className="w-3.5 h-3.5" />
                  More
                </button>
                {moreOpen && (
                  <div className="absolute left-0 bottom-full mb-2 w-[22rem] max-w-[80vw] rounded-xl border border-border bg-popover shadow-xl p-1.5 z-20 animate-in fade-in duration-150">
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
            </>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {working && (
            <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              {progress || PHASE_LABEL[phase]}…
            </span>
          )}
          {!working && attachments.length > 0 && (
            <span className="hidden sm:inline-flex items-center gap-1 text-[11px] text-muted-foreground">
              <ImageIcon className="w-3.5 h-3.5" />
              {attachments.length} attached
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
    </div>
  );
};
