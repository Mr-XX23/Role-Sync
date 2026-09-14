import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Archive, ArchiveRestore, FileUp, Loader2, Plus, RefreshCw, Search, Sparkles, X } from 'lucide-react';
import { describeSkillError, skillsApi } from '../../../api/skillsApi';
import type { ArchivedSkill, Skill, SkillCategory, SkillDetail, SkillList, SkillTool } from '../../../api/skillsApi';
import { Button } from '../../../components/common/Button';
import { InfoTooltip } from '../../../components/common/InfoTooltip';
import { useToast } from '../../../context/ToastContext';
import { useAppSelector } from '../../../store';
import { ImportSkillModal } from './ImportSkillModal';
import { SkillCard } from './SkillCard';
import { SkillDrawer } from './SkillDrawer';
import type { EditorTarget } from './SkillEditor';
import { SkillEditor } from './SkillEditor';
import { CATEGORIES, CATEGORY_META, timeAgo } from './skillMeta';

type SourceFilter = 'all' | 'builtin' | 'workspace' | 'mine' | 'off';

const SOURCE_FILTERS: { key: SourceFilter; label: string; matches: (skill: Skill) => boolean }[] = [
  { key: 'all', label: 'All', matches: () => true },
  { key: 'builtin', label: 'Built-in', matches: (skill) => skill.source === 'BUILTIN' },
  { key: 'workspace', label: 'Workspace', matches: (skill) => skill.source === 'WORKSPACE' },
  { key: 'mine', label: 'Only me', matches: (skill) => skill.source === 'PRIVATE' },
  { key: 'off', label: 'Switched off', matches: (skill) => !skill.enabled },
];

interface Loaded {
  key: string;
  list: SkillList | null;
  tools: SkillTool[];
  error: string | null;
}

const pill = (active: boolean) =>
  `inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-colors cursor-pointer whitespace-nowrap ${
    active ? 'bg-primary/10 border-primary/40 text-primary' : 'border-border text-muted-foreground hover:text-foreground hover:bg-muted/50'
  }`;

export const Skills: React.FC = () => {
  const toast = useToast();
  const navigate = useNavigate();
  const workspaceId = useAppSelector((state) => state.workspace.currentWorkspace?.workspaceId);
  const [refreshes, setRefreshes] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [query, setQuery] = useState('');
  const [source, setSource] = useState<SourceFilter>('all');
  const [category, setCategory] = useState<SkillCategory | null>(null);
  const [switching, setSwitching] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditorTarget | null>(null);
  const [importing, setImporting] = useState(false);
  const [archived, setArchived] = useState<ArchivedSkill[] | null>(null);
  const [saves, setSaves] = useState(0); // reopens the drawer on a saved skill, whose ref may not change
  const [searchParams, setSearchParams] = useSearchParams();

  const requestKey = `${workspaceId}:${refreshes}`;
  useEffect(() => {
    let active = true;
    Promise.all([skillsApi.list(), skillsApi.tools()])
      .then(([list, tools]) => {
        if (active) setLoaded({ key: requestKey, list, tools, error: null });
      })
      .catch((error) => {
        if (active) setLoaded({ key: requestKey, list: null, tools: [], error: describeSkillError(error) });
      });
    return () => {
      active = false;
    };
  }, [requestKey]);

  const loading = loaded?.key !== requestKey;
  const list = loaded?.list ?? null;
  const skills = useMemo(() => list?.skills ?? [], [list]);
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filter = SOURCE_FILTERS.find((item) => item.key === source) ?? SOURCE_FILTERS[0];
    return skills.filter(
      (skill) =>
        filter.matches(skill) &&
        (!category || skill.category === category) &&
        (!needle || `${skill.name} ${skill.description} ${skill.tools.join(' ')}`.toLowerCase().includes(needle))
    );
  }, [skills, query, source, category]);

  const openRef = searchParams.get('skill');
  const openSkill = (ref: string) => setSearchParams({ skill: ref });
  const closeSkill = () =>
    setSearchParams((params) => {
      const next = new URLSearchParams(params);
      next.delete('skill');
      return next;
    });

  const replace = (updated: Skill) =>
    setLoaded((state) => {
      if (!state?.list) return state;
      const skillsNow = state.list.skills.map((skill) => (skill.ref === updated.ref ? { ...skill, ...updated } : skill));
      const exists = skillsNow.some((skill) => skill.ref === updated.ref);
      const next = exists ? skillsNow : [...skillsNow, updated];
      return { ...state, list: { ...state.list, skills: next, limits: { ...state.list.limits, enabled: next.filter((skill) => skill.enabled).length } } };
    });

  const toggle = async (skill: Skill, enabled: boolean) => {
    setSwitching(skill.ref);
    replace({ ...skill, enabled, my_switch: enabled });
    try {
      replace(await skillsApi.setEnabled(skill.ref, enabled));
    } catch (error) {
      replace(skill);
      toast.error(describeSkillError(error));
    } finally {
      setSwitching(null);
    }
  };

  const tryInChat = (skill: Pick<Skill, 'ref'>) => navigate(`/salesman/sales-agent?skill=${encodeURIComponent(skill.ref)}`);

  const saved = (skill: SkillDetail) => {
    setEditor(null);
    setRefreshes((count) => count + 1);
    setSaves((count) => count + 1);
    toast.success(`“${skill.name}” saved.`);
    openSkill(skill.ref);
  };

  const showArchived = async () => {
    try {
      setArchived(await skillsApi.archived());
    } catch (error) {
      toast.error(describeSkillError(error));
    }
  };

  const restore = async (item: ArchivedSkill) => {
    try {
      const skill = await skillsApi.restoreArchived(item.id);
      setArchived((rows) => rows && rows.filter((row) => row.id !== item.id));
      setRefreshes((count) => count + 1);
      toast.success(`“${skill.name}” restored.`);
    } catch (error) {
      toast.error(describeSkillError(error));
    }
  };

  const copyOf = (skill: SkillDetail): EditorTarget => ({
    kind: 'create',
    draft: {
      name: `${skill.name} (my version)`.slice(0, 80),
      description: skill.description,
      instructions: skill.instructions,
      category: skill.category,
      tools: skill.tools.filter((tool) => (loaded?.tools ?? []).some((known) => known.name === tool)),
      warnings: [],
    },
    note: `Copied from “${skill.name}” (version ${skill.version})`,
  });

  return (
    <div className="h-full flex flex-col gap-6 pb-4 animate-in fade-in duration-500">
      <section className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <h2 className="font-serif text-3xl font-bold text-primary">Agent Skills</h2>
            <InfoTooltip label="About skills">
              A skill is a playbook the sales agent follows for one job, such as preparing a discovery call or handling an
              objection. The agent picks the right one for your request, or you can pick one in the chat with /. Skills guide how
              the agent works; they never let it skip your approval.
            </InfoTooltip>
          </div>
          {list && (
            <p className="text-xs text-muted-foreground">
              {list.limits.enabled} of {list.limits.max_enabled} switched on for your agent
            </p>
          )}
        </div>
        {list?.can_create_private && (
          <div className="flex items-center gap-2">
            <Button variant="outline" className="px-3.5 py-2.5 text-xs w-auto" onClick={() => setImporting(true)} icon={<FileUp className="w-4 h-4" />} iconPosition="left">
              Import SKILL.md
            </Button>
            <Button className="px-4 py-2.5 w-auto text-xs" onClick={() => setEditor({ kind: 'create' })} icon={<Plus className="w-4 h-4" />}>
              New skill
            </Button>
          </div>
        )}
      </section>

      <div className="flex flex-col gap-3">
        <div className="flex flex-col lg:flex-row lg:items-center gap-2">
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/70" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search skills…"
              aria-label="Search skills"
              className="w-full pl-9 pr-3 py-2 rounded-xl border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/10 focus:border-primary"
            />
          </div>
          <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5" role="group" aria-label="Which skills">
            {SOURCE_FILTERS.map((filter) => (
              <button key={filter.key} type="button" aria-pressed={source === filter.key} onClick={() => setSource(filter.key)} className={pill(source === filter.key)}>
                {filter.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5 lg:ml-auto">
            <button type="button" onClick={() => void showArchived()} className={pill(false)}>
              <Archive className="w-3.5 h-3.5" /> Archived
            </button>
            <button
              type="button"
              onClick={() => setRefreshes((count) => count + 1)}
              disabled={loading}
              title="Refresh"
              aria-label="Refresh skills"
              className="p-2 rounded-xl border border-border text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors cursor-pointer disabled:cursor-default"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
        <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5" role="group" aria-label="Category">
          <button type="button" aria-pressed={category === null} onClick={() => setCategory(null)} className={pill(category === null)}>
            Every category
          </button>
          {CATEGORIES.map((key) => {
            const Icon = CATEGORY_META[key].icon;
            return (
              <button key={key} type="button" aria-pressed={category === key} onClick={() => setCategory(category === key ? null : key)} className={pill(category === key)}>
                <Icon className="w-3.5 h-3.5" /> {CATEGORY_META[key].label}
              </button>
            );
          })}
        </div>
      </div>

      {!loaded ? (
        <div className="flex-1 flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      ) : loaded.error ? (
        <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-5 py-4 text-sm text-red-700 dark:text-red-300 flex items-center justify-between gap-3">
          <span>{loaded.error}</span>
          <Button variant="outline" className="px-3 py-1.5 text-xs" onClick={() => setRefreshes((count) => count + 1)}>
            Try again
          </Button>
        </div>
      ) : visible.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center gap-3 py-16 bg-card border border-border/70 rounded-2xl">
          <div className="w-12 h-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center">
            <Sparkles className="w-6 h-6" />
          </div>
          <p className="font-serif text-xl font-bold text-foreground">
            {source === 'mine' && !query && !category ? 'You haven’t written a skill yet' : 'No skills match'}
          </p>
          <p className="text-xs text-muted-foreground max-w-md">
            {source === 'mine' && !query && !category
              ? 'Write down how you like a recurring job done, and your agent will follow it every time.'
              : 'Try another search or filter.'}
          </p>
          {source === 'mine' && list?.can_create_private && (
            <Button className="px-4 py-2 w-auto text-xs mt-1" onClick={() => setEditor({ kind: 'create' })} icon={<Plus className="w-4 h-4" />}>
              New skill
            </Button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {visible.map((skill) => (
            <SkillCard
              key={skill.ref}
              skill={skill}
              busy={switching === skill.ref}
              onOpen={() => openSkill(skill.ref)}
              onToggle={(enabled) => void toggle(skill, enabled)}
              onTry={() => tryInChat(skill)}
            />
          ))}
        </div>
      )}

      {openRef && list && (
        <SkillDrawer
          key={`${openRef}:${saves}`}
          skillRef={openRef}
          canManageWorkspace={list.can_manage_workspace}
          canCreatePrivate={list.can_create_private}
          onClose={closeSkill}
          onChanged={replace}
          onArchived={() => {
            closeSkill();
            setRefreshes((count) => count + 1);
          }}
          onEdit={(skill) => setEditor({ kind: 'edit', skill })}
          onCopy={(skill) => {
            closeSkill();
            setEditor(copyOf(skill));
          }}
          onTry={tryInChat}
        />
      )}

      {editor && list && (
        <SkillEditor
          target={editor}
          tools={loaded?.tools ?? []}
          canManageWorkspace={list.can_manage_workspace}
          onClose={() => setEditor(null)}
          onSaved={saved}
        />
      )}

      {importing && (
        <ImportSkillModal
          onClose={() => setImporting(false)}
          onContinue={(draft) => {
            setImporting(false);
            setEditor({ kind: 'create', draft, note: 'Imported from SKILL.md' });
          }}
        />
      )}

      {archived && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs animate-in fade-in duration-200" onClick={() => setArchived(null)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="archived-skills-title"
            className="w-full max-w-lg max-h-[80vh] bg-card border border-border/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="px-5 py-4 border-b border-border/60 flex items-center justify-between gap-3">
              <div>
                <h3 id="archived-skills-title" className="text-base font-bold text-foreground">
                  Archived skills
                </h3>
                <p className="text-xs text-muted-foreground">
                  {list?.can_manage_workspace ? 'Your archived skills and the workspace’s.' : 'Skills you archived.'} Restoring one
                  puts it back as it was.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setArchived(null)}
                aria-label="Close"
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </header>
            <ul className="flex-1 overflow-y-auto divide-y divide-border/60">
              {archived.length === 0 && <li className="px-5 py-6 text-xs text-muted-foreground">Nothing archived.</li>}
              {archived.map((item) => (
                <li key={item.id} className="px-5 py-3 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-foreground truncate">{item.name}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {item.source === 'BUILTIN' ? 'Workspace version of a built-in skill' : item.source === 'WORKSPACE' ? 'Workspace skill' : 'Only me'} ·
                      version {item.version} · archived {timeAgo(item.archived_at)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void restore(item)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-semibold text-foreground/85 hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer shrink-0"
                  >
                    <ArchiveRestore className="w-3.5 h-3.5" /> Restore
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
};

export default Skills;
