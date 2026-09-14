import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { Bot, MessagesSquare, SlidersHorizontal, Wrench } from 'lucide-react';
import { adminApi } from '../../api/adminApi';
import { AdminPage, ErrorBlock, LoadingBlock, RefreshButton, Segmented } from './components/AdminUi';
import { useAdminQuery } from './useAdminQuery';
import { AgentControlsPanel } from './agents/AgentControlsPanel';
import { AgentSessionsPanel } from './agents/AgentSessionsPanel';
import { AgentToolsPanel } from './agents/AgentToolsPanel';

type Tab = 'controls' | 'tools' | 'sessions';
const TABS: Tab[] = ['controls', 'tools', 'sessions'];

export const AdminAgents: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get('tab') as Tab | null;
  const tab: Tab = requested && TABS.includes(requested) ? requested : 'controls';
  const controls = useAdminQuery(() => adminApi.controls(), 'agent-controls');
  const tools = useAdminQuery(() => adminApi.tools(), 'agent-tools');

  const setTab = (next: Tab) => setSearchParams(next === 'controls' ? {} : { tab: next }, { replace: true });
  const refresh = () => {
    controls.reload();
    tools.reload();
  };

  return (
    <AdminPage
      title="Agent Manager"
      icon={Bot}
      description="Run the sales agent for the whole platform: pause it, decide which tools it may use, set its guardrails and budgets, and watch conversations as they happen."
      actions={
        <>
          <Segmented<Tab>
            label="Agent Manager section"
            value={tab}
            onChange={setTab}
            options={[
              { value: 'controls', label: 'Controls', icon: SlidersHorizontal },
              { value: 'tools', label: 'Tools', icon: Wrench },
              { value: 'sessions', label: 'Conversations', icon: MessagesSquare },
            ]}
          />
          {tab !== 'sessions' && <RefreshButton onClick={refresh} loading={controls.loading || tools.loading} />}
        </>
      }
    >
      {tab === 'controls' &&
        (controls.error && !controls.data ? (
          <ErrorBlock message={controls.error} onRetry={controls.reload} />
        ) : !controls.data ? (
          <LoadingBlock />
        ) : (
          <AgentControlsPanel
            controls={controls.data}
            onSaved={(saved) => {
              controls.update(() => saved);
              tools.reload(); // the feature switches change which tools are on
            }}
          />
        ))}

      {tab === 'tools' &&
        (tools.error && !tools.data ? (
          <ErrorBlock message={tools.error} onRetry={tools.reload} />
        ) : !tools.data ? (
          <LoadingBlock />
        ) : (
          <AgentToolsPanel
            tools={tools.data}
            controls={controls.data}
            onChanged={(updated) => tools.update((all) => all.map((tool) => (tool.name === updated.name ? updated : tool)))}
          />
        ))}

      {tab === 'sessions' && <AgentSessionsPanel />}
    </AdminPage>
  );
};

export default AdminAgents;
