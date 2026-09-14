import React, { useMemo, useState } from 'react';
import { Cpu, FlaskConical, PlugZap } from 'lucide-react';
import { adminApi, describeAdminError } from '../../api/adminApi';
import type { ModelTestResult } from '../../api/adminApi';
import { Button } from '../../components/common/Button';
import { useToast } from '../../context/ToastContext';
import { AdminPage, Badge, Card, ErrorBlock, LoadingBlock, RefreshButton, TableHead, TableShell, Th, inputClass, labelClass, selectClass } from './components/AdminUi';
import { formatCompact, formatNumber, formatUsd } from './adminFormat';
import { useAdminQuery } from './useAdminQuery';
import { RatesEditor } from './models/RatesEditor';
import { RouteCard } from './models/RouteCard';
import { TestResult } from './models/TestResult';

export const AdminModels: React.FC = () => {
  const toast = useToast();
  const config = useAdminQuery(() => adminApi.models(), 'models');
  const [testProvider, setTestProvider] = useState('');
  const [testModel, setTestModel] = useState('');
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<ModelTestResult | null>(null);

  const suggestions = useMemo(() => {
    const names = new Set<string>();
    for (const rate of config.data?.rates ?? []) names.add(rate.model);
    for (const route of config.data?.routes ?? []) route.models.forEach((model) => names.add(model));
    for (const row of config.data?.usage_7d ?? []) names.add(row.model);
    return [...names].filter((name) => !name.includes('*')).sort();
  }, [config.data]);

  const provider = testProvider || config.data?.providers.find((item) => item.configured)?.name || '';

  const runTest = async () => {
    if (!provider || !testModel.trim()) return;
    setTesting(true);
    setResult(null);
    try {
      setResult(await adminApi.testModel(provider, testModel.trim()));
    } catch (error) {
      toast.error(describeAdminError(error), 'Couldn’t run the test');
    } finally {
      setTesting(false);
    }
  };

  return (
    <AdminPage
      title="Models"
      icon={Cpu}
      description="Choose which AI model handles each kind of work, keep prices current for cost estimates, and test a model before you switch to it. Changes reach the agent within seconds, without a restart."
      actions={<RefreshButton onClick={config.reload} loading={config.loading} label="Refresh models" />}
    >
      {config.error && !config.data ? (
        <ErrorBlock message={config.error} onRetry={config.reload} />
      ) : !config.data ? (
        <LoadingBlock />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground flex items-center gap-1.5">
              <PlugZap className="w-3.5 h-3.5" /> Providers:
            </span>
            {config.data.providers.map((item) => (
              <Badge key={item.name} tone={item.configured ? 'success' : 'warning'} title={item.configured ? 'API key configured' : 'No API key on the server'}>
                {item.label} · {item.configured ? 'ready' : 'not configured'}
              </Badge>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {config.data.routes.map((route) => (
              <RouteCard
                key={`${route.route}:${route.provider}:${route.models.join(',')}`}
                route={route}
                config={config.data!}
                suggestions={suggestions}
                onSaved={(next) => config.update(() => next)}
              />
            ))}
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <Card className="xl:col-span-2" title="Model usage" subtitle="Last 7 days, all workspaces" icon={Cpu} bodyClassName="p-0">
              {config.data.usage_7d.length === 0 ? (
                <p className="text-xs text-muted-foreground px-5 py-10 text-center">No model calls in the last 7 days.</p>
              ) : (
                <TableShell>
                  <TableHead>
                    <Th>Model</Th>
                    <Th>Calls</Th>
                    <Th>Input tokens</Th>
                    <Th>Output tokens</Th>
                    <Th>Cost</Th>
                  </TableHead>
                  <tbody className="divide-y divide-border/60">
                    {[...config.data.usage_7d]
                      .sort((a, b) => b.input_tokens + b.output_tokens - (a.input_tokens + a.output_tokens))
                      .map((row) => (
                        <tr key={`${row.provider}-${row.model}`}>
                          <td className="px-4 py-2.5">
                            <span className="font-mono text-foreground break-all">{row.model}</span>
                            <span className="block text-[10px] text-muted-foreground">{row.provider}</span>
                          </td>
                          <td className="px-4 py-2.5 tabular-nums">{formatNumber(row.calls)}</td>
                          <td className="px-4 py-2.5 tabular-nums">{formatCompact(row.input_tokens)}</td>
                          <td className="px-4 py-2.5 tabular-nums">{formatCompact(row.output_tokens)}</td>
                          <td className="px-4 py-2.5 tabular-nums">{formatUsd(row.cost_usd)}</td>
                        </tr>
                      ))}
                  </tbody>
                </TableShell>
              )}
            </Card>

            <Card title="Try any model" subtitle="Sends one short test message. It counts toward usage." icon={FlaskConical}>
              <div className="space-y-3">
                <div className="space-y-1">
                  <label htmlFor="test-provider" className={labelClass}>
                    Provider
                  </label>
                  <select id="test-provider" className={`${selectClass} w-full`} value={provider} onChange={(event) => setTestProvider(event.target.value)}>
                    {config.data.providers.map((item) => (
                      <option key={item.name} value={item.name} disabled={!item.configured}>
                        {item.label}
                        {item.configured ? '' : ' (not configured)'}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label htmlFor="test-model" className={labelClass}>
                    Model
                  </label>
                  <input
                    id="test-model"
                    className={`${inputClass} font-mono text-xs`}
                    list="model-test-suggestions"
                    value={testModel}
                    placeholder={provider === 'gemini' ? 'gemini-2.5-flash' : 'vendor/model-name'}
                    onChange={(event) => setTestModel(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') void runTest();
                    }}
                  />
                  <datalist id="model-test-suggestions">
                    {suggestions.map((model) => (
                      <option key={model} value={model} />
                    ))}
                  </datalist>
                </div>
                <Button className="px-3 py-2 w-full text-xs" icon={<FlaskConical className="w-3.5 h-3.5" />} iconPosition="left" isLoading={testing} loadingText="Waiting for the model…" disabled={!provider || !testModel.trim()} onClick={() => void runTest()}>
                  Run test
                </Button>
                {result && <TestResult result={result} onDismiss={() => setResult(null)} />}
              </div>
            </Card>
          </div>

          <RatesEditor config={config.data} onSaved={(next) => config.update(() => next)} />
        </>
      )}
    </AdminPage>
  );
};

export default AdminModels;
