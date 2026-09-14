import React, { useRef, useState } from 'react';
import { AlertTriangle, FileUp, X } from 'lucide-react';
import { describeSkillError, skillsApi } from '../../../api/skillsApi';
import type { SkillDraft } from '../../../api/skillsApi';
import { Button } from '../../../components/common/Button';
import { CATEGORY_META } from './skillMeta';

const MAX_BYTES = 64 * 1024;

interface ImportSkillModalProps {
  onClose: () => void;
  /** The file read into a skill, to review and save in the editor. */
  onContinue: (draft: SkillDraft) => void;
}

/** Bring in a SKILL.md file (the Anthropic Agent Skills format): upload or paste, check what came through, then edit and save. */
export const ImportSkillModal: React.FC<ImportSkillModalProps> = ({ onClose, onContinue }) => {
  const fileRef = useRef<HTMLInputElement>(null);
  const [content, setContent] = useState('');
  const [fileName, setFileName] = useState<string | null>(null);
  const [draft, setDraft] = useState<SkillDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);

  const readFile = async (file: File) => {
    setDraft(null);
    setError(null);
    if (file.size > MAX_BYTES) {
      setError('A SKILL.md file can be at most 64 KB.');
      return;
    }
    setFileName(file.name);
    setContent(await file.text());
  };

  const preview = async () => {
    setReading(true);
    setError(null);
    try {
      setDraft(await skillsApi.previewImport(content));
    } catch (failure) {
      setDraft(null);
      setError(describeSkillError(failure, 'The file couldn’t be read right now.'));
    } finally {
      setReading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs animate-in fade-in duration-200">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="skill-import-title"
        className="w-full max-w-2xl max-h-[90vh] bg-card border border-border/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col"
      >
        <header className="px-6 py-4 border-b border-border/60 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 id="skill-import-title" className="text-base font-bold text-foreground">
              Import a SKILL.md file
            </h3>
            <p className="text-xs text-muted-foreground">
              Only the file’s instructions come in; scripts or other files that came with it are never run.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          <input
            ref={fileRef}
            type="file"
            accept=".md,text/markdown,text/plain"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void readFile(file);
              event.target.value = '';
            }}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              const file = event.dataTransfer.files?.[0];
              if (file) void readFile(file);
            }}
            className="w-full rounded-xl border-2 border-dashed border-border hover:border-primary/40 hover:bg-primary/5 px-4 py-6 flex flex-col items-center gap-2 text-center transition-colors cursor-pointer"
          >
            <FileUp className="w-5 h-5 text-primary" />
            <span className="text-sm font-semibold text-foreground">{fileName ?? 'Choose or drop a SKILL.md file'}</span>
            <span className="text-[11px] text-muted-foreground">Or paste its text below.</span>
          </button>
          <textarea
            aria-label="SKILL.md text"
            rows={9}
            value={content}
            maxLength={MAX_BYTES}
            placeholder={'---\nname: renewal-call-prep\ndescription: Use when a renewal call is booked.\n---\n# Renewal call prep\n...'}
            onChange={(event) => {
              setContent(event.target.value);
              setDraft(null);
            }}
            className="w-full py-2 px-3 rounded-xl border border-border bg-background font-mono text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/10 focus:border-primary"
          />

          {error && (
            <p className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-700 dark:text-red-300" role="alert">
              {error}
            </p>
          )}

          {draft && (
            <section className="rounded-xl border border-border/70 bg-muted/20 px-4 py-3 space-y-2">
              <p className="text-sm font-bold text-foreground">{draft.name}</p>
              <p className="text-xs text-muted-foreground">{draft.description}</p>
              <p className="text-[11px] text-muted-foreground">
                {CATEGORY_META[draft.category].label} · {draft.instructions.length.toLocaleString()} characters of instructions ·{' '}
                {draft.tools.length ? `tools: ${draft.tools.join(', ')}` : 'no tools listed'}
              </p>
              {draft.warnings.map((warning) => (
                <p key={warning} className="flex items-start gap-2 text-xs text-amber-900 dark:text-amber-200">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  {warning}
                </p>
              ))}
            </section>
          )}
        </div>

        <footer className="px-6 py-3 border-t border-border/60 bg-muted/20 flex items-center justify-end gap-2">
          <Button variant="outline" className="px-3.5 py-2 text-xs" onClick={onClose}>
            Cancel
          </Button>
          {draft ? (
            <Button className="px-4 py-2 text-xs w-auto" onClick={() => onContinue(draft)}>
              Review and save
            </Button>
          ) : (
            <Button className="px-4 py-2 text-xs w-auto" disabled={!content.trim()} isLoading={reading} loadingText="Reading" onClick={() => void preview()}>
              Read file
            </Button>
          )}
        </footer>
      </div>
    </div>
  );
};
