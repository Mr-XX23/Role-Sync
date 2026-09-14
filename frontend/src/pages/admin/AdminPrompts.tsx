import React, { useState } from 'react';
import {
  Bot,
  ChevronDown,
  Copy,
  Eye,
  FileText,
  History,
  Megaphone,
  MessageSquareCode,
  Receipt,
  RotateCcw,
  Search,
  Send,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { adminApi, describeAdminError } from '../../api/adminApi';
import type { AgentPrompt, PromptAgent, PromptMode, PromptVersion } from '../../api/adminApi';
import { Button } from '../../components/common/Button';
import { useToast } from '../../context/ToastContext';
import {
  AdminPage,
  Badge,
  Card,
  ConfirmAction,
  ErrorBlock,
  LoadingBlock,
  Modal,
  Notice,
  RefreshButton,
  Segmented,
  inputClass,
  labelClass,
} from './components/AdminUi';
import { formatDateTime, formatNumber, timeAgo } from './adminFormat';
import { useAdminQuery } from './useAdminQuery';

const MAX_CHARS = 20000;
const REPLACE_MIN_CHARS = 50;

const AGENT_ICON: Record<PromptAgent, LucideIcon> = {
  orchestrator: Bot,
  research: Search,
  outreach: Megaphone,
  quote: Receipt,
};

interface Draft {
  base: string; // the active version this draft was started from
  mode: PromptMode;
  instructions: string;
  note: string;
}

function activeKey(prompt: AgentPrompt): string {
  return prompt.active ? `v${prompt.active.version}` : 'none';
}

function draftFrom(prompt: AgentPrompt): Draft {
  return {
    base: activeKey(prompt),
    mode: prompt.active?.mode ?? 'APPEND',
    instructions: prompt.active?.instructions ?? '',
    note: '',
  };
}

export const AdminPrompts: React.FC = () => {
  const toast = useToast();
  const prompts = useAdminQuery(() => adminApi.prompts(), 'prompts');
  const [selected, setSelected] = useState<PromptAgent>('orchestrator');
  const [drafts, setDrafts] = useState<Partial<Record<PromptAgent, Draft>>>({});
  const [showBase, setShowBase] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [confirm, setConfirm] = useState<{ kind: 'publish' } | { kind: 'restore'; version: PromptVersion } | null>(null);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);

  const list = prompts.data ?? [];
  const prompt = list.find((item) => item.agent === selected) ?? list[0];
  const stored = prompt ? drafts[prompt.agent] : undefined;
  const draft = prompt ? (stored && stored.base === activeKey(prompt) ? stored : draftFrom(prompt)) : null;
  const saved = prompt ? draftFrom(prompt) : null;
  const dirty = Boolean(draft && saved && (draft.mode !== saved.mode || draft.instructions !== saved.instructions));
  const chars = draft?.instructions.length ?? 0;
  const replaceTooShort = draft?.mode === 'REPLACE' && draft.instructions.trim().length < REPLACE_MIN_CHARS;
  const tooLong = chars > MAX_CHARS;

  const change = (update: Partial<Draft>) => {
    if (!prompt || !draft) return;
    setDrafts((current) => ({ ...current, [prompt.agent]: { ...draft, ...update } }));
  };

  const replaceEntry = (updated: AgentPrompt) => {
    prompts.update((all) => all.map((item) => (item.agent === updated.agent ? updated : item)));
    setDrafts((current) => ({ ...current, [updated.agent]: undefined }));
  };

  const publish = async () => {
    if (!prompt || !draft) return;
    setBusy(true);
    try {
      const updated = await adminApi.publishPrompt(prompt.agent, draft.mode, draft.instructions, draft.note.trim() || null);
      replaceEntry(updated);
      setConfirm(null);
      toast.success(`Version ${updated.active?.version ?? ''} of the ${prompt.title} prompt is live. New steps use it within seconds.`, 'Prompt published');
    } catch (error) {
      toast.error(describeAdminError(error), 'Couldn’t publish the prompt');
    } finally {
      setBusy(false);
    }
  };

  const restore = async (version: PromptVersion) => {
    if (!prompt) return;
    setBusy(true);
    try {
      const updated = await adminApi.restorePrompt(prompt.agent, version.version);
      replaceEntry(updated);
      setConfirm(null);
      toast.success(`Version ${version.version} is live again as version ${updated.active?.version ?? ''}.`, 'Prompt restored');
    } catch (error) {
      toast.error(describeAdminError(error), 'Couldn’t restore that version');
    } finally {
      setBusy(false);
    }
  };

  const openPreview = async () => {
    if (!prompt || !draft) return;
    setPreviewing(true);
    try {
      const result = await adminApi.previewPrompt(prompt.agent, draft.mode, draft.instructions);
      setPreview(result.system_prompt);
    } catch (error) {
      toast.error(describeAdminError(error), 'Couldn’t build the preview');
    } finally {
      setPreviewing(false);
    }
  };

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.info('Copied to the clipboard.');
    } catch {
      toast.error('Your browser blocked copying. Select the text instead.');
    }
  };

  return (
    <AdminPage
      title="Prompts"
      icon={MessageSquareCode}
      description="The instructions each agent follows. Add your own guidance on top of the built-in prompt, or replace it entirely. Every change is versioned, so you can go back at any time."
      actions={<RefreshButton onClick={prompts.reload} loading={prompts.loading} label="Refresh prompts" />}
    >
      <Notice tone="info">
        Approvals, permissions and limits are enforced by the platform itself, so a prompt can change how the agent writes and
        works, but never lets it skip an approval or use a tool it isn’t allowed to.
      </Notice>

      {prompts.error && !prompts.data ? (
        <ErrorBlock message={prompts.error} onRetry={prompts.reload} />
      ) : !prompts.data || !prompt || !draft ? (
        <LoadingBlock />
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-[18rem_1fr] gap-4 items-start">
          <nav aria-label="Agents" className="space-y-2">
            {list.map((item) => {
              const Icon = AGENT_ICON[item.agent] ?? Bot;
              const isSelected = item.agent === prompt.agent;
              const itemDraft = drafts[item.agent];
              const hasDraft =
                itemDraft &&
                itemDraft.base === activeKey(item) &&
                (itemDraft.instructions !== (item.active?.instructions ?? '') || itemDraft.mode !== (item.active?.mode ?? 'APPEND'));
              return (
                <button
                  key={item.agent}
                  type="button"
                  onClick={() => {
                    setSelected(item.agent);
                    setExpanded(null);
                  }}
                  className={`w-full text-left rounded-2xl border p-3.5 transition-all cursor-pointer flex items-start gap-3 ${
                    isSelected ? 'bg-card border-primary/40 shadow-xs' : 'bg-card/60 border-border/70 hover:bg-card hover:border-border'
                  }`}
                >
                  <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${isSelected ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground'}`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="min-w-0 space-y-1">
                    <p className="text-sm font-semibold text-foreground">{item.title}</p>
                    <p className="text-[11px] text-muted-foreground line-clamp-2">{item.description}</p>
                    <div className="flex flex-wrap items-center gap-1">
                      {item.active ? (
                        <Badge tone={item.active.mode === 'REPLACE' ? 'warning' : 'primary'}>
                          v{item.active.version} · {item.active.mode === 'REPLACE' ? 'Replaced' : 'Added to'}
                        </Badge>
                      ) : (
                        <Badge>Built-in only</Badge>
                      )}
                      {hasDraft && <Badge tone="info">Unsaved</Badge>}
                    </div>
                  </div>
                </button>
              );
            })}
          </nav>

          <div className="space-y-4 min-w-0">
            <Card
              title={`${prompt.title} instructions`}
              subtitle={
                prompt.active
                  ? `Live: version ${prompt.active.version}, published ${timeAgo(prompt.active.created_at)}${prompt.active.created_by_email ? ` by ${prompt.active.created_by_email}` : ''}`
                  : 'Only the built-in prompt is in use.'
              }
              icon={FileText}
            >
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <Segmented<PromptMode>
                    label="How your instructions are used"
                    value={draft.mode}
                    onChange={(mode) => change({ mode })}
                    options={[
                      { value: 'APPEND', label: 'Add to built-in prompt' },
                      { value: 'REPLACE', label: 'Replace built-in prompt' },
                    ]}
                  />
                  <button
                    type="button"
                    onClick={() => setShowBase(!showBase)}
                    className="text-xs font-semibold text-primary hover:underline flex items-center gap-1 cursor-pointer"
                    aria-expanded={showBase}
                  >
                    {showBase ? 'Hide' : 'Show'} the built-in prompt
                    <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showBase ? 'rotate-180' : ''}`} />
                  </button>
                </div>

                {showBase && (
                  <div className="relative rounded-xl border border-border/70 bg-muted/30">
                    <button
                      type="button"
                      onClick={() => void copy(prompt.base_prompt)}
                      className="absolute top-2 right-2 p-1.5 rounded-lg bg-card border border-border/70 text-muted-foreground hover:text-foreground cursor-pointer"
                      aria-label="Copy the built-in prompt"
                      title="Copy"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                    <pre className="max-h-80 overflow-auto p-4 pr-12 text-[11px] leading-relaxed font-mono whitespace-pre-wrap text-foreground/90">
                      {prompt.base_prompt}
                    </pre>
                  </div>
                )}

                {draft.mode === 'REPLACE' && (
                  <Notice tone="warning">
                    Replacing drops everything in the built-in prompt: how to use tools, approvals etiquette, citations and tone.
                    Start from a copy of it and change what you need. Today’s date and the rep’s time zone are still added for you.
                  </Notice>
                )}

                <div className="space-y-1">
                  <label htmlFor="prompt-instructions" className={labelClass}>
                    {draft.mode === 'APPEND' ? 'Additional instructions' : 'Full prompt'}
                  </label>
                  <textarea
                    id="prompt-instructions"
                    rows={14}
                    value={draft.instructions}
                    disabled={busy}
                    onChange={(event) => change({ instructions: event.target.value })}
                    placeholder={
                      draft.mode === 'APPEND'
                        ? 'For example: Always offer a follow-up meeting slot when a prospect replies positively. Write prices in the customer’s currency.'
                        : 'Write the complete prompt for this agent…'
                    }
                    className="w-full font-mono text-xs leading-relaxed min-h-[16rem]"
                  />
                  <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                    <span className={tooLong ? 'text-destructive' : 'text-muted-foreground'}>
                      {formatNumber(chars)} / {formatNumber(MAX_CHARS)} characters
                    </span>
                    {draft.mode === 'REPLACE' && replaceTooShort && (
                      <span className="text-destructive">A replacement prompt needs at least {REPLACE_MIN_CHARS} characters.</span>
                    )}
                    {draft.mode === 'REPLACE' && !draft.instructions.trim() && (
                      <button type="button" onClick={() => change({ instructions: prompt.base_prompt })} className="text-primary font-semibold hover:underline cursor-pointer">
                        Start from the built-in prompt
                      </button>
                    )}
                  </div>
                </div>

                <div className="space-y-1">
                  <label htmlFor="prompt-note" className={labelClass}>
                    What changed <span className="normal-case font-normal tracking-normal">(optional, shown in the history)</span>
                  </label>
                  <input
                    id="prompt-note"
                    className={inputClass}
                    maxLength={300}
                    value={draft.note}
                    disabled={busy}
                    onChange={(event) => change({ note: event.target.value })}
                    placeholder="Ask for a follow-up slot in positive replies"
                  />
                </div>

                <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
                  {dirty && (
                    <button
                      type="button"
                      onClick={() => setDrafts((current) => ({ ...current, [prompt.agent]: undefined }))}
                      disabled={busy}
                      className="px-4 py-2 text-xs font-medium rounded-xl border border-border/70 hover:bg-muted/60 text-muted-foreground hover:text-foreground cursor-pointer disabled:opacity-50"
                    >
                      Discard changes
                    </button>
                  )}
                  <Button variant="outline" className="px-4 py-2 w-auto text-xs" icon={<Eye className="w-3.5 h-3.5" />} iconPosition="left" isLoading={previewing} loadingText="Building…" disabled={tooLong || replaceTooShort} onClick={() => void openPreview()}>
                    Preview full prompt
                  </Button>
                  <Button className="px-4 py-2 w-auto text-xs" icon={<Send className="w-3.5 h-3.5" />} iconPosition="left" disabled={!dirty || tooLong || replaceTooShort || busy} onClick={() => setConfirm({ kind: 'publish' })}>
                    Publish
                  </Button>
                </div>
              </div>
            </Card>

            <Card title="Version history" subtitle="Newest first. Restoring publishes a copy as a new version." icon={History} bodyClassName="p-0">
              {prompt.versions.length === 0 ? (
                <p className="text-xs text-muted-foreground px-5 py-8 text-center">No versions yet. Publishing creates version 1.</p>
              ) : (
                <ul className="divide-y divide-border/60">
                  {prompt.versions.map((version) => {
                    const isActive = version.active ?? prompt.active?.version === version.version;
                    const open = expanded === version.version;
                    return (
                      <li key={version.version} className="px-5 py-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="font-mono text-xs font-bold text-foreground">v{version.version}</span>
                            <Badge tone={version.mode === 'REPLACE' ? 'warning' : 'primary'}>{version.mode === 'REPLACE' ? 'Replace' : 'Add'}</Badge>
                            {isActive && <Badge tone="success">Live</Badge>}
                            <span className="text-xs text-foreground truncate">{version.note || (version.instructions.trim() ? 'No note' : 'Instructions cleared')}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-[11px] text-muted-foreground" title={formatDateTime(version.created_at)}>
                              {timeAgo(version.created_at)}
                              {version.created_by_email ? ` · ${version.created_by_email}` : ''}
                            </span>
                            <button type="button" onClick={() => setExpanded(open ? null : version.version)} className="text-[11px] font-semibold text-primary hover:underline cursor-pointer" aria-expanded={open}>
                              {open ? 'Hide' : 'View'}
                            </button>
                            {!isActive && (
                              <Button variant="outline" className="px-2.5 py-1 w-auto text-[11px]" icon={<RotateCcw className="w-3 h-3" />} iconPosition="left" disabled={busy} onClick={() => setConfirm({ kind: 'restore', version })}>
                                Restore
                              </Button>
                            )}
                          </div>
                        </div>
                        {open && (
                          <pre className="mt-2 max-h-64 overflow-auto rounded-xl border border-border/70 bg-muted/30 p-3 text-[11px] font-mono whitespace-pre-wrap text-foreground/90">
                            {version.instructions || '(empty: only the built-in prompt)'}
                          </pre>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}

      {preview !== null && prompt && (
        <Modal
          title={`${prompt.title}: what the model receives`}
          subtitle="The rep’s own profile details, memory and conversation are added after this at run time."
          icon={Eye}
          width="max-w-4xl"
          onClose={() => setPreview(null)}
          footer={
            <Button variant="outline" className="px-3 py-2 w-auto text-xs" icon={<Copy className="w-3.5 h-3.5" />} iconPosition="left" onClick={() => void copy(preview)}>
              Copy
            </Button>
          }
        >
          <pre className="max-h-[65vh] overflow-auto rounded-xl border border-border/70 bg-muted/30 p-4 text-[11px] leading-relaxed font-mono whitespace-pre-wrap text-foreground/90">
            {preview}
          </pre>
        </Modal>
      )}

      {confirm?.kind === 'publish' && prompt && draft && (
        <ConfirmAction
          destructive={draft.mode === 'REPLACE'}
          title={`Publish new ${prompt.title} instructions?`}
          message={
            draft.mode === 'REPLACE' ? (
              <>Every workspace’s {prompt.title.toLowerCase()} will use your text instead of the built-in prompt from its next step.</>
            ) : draft.instructions.trim() ? (
              <>Every workspace’s {prompt.title.toLowerCase()} gets your instructions on top of the built-in prompt from its next step.</>
            ) : (
              <>This removes the additional instructions, so only the built-in prompt is used.</>
            )
          }
          confirmLabel="Publish"
          busyLabel="Publishing…"
          busy={busy}
          onConfirm={() => void publish()}
          onCancel={() => setConfirm(null)}
        />
      )}
      {confirm?.kind === 'restore' && prompt && (
        <ConfirmAction
          title={`Restore version ${confirm.version.version}?`}
          message={<>Its instructions become live again as a new version. The current version stays in the history.</>}
          confirmLabel="Restore"
          busyLabel="Restoring…"
          busy={busy}
          onConfirm={() => void restore(confirm.version)}
          onCancel={() => setConfirm(null)}
        />
      )}
    </AdminPage>
  );
};

export default AdminPrompts;
