import React, { useId, useState } from 'react';
import { FlaskConical, Pencil, Plus, RotateCcw, X } from 'lucide-react';
import { adminApi, describeAdminError } from '../../../api/adminApi';
import type { ModelRoute, ModelsConfig, ModelTestResult } from '../../../api/adminApi';
import { Button } from '../../../components/common/Button';
import { useToast } from '../../../context/ToastContext';
import { Badge, inputClass, labelClass, selectClass } from '../components/AdminUi';
import { TestResult } from './TestResult';

const MODEL_PATTERN = /^[A-Za-z0-9._:/@+-]+$/;

export const RouteCard: React.FC<{
  route: ModelRoute;
  config: ModelsConfig;
  suggestions: string[];
  onSaved: (config: ModelsConfig) => void;
}> = ({ route, config, suggestions, onSaved }) => {
  const toast = useToast();
  const listId = useId();
  const [editing, setEditing] = useState(false);
  const [provider, setProvider] = useState(route.provider);
  const [models, setModels] = useState<string[]>(route.models);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<ModelTestResult | null>(null);

  const providerInfo = config.providers.find((item) => item.name === provider);
  const multiple = providerInfo?.supports_model_list ?? false;
  const groundedOnly = route.route === 'web_grounded';
  const cleaned = models.map((model) => model.trim()).filter(Boolean);
  const problem =
    cleaned.length === 0
      ? 'Add a model.'
      : cleaned.some((model) => model.length > 200 || !MODEL_PATTERN.test(model))
        ? 'Model names use letters, numbers and . _ : / @ + - only.'
        : !multiple && cleaned.length > 1
          ? `${providerInfo?.label ?? 'This provider'} uses one model per route.`
          : null;

  const startEditing = () => {
    setProvider(route.provider);
    setModels(route.models.length > 0 ? route.models : ['']);
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const next = await adminApi.setRoute(route.route, provider, cleaned);
      onSaved(next);
      setEditing(false);
      toast.success(`${route.label} now uses ${cleaned.join(', ')}.`, 'Model route saved');
    } catch (error) {
      toast.error(describeAdminError(error), 'Couldn’t save the route');
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setSaving(true);
    try {
      const next = await adminApi.resetRoute(route.route);
      onSaved(next);
      setEditing(false);
      toast.success(`${route.label} is back to the server default.`, 'Route reset');
    } catch (error) {
      toast.error(describeAdminError(error), 'Couldn’t reset the route');
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    const model = (editing ? cleaned[0] : route.models[0]) ?? '';
    const testProvider = editing ? provider : route.provider;
    if (!model) return;
    setTesting(true);
    setResult(null);
    try {
      setResult(await adminApi.testModel(testProvider, model));
    } catch (error) {
      toast.error(describeAdminError(error), 'Couldn’t run the test');
    } finally {
      setTesting(false);
    }
  };

  return (
    <article className={`rounded-2xl border bg-card p-5 shadow-2xs flex flex-col gap-3 ${route.available ? 'border-border/80' : 'border-amber-500/40'}`}>
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-foreground">{route.label}</h3>
          <p className="text-[11px] text-muted-foreground mt-0.5">{route.description}</p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {route.overridden ? <Badge tone="primary">Custom</Badge> : <Badge>Default</Badge>}
          {!route.available && <Badge tone="warning">Provider not set</Badge>}
        </div>
      </header>

      {!editing ? (
        <>
          <div className="rounded-xl bg-muted/40 px-3 py-2.5 space-y-1.5">
            <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              {config.providers.find((item) => item.name === route.provider)?.label ?? route.provider}
            </p>
            <ol className="space-y-1">
              {route.models.map((model, index) => (
                <li key={`${model}-${index}`} className="font-mono text-xs text-foreground break-all flex items-center gap-2">
                  {route.models.length > 1 && <span className="text-[10px] text-muted-foreground w-4">{index + 1}.</span>}
                  {model}
                </li>
              ))}
            </ol>
          </div>
          {route.overridden && (
            <p className="text-[11px] text-muted-foreground">
              Server default: <span className="font-mono">{route.default_models.join(', ')}</span> on {route.default_provider}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2 mt-auto">
            <Button variant="outline" className="px-3 py-1.5 w-auto text-xs" icon={<Pencil className="w-3.5 h-3.5" />} iconPosition="left" onClick={startEditing}>
              Change
            </Button>
            <Button variant="outline" className="px-3 py-1.5 w-auto text-xs" icon={<FlaskConical className="w-3.5 h-3.5" />} iconPosition="left" isLoading={testing} loadingText="Testing…" disabled={!route.available} onClick={() => void test()}>
              Test
            </Button>
            {route.overridden && (
              <Button variant="outline" className="px-3 py-1.5 w-auto text-xs" icon={<RotateCcw className="w-3.5 h-3.5" />} iconPosition="left" disabled={saving} onClick={() => void reset()}>
                Use default
              </Button>
            )}
          </div>
        </>
      ) : (
        <div className="space-y-3">
          <div className="space-y-1">
            <label className={labelClass} htmlFor={`${listId}-provider`}>
              Provider
            </label>
            <select
              id={`${listId}-provider`}
              className={`${selectClass} w-full`}
              value={provider}
              disabled={groundedOnly || saving}
              onChange={(event) => {
                setProvider(event.target.value);
                setModels((current) => current.slice(0, 1));
              }}
            >
              {config.providers.map((item) => (
                <option key={item.name} value={item.name} disabled={!item.configured}>
                  {item.label}
                  {item.configured ? '' : ' (not configured)'}
                </option>
              ))}
            </select>
            {groundedOnly && <p className="text-[11px] text-muted-foreground">Only Gemini can answer from Google Search.</p>}
          </div>
          <div className="space-y-1.5">
            <span className={labelClass}>{multiple ? 'Models, tried in order' : 'Model'}</span>
            {models.map((model, index) => (
              <div key={index} className="flex items-center gap-2">
                <input
                  className={`${inputClass} font-mono text-xs`}
                  value={model}
                  list={listId}
                  maxLength={200}
                  placeholder={provider === 'gemini' ? 'gemini-2.5-flash' : 'vendor/model-name'}
                  disabled={saving}
                  aria-label={`Model ${index + 1}`}
                  onChange={(event) => setModels((current) => current.map((item, i) => (i === index ? event.target.value : item)))}
                />
                {models.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setModels((current) => current.filter((_, i) => i !== index))}
                    aria-label={`Remove model ${index + 1}`}
                    className="p-2 rounded-lg border border-border/70 text-muted-foreground hover:text-destructive hover:bg-destructive/10 cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
            <datalist id={listId}>
              {suggestions.map((model) => (
                <option key={model} value={model} />
              ))}
            </datalist>
            {multiple && models.length < 5 && (
              <button
                type="button"
                onClick={() => setModels((current) => [...current, ''])}
                className="text-[11px] font-semibold text-primary hover:underline flex items-center gap-1 cursor-pointer"
              >
                <Plus className="w-3 h-3" /> Add a fallback model
              </button>
            )}
            {problem && <p className="text-[11px] text-destructive">{problem}</p>}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setEditing(false)}
              disabled={saving}
              className="px-3 py-1.5 text-xs font-medium rounded-xl border border-border/70 hover:bg-muted/60 text-muted-foreground hover:text-foreground cursor-pointer disabled:opacity-50"
            >
              Cancel
            </button>
            <Button variant="outline" className="px-3 py-1.5 w-auto text-xs" icon={<FlaskConical className="w-3.5 h-3.5" />} iconPosition="left" isLoading={testing} loadingText="Testing…" disabled={Boolean(problem) || !providerInfo?.configured} onClick={() => void test()}>
              Test first model
            </Button>
            <Button className="px-3 py-1.5 w-auto text-xs" isLoading={saving} loadingText="Saving…" disabled={Boolean(problem)} onClick={() => void save()}>
              Save route
            </Button>
          </div>
        </div>
      )}

      {result && <TestResult result={result} onDismiss={() => setResult(null)} />}
    </article>
  );
};
