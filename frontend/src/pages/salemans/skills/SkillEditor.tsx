import React, { useMemo, useState } from 'react';
import { AlertTriangle, Code, Eye, Loader2, Lock, Search, Users, WandSparkles, X } from 'lucide-react';
import { describeSkillError, skillsApi } from '../../../api/skillsApi';
import type { SkillCategory, SkillDetail, SkillDraft, SkillFields, SkillTool, SkillVisibility } from '../../../api/skillsApi';
import { Button } from '../../../components/common/Button';
import { Markdown } from '../../../components/common/Markdown';
import { CATEGORIES, CATEGORY_META } from './skillMeta';

/** Kept in sync with app/skills/model.py. */
const LIMITS = { name: [3, 80], description: [10, 240], instructions: [50, 12_000] } as const;
const MAX_TOOLS = 20;

export type EditorTarget =
  | { kind: 'create'; draft?: SkillDraft; note?: string }
  | { kind: 'edit'; skill: SkillDetail };

interface SkillEditorProps {
  target: EditorTarget;
  tools: SkillTool[];
  canManageWorkspace: boolean;
  onClose: () => void;
  onSaved: (skill: SkillDetail) => void;
}

const control =
  'w-full py-2 px-3 rounded-xl border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/10 focus:border-primary disabled:opacity-70 disabled:cursor-not-allowed';

const Label: React.FC<{ htmlFor: string; children: React.ReactNode; hint?: React.ReactNode }> = ({ htmlFor, children, hint }) => (
  <div className="flex items-baseline justify-between gap-2">
    <label htmlFor={htmlFor} className="block text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground">
      {children}
    </label>
    {hint && <span className="text-[10px] font-mono text-muted-foreground tabular-nums">{hint}</span>}
  </div>
);

function initialFields(target: EditorTarget): SkillFields {
  if (target.kind === 'edit') {
    const { name, description, instructions, category, tools } = target.skill;
    return { name, description, instructions, category, tools };
  }
  if (target.draft) {
    const { name, description, instructions, category, tools } = target.draft;
    return { name, description, instructions, category, tools };
  }
  return { name: '', description: '', instructions: '# \n\nGoal: \n\n## Steps\n1. \n\n## Output\n- ', category: 'OTHER', tools: [] };
}

function problemWith(fields: SkillFields): string | null {
  const checks: [keyof typeof LIMITS, string][] = [
    ['name', 'The name'],
    ['description', '“When to use it”'],
    ['instructions', 'The instructions'],
  ];
  for (const [key, label] of checks) {
    const length = fields[key].trim().length;
    const [low, high] = LIMITS[key];
    if (length < low) return `${label} needs at least ${low} characters.`;
    if (length > high) return `${label} can be at most ${high.toLocaleString()} characters.`;
  }
  return null;
}

export const SkillEditor: React.FC<SkillEditorProps> = ({ target, tools, canManageWorkspace, onClose, onSaved }) => {
  const [fields, setFields] = useState<SkillFields>(() => initialFields(target));
  const [visibility, setVisibility] = useState<SkillVisibility>('PRIVATE');
  const [tab, setTab] = useState<'write' | 'preview'>('write');
  const [toolQuery, setToolQuery] = useState('');
  // Tools picked when the editor opened (or a draft arrived) are listed first; ticking more doesn't reorder the list.
  const [toolsFirst, setToolsFirst] = useState<ReadonlySet<string>>(() => new Set(initialFields(target).tools));
  const [idea, setIdea] = useState('');
  const [drafting, setDrafting] = useState(false);
  const [warnings, setWarnings] = useState<string[]>(target.kind === 'create' ? (target.draft?.warnings ?? []) : []);
  const [drafted, setDrafted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const editing = target.kind === 'edit' ? target.skill : null;
  const customizing = editing?.source === 'BUILTIN' && !editing.customized;
  const problem = problemWith(fields);
  const set = <K extends keyof SkillFields>(key: K, value: SkillFields[K]) => setFields((current) => ({ ...current, [key]: value }));

  const shownTools = useMemo(() => {
    const needle = toolQuery.trim().toLowerCase();
    return tools
      .filter((tool) => !needle || `${tool.name} ${tool.description} ${tool.app ?? ''}`.toLowerCase().includes(needle))
      .sort((a, b) => Number(toolsFirst.has(b.name)) - Number(toolsFirst.has(a.name)));
  }, [tools, toolQuery, toolsFirst]);

  const toggleTool = (name: string) =>
    set('tools', fields.tools.includes(name) ? fields.tools.filter((tool) => tool !== name) : [...fields.tools, name].slice(0, MAX_TOOLS));

  const draftWithAi = async () => {
    setDrafting(true);
    setError(null);
    try {
      const draft = await skillsApi.draft(idea.trim());
      setFields({ name: draft.name, description: draft.description, instructions: draft.instructions, category: draft.category, tools: draft.tools });
      setToolsFirst(new Set(draft.tools));
      setWarnings(draft.warnings);
      setDrafted(true);
      setTab('preview');
    } catch (failure) {
      setError(describeSkillError(failure, 'The draft couldn’t be written right now. Try again, or write the skill yourself.'));
    } finally {
      setDrafting(false);
    }
  };

  const save = async () => {
    if (problem) return;
    setSaving(true);
    setError(null);
    const clean: SkillFields = { ...fields, name: fields.name.trim(), description: fields.description.trim(), instructions: fields.instructions.trim() };
    try {
      const saved = editing
        ? await skillsApi.update(editing.ref, clean, editing.version)
        : await skillsApi.create({
            ...clean,
            visibility,
            note: target.kind === 'create' ? (target.note ?? (drafted ? 'Drafted with AI' : undefined)) : undefined,
          });
      onSaved(saved);
    } catch (failure) {
      setError(describeSkillError(failure, 'The skill couldn’t be saved right now.'));
      setSaving(false);
    }
  };

  const title = editing ? (customizing ? `Customize “${editing.name}”` : `Edit “${editing.name}”`) : 'New skill';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs animate-in fade-in duration-200">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="skill-editor-title"
        className="relative w-full max-w-5xl max-h-[92vh] bg-card border border-border/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col"
      >
        <header className="px-6 py-4 border-b border-border/60 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 id="skill-editor-title" className="text-base font-bold text-foreground truncate">
              {title}
            </h3>
            <p className="text-xs text-muted-foreground truncate">
              {customizing
                ? 'Saving makes a workspace version of this built-in skill. You can reset it to the built-in version at any time.'
                : 'A playbook the agent follows for one job: when to use it, the steps, and what a good result looks like.'}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            aria-label="Close"
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors disabled:opacity-30 cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-6 grid grid-cols-1 lg:grid-cols-[1fr_17rem] gap-6">
          <div className="space-y-4 min-w-0">
            {!editing && (
              <div className="rounded-xl border border-primary/25 bg-primary/5 p-3 space-y-2">
                <Label htmlFor="skill-idea">Draft with AI</Label>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    id="skill-idea"
                    className={control}
                    value={idea}
                    maxLength={500}
                    placeholder="e.g. Prepare me for renewal calls with customers whose contracts end this quarter"
                    onChange={(event) => setIdea(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && idea.trim().length >= 10 && !drafting) void draftWithAi();
                    }}
                  />
                  <Button
                    variant="outline"
                    className="px-3 py-2 text-xs w-auto shrink-0"
                    disabled={idea.trim().length < 10}
                    isLoading={drafting}
                    loadingText="Drafting"
                    onClick={() => void draftWithAi()}
                    icon={<WandSparkles className="w-3.5 h-3.5" />}
                    iconPosition="left"
                  >
                    Draft
                  </Button>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  {drafted ? 'Drafted. Read it through and change anything before saving.' : 'Describe the job in a sentence and the agent writes a first version for you to edit.'}
                </p>
              </div>
            )}

            {warnings.length > 0 && (
              <div className="rounded-xl border border-amber-500/35 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-200">
                {warnings.map((warning) => (
                  <p key={warning} className="flex items-start gap-2">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                    {warning}
                  </p>
                ))}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-[1fr_11rem] gap-3">
              <div className="space-y-1">
                <Label htmlFor="skill-name" hint={`${fields.name.trim().length}/${LIMITS.name[1]}`}>
                  Name
                </Label>
                <input
                  id="skill-name"
                  className={control}
                  value={fields.name}
                  maxLength={LIMITS.name[1]}
                  placeholder="Renewal call prep"
                  onChange={(event) => set('name', event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="skill-category">Category</Label>
                <select id="skill-category" className={control} value={fields.category} onChange={(event) => set('category', event.target.value as SkillCategory)}>
                  {CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {CATEGORY_META[category].label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="space-y-1">
              <Label htmlFor="skill-description" hint={`${fields.description.trim().length}/${LIMITS.description[1]}`}>
                When should the agent use it?
              </Label>
              <textarea
                id="skill-description"
                rows={2}
                className={`${control} resize-none`}
                value={fields.description}
                maxLength={LIMITS.description[1]}
                placeholder="Use when a customer's renewal is due in the next 60 days and the rep wants to prepare for the call."
                onChange={(event) => set('description', event.target.value)}
              />
              <p className="text-[11px] text-muted-foreground">The agent reads this line to decide when the skill fits a request.</p>
            </div>

            <div className="space-y-1">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="skill-instructions" hint={`${fields.instructions.trim().length.toLocaleString()}/${LIMITS.instructions[1].toLocaleString()}`}>
                  Instructions
                </Label>
                <div className="flex items-center gap-1" role="tablist" aria-label="Instructions view">
                  {(['write', 'preview'] as const).map((view) => (
                    <button
                      key={view}
                      type="button"
                      role="tab"
                      aria-selected={tab === view}
                      onClick={() => setTab(view)}
                      className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-semibold transition-colors cursor-pointer ${
                        tab === view ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {view === 'write' ? <Code className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                      {view === 'write' ? 'Write' : 'Preview'}
                    </button>
                  ))}
                </div>
              </div>
              {tab === 'write' ? (
                <textarea
                  id="skill-instructions"
                  rows={16}
                  className={`${control} font-mono text-xs leading-relaxed resize-y min-h-[18rem]`}
                  value={fields.instructions}
                  maxLength={LIMITS.instructions[1]}
                  onChange={(event) => set('instructions', event.target.value)}
                />
              ) : (
                <div className="min-h-[18rem] max-h-[28rem] overflow-y-auto rounded-xl border border-border bg-background px-4 py-3 text-sm text-foreground">
                  {fields.instructions.trim() ? <Markdown>{fields.instructions}</Markdown> : <p className="text-muted-foreground text-xs">Nothing written yet.</p>}
                </div>
              )}
              <p className="text-[11px] text-muted-foreground">
                Markdown. Name tools in backticks, like <code className="font-mono">`search_deals`</code>. Actions the steps mention
                still wait for approval.
              </p>
            </div>
          </div>

          <aside className="space-y-4 min-w-0">
            {!editing && (
              <fieldset className="space-y-1.5">
                <legend className="block text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground mb-1">Who uses it</legend>
                {(
                  [
                    ['PRIVATE', 'Only me', 'Only your agent uses it; nobody else sees it.', Lock],
                    ['WORKSPACE', 'Everyone in the workspace', canManageWorkspace ? 'Every member’s agent can use it.' : 'Only owners and admins can share skills.', Users],
                  ] as const
                ).map(([value, label, hint, Icon]) => {
                  const unavailable = value === 'WORKSPACE' && !canManageWorkspace;
                  return (
                    <label
                      key={value}
                      className={`flex items-start gap-2.5 rounded-xl border px-3 py-2 transition-colors ${
                        visibility === value ? 'border-primary/50 bg-primary/5' : 'border-border'
                      } ${unavailable ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer hover:bg-muted/40'}`}
                    >
                      <input
                        type="radio"
                        name="skill-visibility"
                        value={value}
                        checked={visibility === value}
                        disabled={unavailable}
                        onChange={() => setVisibility(value)}
                        className="mt-1 accent-primary"
                      />
                      <span className="min-w-0">
                        <span className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                          <Icon className="w-3.5 h-3.5" /> {label}
                        </span>
                        <span className="block text-[11px] text-muted-foreground">{hint}</span>
                      </span>
                    </label>
                  );
                })}
              </fieldset>
            )}

            <div className="space-y-1.5">
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground">Tools it uses</p>
                <span className="text-[10px] font-mono text-muted-foreground">{fields.tools.length} picked</span>
              </div>
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/70" />
                <input
                  value={toolQuery}
                  onChange={(event) => setToolQuery(event.target.value)}
                  placeholder="Find a tool"
                  aria-label="Find a tool"
                  className="w-full pl-8 pr-2 py-1.5 rounded-lg border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/10 focus:border-primary"
                />
              </div>
              <ul className="max-h-[22rem] overflow-y-auto rounded-xl border border-border divide-y divide-border/60">
                {shownTools.map((tool) => (
                  <li key={tool.name}>
                    <label className="flex items-start gap-2 px-2.5 py-2 cursor-pointer hover:bg-muted/40">
                      <input
                        type="checkbox"
                        className="mt-0.5 accent-primary"
                        checked={fields.tools.includes(tool.name)}
                        onChange={() => toggleTool(tool.name)}
                      />
                      <span className="min-w-0">
                        <span className="flex items-center gap-1.5">
                          <code className="font-mono text-[11px] text-foreground">{tool.name}</code>
                          {tool.app && <span className="rounded bg-muted px-1 text-[9px] text-muted-foreground">{tool.app}</span>}
                        </span>
                        <span className="block text-[10px] text-muted-foreground leading-snug line-clamp-2">{tool.description}</span>
                      </span>
                    </label>
                  </li>
                ))}
                {shownTools.length === 0 && <li className="px-2.5 py-2 text-[11px] text-muted-foreground">No tools match.</li>}
              </ul>
              <p className="text-[11px] text-muted-foreground">Listing tools shows reps which apps a skill needs. The agent can still only use its own tools.</p>
            </div>
          </aside>
        </div>

        <footer className="px-6 py-3 border-t border-border/60 bg-muted/20 flex flex-wrap items-center justify-between gap-3">
          <p className={`text-xs ${error ? 'text-red-700 dark:text-red-300' : 'text-muted-foreground'}`} role={error ? 'alert' : undefined}>
            {error ??
              problem ??
              (customizing
                ? 'Everyone in the workspace gets your version.'
                : editing
                  ? `Saving creates version ${editing.version + 1}.`
                  : 'Saved skills are on for your agent right away.')}
          </p>
          <div className="flex items-center gap-2">
            <Button variant="outline" className="px-3.5 py-2 text-xs" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button className="px-4 py-2 text-xs w-auto" disabled={Boolean(problem) || drafting} isLoading={saving} loadingText="Saving" onClick={() => void save()}>
              {editing ? 'Save' : 'Create skill'}
            </Button>
          </div>
        </footer>
        {drafting && (
          <div className="absolute inset-0 bg-card/40 flex items-center justify-center pointer-events-none">
            <Loader2 className="w-5 h-5 animate-spin text-primary" />
          </div>
        )}
      </div>
    </div>
  );
};
