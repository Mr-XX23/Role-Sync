import React, { useEffect, useState } from 'react';
import { Archive, BookOpen, Copy, Download, History, Loader2, MessageSquarePlus, Pencil, RotateCcw, X } from 'lucide-react';
import { describeSkillError, skillsApi } from '../../../api/skillsApi';
import type { Skill, SkillDetail, SkillVersion } from '../../../api/skillsApi';
import { Markdown } from '../../../components/common/Markdown';
import { Switch } from '../../../components/common/Switch';
import { useToast } from '../../../context/ToastContext';
import { CATEGORY_META, SOURCE_HINT, offReason, sourceLabel, timeAgo } from './skillMeta';

interface SkillDrawerProps {
  skillRef: string;
  canManageWorkspace: boolean;
  canCreatePrivate: boolean;
  onClose: () => void;
  onChanged: (skill: Skill) => void;
  onArchived: (ref: string) => void;
  onEdit: (skill: SkillDetail) => void;
  onCopy: (skill: SkillDetail) => void;
  onTry: (skill: Skill) => void;
}

const actionClass =
  'inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-semibold text-foreground/85 hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50';

export const SkillDrawer: React.FC<SkillDrawerProps> = ({
  skillRef,
  canManageWorkspace,
  canCreatePrivate,
  onClose,
  onChanged,
  onArchived,
  onEdit,
  onCopy,
  onTry,
}) => {
  const toast = useToast();
  const notifyError = toast.error;
  const [skill, setSkill] = useState<SkillDetail | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [tab, setTab] = useState<'playbook' | 'history'>('playbook');
  const [versions, setVersions] = useState<SkillVersion[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    skillsApi
      .get(skillRef)
      .then((detail) => {
        if (active) setSkill(detail);
      })
      .catch((error) => {
        if (active) setFailed(describeSkillError(error));
      });
    return () => {
      active = false;
    };
  }, [skillRef]);

  const version = skill?.version;
  useEffect(() => {
    if (tab !== 'history' || version === undefined) return;
    let active = true;
    skillsApi
      .versions(skillRef)
      .then((rows) => {
        if (active) setVersions(rows);
      })
      .catch((error) => {
        if (active) notifyError(describeSkillError(error));
      });
    return () => {
      active = false;
    };
  }, [tab, skillRef, version, notifyError]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && !busy && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [busy, onClose]);

  const run = async (label: string, action: () => Promise<void>) => {
    setBusy(label);
    try {
      await action();
    } catch (error) {
      notifyError(describeSkillError(error));
    } finally {
      setBusy(null);
    }
  };

  const keep = (updated: Skill) => {
    setSkill((current) => current && { ...current, ...updated });
    onChanged(updated);
  };

  const canEdit = skill ? skill.editable : false;
  const isBuiltin = skill?.source === 'BUILTIN';
  const off = skill ? offReason(skill) : null;
  const category = skill ? CATEGORY_META[skill.category] : null;
  const CategoryIcon = category?.icon ?? BookOpen;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-xs animate-in fade-in duration-200" onClick={() => !busy && onClose()}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="skill-drawer-title"
        className="h-full w-full max-w-2xl bg-card border-l border-border shadow-2xl flex flex-col"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3 px-5 py-4 border-b border-border/60">
          <div className="flex items-start gap-3 min-w-0">
            <span className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${category?.tone ?? 'bg-muted'}`}>
              <CategoryIcon className="w-4 h-4" />
            </span>
            <div className="min-w-0">
              <h3 id="skill-drawer-title" className="text-base font-bold text-foreground leading-snug">
                {skill?.name ?? 'Skill'}
              </h3>
              {skill && (
                <p className="text-[11px] text-muted-foreground" title={SOURCE_HINT[skill.source]}>
                  {sourceLabel(skill)} · {category?.label} · version {skill.version}
                  {skill.updated_at && ` · changed ${timeAgo(skill.updated_at)}${skill.updated_by_me ? ' by you' : ''}`}
                </p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {failed ? (
          <p className="p-5 text-sm text-muted-foreground">{failed}</p>
        ) : !skill ? (
          <div className="p-5">
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            <div className="px-5 py-3 border-b border-border/60 space-y-3">
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                <label className="flex items-center gap-2.5 text-xs font-semibold text-foreground">
                  <Switch
                    checked={skill.enabled}
                    disabled={Boolean(busy) || !skill.workspace_enabled}
                    label="Use this skill"
                    onChange={(enabled) => void run('switch', async () => keep(await skillsApi.setEnabled(skill.ref, enabled)))}
                  />
                  Use in my agent
                </label>
                {canManageWorkspace && skill.source !== 'PRIVATE' && (
                  <label className="flex items-center gap-2.5 text-xs font-semibold text-foreground">
                    <Switch
                      checked={skill.workspace_enabled}
                      disabled={Boolean(busy)}
                      label="On for everyone in the workspace"
                      onChange={(enabled) => void run('workspace', async () => keep(await skillsApi.setWorkspaceEnabled(skill.ref, enabled)))}
                    />
                    On for everyone
                  </label>
                )}
              </div>
              {off && <p className="text-[11px] text-muted-foreground">{off}.</p>}
              <div className="flex flex-wrap gap-2">
                <button type="button" className={actionClass} disabled={!skill.enabled} onClick={() => onTry(skill)}>
                  <MessageSquarePlus className="w-3.5 h-3.5" /> Try in chat
                </button>
                {canEdit && (
                  <button type="button" className={actionClass} onClick={() => onEdit(skill)}>
                    <Pencil className="w-3.5 h-3.5" /> {isBuiltin && !skill.customized ? 'Customize' : 'Edit'}
                  </button>
                )}
                {canCreatePrivate && skill.source !== 'PRIVATE' && (
                  <button type="button" className={actionClass} onClick={() => onCopy(skill)} title="Make your own private copy to change">
                    <Copy className="w-3.5 h-3.5" /> Make my own copy
                  </button>
                )}
                <button
                  type="button"
                  className={actionClass}
                  disabled={busy === 'download'}
                  onClick={() => void run('download', () => skillsApi.download(skill))}
                >
                  <Download className="w-3.5 h-3.5" /> SKILL.md
                </button>
                {canEdit && (!isBuiltin || skill.customized) && (
                  <button
                    type="button"
                    className={`${actionClass} text-red-700 dark:text-red-300 hover:bg-red-500/10`}
                    disabled={Boolean(busy)}
                    onClick={() => {
                      const question = isBuiltin
                        ? `Reset “${skill.name}” to the built-in version? Your workspace's version is kept in the archive.`
                        : `Archive “${skill.name}”? Agents stop using it, and you can restore it from the archive.`;
                      if (!window.confirm(question)) return;
                      void run('archive', async () => {
                        await skillsApi.archive(skill.ref);
                        toast.success(isBuiltin ? `“${skill.name}” is back to the built-in version.` : `“${skill.name}” archived.`);
                        onArchived(skill.ref);
                      });
                    }}
                  >
                    {isBuiltin ? <RotateCcw className="w-3.5 h-3.5" /> : <Archive className="w-3.5 h-3.5" />}
                    {isBuiltin ? 'Reset to built-in' : 'Archive'}
                  </button>
                )}
              </div>
            </div>

            <div className="px-5 pt-3 flex gap-1.5" role="tablist" aria-label="Skill details">
              {(
                [
                  ['playbook', 'Playbook', BookOpen],
                  ['history', 'History', History],
                ] as const
              ).map(([key, label, Icon]) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={tab === key}
                  onClick={() => setTab(key)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors cursor-pointer ${
                    tab === key ? 'bg-muted border-border text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/40'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" /> {label}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4">
              {tab === 'playbook' ? (
                <div className="space-y-4">
                  <section className="rounded-xl border border-border/60 bg-muted/20 px-4 py-3 space-y-1">
                    <p className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground">When the agent uses it</p>
                    <p className="text-sm text-foreground">{skill.description}</p>
                  </section>
                  <dl className="grid grid-cols-3 gap-2 text-center">
                    {(
                      [
                        ['Chosen by the agent', skill.usage.auto],
                        ['Picked in chat', skill.usage.picked],
                        ['Given to a sub-agent', skill.usage.delegated],
                      ] as const
                    ).map(([label, count]) => (
                      <div key={label} className="rounded-xl border border-border/60 px-2 py-2">
                        <dt className="text-[10px] text-muted-foreground">{label}</dt>
                        <dd className="text-base font-bold text-foreground tabular-nums">{count}</dd>
                      </div>
                    ))}
                  </dl>
                  <p className="text-[11px] text-muted-foreground">
                    {skill.usage.total
                      ? `Used ${skill.usage.total} time${skill.usage.total === 1 ? '' : 's'} in this workspace (${skill.usage.mine} by you), last ${timeAgo(skill.usage.last_used_at)}.`
                      : 'Not used yet.'}
                  </p>
                  {skill.tools.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground">Tools it uses</p>
                      <ul className="flex flex-wrap gap-1.5">
                        {skill.tools.map((tool) => (
                          <li key={tool}>
                            <code className="rounded-md border border-border/70 bg-background px-1.5 py-0.5 font-mono text-[11px] text-foreground">{tool}</code>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <article className="rounded-xl border border-border/60 px-4 py-3 text-sm text-foreground">
                    <Markdown>{skill.instructions}</Markdown>
                  </article>
                </div>
              ) : versions === null ? (
                <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
              ) : (
                <ol className="space-y-2">
                  {versions.map((item) => (
                    <li key={item.version} className="rounded-xl border border-border/60 px-3.5 py-3 space-y-1.5">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-xs font-bold text-foreground">
                            Version {item.version}
                            {item.version === skill.version && <span className="ml-2 font-normal text-muted-foreground">current</span>}
                          </p>
                          <p className="text-[11px] text-muted-foreground">
                            {[item.note, item.edited_at && `${timeAgo(item.edited_at)}${item.edited_by_me ? ' by you' : ''}`].filter(Boolean).join(' · ')}
                          </p>
                        </div>
                        {canEdit && item.version !== skill.version && (
                          <button
                            type="button"
                            className={actionClass}
                            disabled={Boolean(busy)}
                            onClick={() =>
                              void run(`restore-${item.version}`, async () => {
                                const restored = await skillsApi.restoreVersion(skill.ref, item.version, skill.version);
                                setSkill(restored);
                                setVersions(null);
                                onChanged(restored);
                                toast.success(`Restored version ${item.version} as version ${restored.version}.`);
                              })
                            }
                          >
                            <RotateCcw className="w-3.5 h-3.5" /> Restore
                          </button>
                        )}
                      </div>
                      <details className="text-xs">
                        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                          {item.name} · {item.description.slice(0, 90)}
                          {item.description.length > 90 ? '…' : ''}
                        </summary>
                        <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-muted/40 p-3 font-mono text-[11px] text-foreground">
                          {item.instructions}
                        </pre>
                      </details>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </>
        )}
      </aside>
    </div>
  );
};
