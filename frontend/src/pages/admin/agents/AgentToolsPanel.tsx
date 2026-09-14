import React, { useMemo, useState } from 'react';
import { Lock, Wrench } from 'lucide-react';
import { adminApi, describeAdminError } from '../../../api/adminApi';
import type { AdminTool, AgentControls } from '../../../api/adminApi';
import { useToast } from '../../../context/ToastContext';
import { Badge, EmptyBlock, SearchInput, Segmented, Switch } from '../components/AdminUi';
import { formatNumber, humanize, percent } from '../adminFormat';
import { SWITCHED_TOOLS, TOOL_KIND_META } from './agentMeta';

type KindFilter = 'all' | AdminTool['kind'];

export const AgentToolsPanel: React.FC<{
  tools: AdminTool[];
  controls: AgentControls | null;
  onChanged: (tool: AdminTool) => void;
}> = ({ tools, controls, onChanged }) => {
  const toast = useToast();
  const [search, setSearch] = useState('');
  const [kind, setKind] = useState<KindFilter>('all');
  const [saving, setSaving] = useState<string | null>(null);

  const visible = useMemo(() => {
    const words = search.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return tools
      .filter((tool) => kind === 'all' || tool.kind === kind)
      .filter((tool) => {
        const text = `${tool.name} ${tool.description} ${tool.category} ${tool.scope}`.toLowerCase();
        return words.every((word) => text.includes(word));
      })
      .sort((a, b) => a.kind.localeCompare(b.kind) || a.name.localeCompare(b.name));
  }, [tools, search, kind]);

  const counts = useMemo(() => {
    const off = tools.filter((tool) => !tool.enabled).length;
    return { total: tools.length, off, calls: tools.reduce((sum, tool) => sum + tool.calls_30d, 0) };
  }, [tools]);

  const toggle = async (tool: AdminTool, enabled: boolean) => {
    setSaving(tool.name);
    try {
      const updated = await adminApi.setToolEnabled(tool.name, enabled);
      onChanged(updated);
      toast.success(
        enabled ? `The agent can use ${tool.name} again.` : `The agent won’t see or run ${tool.name} anymore.`,
        enabled ? 'Tool turned on' : 'Tool turned off'
      );
    } catch (error) {
      toast.error(describeAdminError(error), 'Couldn’t change the tool');
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <SearchInput value={search} onChange={setSearch} placeholder="Search tools…" />
          <Segmented<KindFilter>
            label="Tool kind"
            size="sm"
            value={kind}
            onChange={setKind}
            options={[
              { value: 'all', label: 'All' },
              { value: 'READ', label: 'Read' },
              { value: 'WRITE', label: 'Actions' },
              { value: 'MEMORY', label: 'Memory' },
              { value: 'DELEGATE', label: 'Sub-agents' },
            ]}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          {formatNumber(counts.total)} tools · {formatNumber(counts.off)} turned off · {formatNumber(counts.calls)} calls in 30 days
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {visible.map((tool) => {
          const kindMeta = TOOL_KIND_META[tool.kind] ?? { label: tool.kind, tone: 'neutral' as const, description: '' };
          const switchKey = SWITCHED_TOOLS[tool.name];
          const offBySwitch = Boolean(switchKey && controls && !controls[switchKey]);
          const failureRate = percent(tool.failures_30d, tool.calls_30d);
          return (
            <article
              key={tool.name}
              className={`rounded-2xl border bg-card p-4 flex flex-col gap-3 shadow-2xs transition-colors ${
                tool.enabled ? 'border-border/80' : 'border-dashed border-border opacity-80'
              }`}
            >
              <header className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-mono text-xs font-bold text-foreground break-all">{tool.name}</p>
                  <div className="flex flex-wrap items-center gap-1 mt-1.5">
                    <Badge tone={kindMeta.tone} title={kindMeta.description}>
                      {kindMeta.label}
                    </Badge>
                    <Badge>{humanize(tool.category)}</Badge>
                    {tool.irreversible && <Badge tone="danger">Can’t be undone</Badge>}
                    {tool.protected && (
                      <Badge tone="neutral" title="Needed for safety or for long results, so it can’t be turned off">
                        <Lock className="w-3 h-3" /> Always on
                      </Badge>
                    )}
                  </div>
                </div>
                <Switch
                  size="sm"
                  label={`${tool.enabled ? 'Turn off' : 'Turn on'} ${tool.name}`}
                  checked={tool.enabled}
                  disabled={tool.protected || offBySwitch || saving === tool.name}
                  onChange={(checked) => void toggle(tool, checked)}
                />
              </header>
              <p className="text-xs text-muted-foreground leading-relaxed line-clamp-3" title={tool.description}>
                {tool.description}
              </p>
              {offBySwitch && (
                <p className="text-[11px] text-amber-700 dark:text-amber-300">
                  Off because {switchKey === 'web_search_enabled' ? 'web search' : 'sub-agents'} are switched off in Controls.
                </p>
              )}
              <footer className="mt-auto pt-2 border-t border-border/50 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                <span className="truncate" title="Agents allowed to use it">
                  {tool.available_to.map(humanize).join(', ') || '—'}
                </span>
                <span className="tabular-nums shrink-0">
                  {formatNumber(tool.calls_30d)} calls
                  {tool.failures_30d > 0 && <span className="text-red-600 dark:text-red-400"> · {failureRate}% failed</span>}
                </span>
              </footer>
            </article>
          );
        })}
      </div>
      {visible.length === 0 && <EmptyBlock icon={Wrench} title="No tools match" description="Try another search or kind." />}
    </div>
  );
};
