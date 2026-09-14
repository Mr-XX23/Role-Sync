import React from 'react';
import { CheckCircle2, X, XCircle } from 'lucide-react';
import type { ModelTestResult } from '../../../api/adminApi';
import { formatNumber } from '../adminFormat';

export const TestResult: React.FC<{ result: ModelTestResult; onDismiss: () => void }> = ({ result, onDismiss }) => (
  <div
    role="status"
    className={`rounded-xl border px-3 py-2.5 text-xs flex items-start gap-2 ${
      result.ok ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-red-500/30 bg-red-500/10'
    }`}
  >
    {result.ok ? (
      <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0 mt-px" />
    ) : (
      <XCircle className="w-4 h-4 text-red-600 dark:text-red-400 shrink-0 mt-px" />
    )}
    <div className="min-w-0 flex-1 space-y-0.5">
      <p className="font-semibold text-foreground">
        {result.ok ? 'Answered' : 'Failed'} in {formatNumber(result.latency_ms)} ms
        <span className="font-normal text-muted-foreground">
          {' '}
          · <span className="font-mono">{result.model}</span>
        </span>
      </p>
      {result.ok ? (
        <p className="text-muted-foreground">
          Reply “{(result.reply ?? '').slice(0, 120)}” · {formatNumber(result.input_tokens)} in / {formatNumber(result.output_tokens)} out tokens
        </p>
      ) : (
        <p className="text-red-700 dark:text-red-300 break-words">{result.error}</p>
      )}
    </div>
    <button type="button" onClick={onDismiss} aria-label="Dismiss test result" className="p-0.5 rounded text-muted-foreground hover:text-foreground cursor-pointer">
      <X className="w-3.5 h-3.5" />
    </button>
  </div>
);
