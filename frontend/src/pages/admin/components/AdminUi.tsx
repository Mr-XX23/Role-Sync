import React, { useCallback, useEffect, useId, useState } from 'react';
import { AlertTriangle, ChevronLeft, ChevronRight, Inbox, Loader2, RefreshCw, Search, ShieldCheck, X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Button } from '../../../components/common/Button';

// Shared building blocks for the Super Admin Console, in the app's own visual language.

export type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'violet';

const TONE_BADGE: Record<Tone, string> = {
  neutral: 'bg-slate-500/10 text-slate-600 dark:text-slate-300 border-slate-500/20',
  primary: 'bg-primary/10 text-primary border-primary/25',
  success: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/25',
  warning: 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/25',
  danger: 'bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/25',
  info: 'bg-sky-500/10 text-sky-700 dark:text-sky-400 border-sky-500/25',
  violet: 'bg-violet-500/10 text-violet-700 dark:text-violet-300 border-violet-500/25',
};

const TONE_ICON: Record<Tone, string> = {
  neutral: 'bg-muted text-muted-foreground border-border/60',
  primary: 'bg-primary/10 text-primary border-primary/20',
  success: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
  warning: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
  danger: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20',
  info: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20',
  violet: 'bg-violet-500/10 text-violet-600 dark:text-violet-300 border-violet-500/20',
};

export const Badge: React.FC<{ tone?: Tone; children: React.ReactNode; className?: string; title?: string }> = ({
  tone = 'neutral',
  children,
  className = '',
  title,
}) => (
  <span
    title={title}
    className={`inline-flex items-center gap-1 text-[10px] font-mono font-bold uppercase tracking-wide px-2 py-0.5 rounded-md border whitespace-nowrap ${TONE_BADGE[tone]} ${className}`}
  >
    {children}
  </span>
);

export const AdminPage: React.FC<{
  title: string;
  description?: React.ReactNode;
  icon?: LucideIcon;
  actions?: React.ReactNode;
  children: React.ReactNode;
}> = ({ title, description, icon: Icon, actions, children }) => (
  <div className="flex flex-col gap-6 pb-10 animate-in fade-in duration-300">
    <section className="flex flex-col md:flex-row md:items-end justify-between gap-4">
      <div className="space-y-2 min-w-0">
        <div className="flex items-center gap-3">
          {Icon && (
            <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 text-primary flex items-center justify-center shrink-0">
              <Icon className="w-5 h-5" />
            </div>
          )}
          <h2 className="font-serif text-3xl font-bold text-primary leading-tight">{title}</h2>
        </div>
        {description && <p className="text-sm text-muted-foreground max-w-3xl leading-relaxed">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 shrink-0">{actions}</div>}
    </section>
    {children}
  </div>
);

export const Card: React.FC<{
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  icon?: LucideIcon;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}> = ({ title, subtitle, icon: Icon, actions, children, className = '', bodyClassName = 'p-5' }) => (
  <section className={`bg-card border border-border/80 rounded-2xl shadow-2xs min-w-0 flex flex-col ${className}`}>
    {(title || actions) && (
      <header className="px-5 pt-4 pb-3 border-b border-border/50 flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5 min-w-0">
          {Icon && <Icon className="w-4 h-4 mt-0.5 text-muted-foreground shrink-0" />}
          <div className="min-w-0">
            {title && <h3 className="text-sm font-bold text-foreground leading-tight">{title}</h3>}
            {subtitle && <p className="text-[11px] text-muted-foreground mt-0.5">{subtitle}</p>}
          </div>
        </div>
        {actions && <div className="flex items-center gap-1.5 shrink-0">{actions}</div>}
      </header>
    )}
    <div className={`flex-1 min-w-0 ${bodyClassName}`}>{children}</div>
  </section>
);

export const StatCard: React.FC<{
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: LucideIcon;
  tone?: Tone;
  loading?: boolean;
}> = ({ label, value, hint, icon: Icon, tone = 'primary', loading = false }) => (
  <div className="bg-card border border-border/80 rounded-2xl px-4 py-3.5 shadow-2xs min-w-0 flex items-start gap-3">
    {Icon && (
      <div className={`w-9 h-9 rounded-xl border flex items-center justify-center shrink-0 ${TONE_ICON[tone]}`}>
        <Icon className="w-4 h-4" />
      </div>
    )}
    <div className="min-w-0">
      <p className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground truncate">{label}</p>
      {loading ? (
        <div className="h-7 w-16 mt-1 rounded-md bg-muted animate-pulse" />
      ) : (
        <p className="text-xl font-bold text-foreground tabular-nums leading-tight mt-0.5 truncate">{value}</p>
      )}
      {hint && !loading && <p className="text-[11px] text-muted-foreground mt-0.5 truncate">{hint}</p>}
    </div>
  </div>
);

export const Switch: React.FC<{
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label: string;
  size?: 'sm' | 'md';
}> = ({ checked, onChange, disabled = false, label, size = 'md' }) => {
  const track = size === 'sm' ? 'w-8 h-[18px]' : 'w-10 h-[22px]';
  const thumb = size === 'sm' ? 'w-3.5 h-3.5' : 'w-4.5 h-4.5';
  const shift = size === 'sm' ? 'translate-x-[14px]' : 'translate-x-[18px]';
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex shrink-0 items-center rounded-full border transition-colors duration-200 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 ${track} ${
        checked ? 'bg-emerald-500 border-emerald-500' : 'bg-muted border-border'
      }`}
    >
      <span
        className={`inline-block rounded-full bg-white shadow-sm transition-transform duration-200 ml-[2px] ${thumb} ${checked ? shift : 'translate-x-0'}`}
      />
    </button>
  );
};

export const Segmented = <T extends string>({
  value,
  options,
  onChange,
  label,
  size = 'md',
}: {
  value: T;
  options: { value: T; label: string; icon?: LucideIcon }[];
  onChange: (value: T) => void;
  label: string;
  size?: 'sm' | 'md';
}) => (
  <div role="radiogroup" aria-label={label} className="inline-flex items-center p-0.5 rounded-xl border border-border/80 bg-muted/40">
    {options.map((option) => {
      const Icon = option.icon;
      const selected = option.value === value;
      return (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={selected}
          onClick={() => onChange(option.value)}
          className={`flex items-center gap-1.5 rounded-[10px] font-semibold transition-all cursor-pointer ${
            size === 'sm' ? 'px-2.5 py-1 text-[11px]' : 'px-3 py-1.5 text-xs'
          } ${selected ? 'bg-card text-foreground shadow-xs border border-border/70' : 'text-muted-foreground hover:text-foreground border border-transparent'}`}
        >
          {Icon && <Icon className="w-3.5 h-3.5" />}
          {option.label}
        </button>
      );
    })}
  </div>
);

export const SearchInput: React.FC<{
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  className?: string;
}> = ({ value, onChange, placeholder, className = '' }) => (
  <div className={`relative flex-1 min-w-[14rem] max-w-md ${className}`}>
    <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/70" />
    <input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      aria-label={placeholder}
      className="w-full pl-9 pr-8 py-2 rounded-xl border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/10 focus:border-primary"
    />
    {value && (
      <button
        type="button"
        onClick={() => onChange('')}
        aria-label="Clear search"
        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-muted-foreground hover:text-foreground cursor-pointer"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    )}
  </div>
);

export const selectClass =
  'py-2 px-3 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/10 focus:border-primary cursor-pointer disabled:opacity-60';

export const inputClass =
  'w-full py-2 px-3 rounded-xl border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/10 focus:border-primary disabled:opacity-60 disabled:cursor-not-allowed';

export const labelClass = 'block text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground';

export const RefreshButton: React.FC<{ onClick: () => void; loading: boolean; label?: string }> = ({
  onClick,
  loading,
  label = 'Refresh',
}) => (
  <button
    type="button"
    onClick={onClick}
    disabled={loading}
    title={label}
    aria-label={label}
    className="p-2 rounded-xl border border-border text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors cursor-pointer disabled:cursor-default bg-card"
  >
    <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
  </button>
);

export const IconAction: React.FC<{
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  tone?: 'default' | 'danger' | 'success';
}> = ({ icon: Icon, label, onClick, disabled = false, tone = 'default' }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    title={label}
    aria-label={label}
    className={`p-1.5 rounded-lg transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${
      tone === 'danger'
        ? 'text-muted-foreground hover:text-destructive hover:bg-destructive/10'
        : tone === 'success'
          ? 'text-muted-foreground hover:text-emerald-600 hover:bg-emerald-500/10'
          : 'text-muted-foreground hover:text-foreground hover:bg-muted'
    }`}
  >
    <Icon className="w-4 h-4" />
  </button>
);

export const LoadingBlock: React.FC<{ label?: string; className?: string }> = ({ label = 'Loading…', className = 'py-16' }) => (
  <div className={`flex items-center justify-center gap-2 text-sm text-muted-foreground ${className}`}>
    <Loader2 className="w-4 h-4 animate-spin" />
    {label}
  </div>
);

export const ErrorBlock: React.FC<{ message: string; onRetry?: () => void; compact?: boolean }> = ({
  message,
  onRetry,
  compact = false,
}) => (
  <div
    role="alert"
    className={`rounded-2xl border border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300 flex items-center justify-between gap-3 ${
      compact ? 'px-3 py-2 text-xs' : 'px-5 py-4 text-sm'
    }`}
  >
    <span className="flex items-center gap-2 min-w-0">
      <AlertTriangle className="w-4 h-4 shrink-0" />
      <span className="min-w-0">{message}</span>
    </span>
    {onRetry && (
      <Button variant="outline" className="px-3 py-1.5 text-xs shrink-0" onClick={onRetry}>
        Try again
      </Button>
    )}
  </div>
);

export const EmptyBlock: React.FC<{ icon?: LucideIcon; title: string; description?: React.ReactNode; action?: React.ReactNode }> = ({
  icon: Icon = Inbox,
  title,
  description,
  action,
}) => (
  <div className="flex flex-col items-center justify-center text-center gap-2 py-12 px-4">
    <div className="w-11 h-11 rounded-2xl bg-muted/70 text-muted-foreground flex items-center justify-center">
      <Icon className="w-5 h-5" />
    </div>
    <p className="text-sm font-semibold text-foreground">{title}</p>
    {description && <p className="text-xs text-muted-foreground max-w-sm">{description}</p>}
    {action && <div className="mt-2">{action}</div>}
  </div>
);

export const Notice: React.FC<{ tone?: 'info' | 'warning' | 'danger' | 'success'; icon?: LucideIcon; children: React.ReactNode }> = ({
  tone = 'info',
  icon: Icon = ShieldCheck,
  children,
}) => {
  const styles = {
    info: 'border-sky-500/25 bg-sky-500/5 text-sky-800 dark:text-sky-200',
    warning: 'border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-200',
    danger: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300',
    success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200',
  }[tone];
  return (
    <div className={`rounded-xl border px-4 py-2.5 text-xs flex items-start gap-2 leading-relaxed ${styles}`}>
      <Icon className="w-4 h-4 shrink-0 mt-px" />
      <div className="min-w-0">{children}</div>
    </div>
  );
};

export const Pagination: React.FC<{
  page: number;
  totalPages: number;
  total: number;
  size: number;
  onPage: (page: number) => void;
  disabled?: boolean;
}> = ({ page, totalPages, total, size, onPage, disabled = false }) => {
  if (total === 0) return null;
  const from = page * size + 1;
  const to = Math.min(total, (page + 1) * size);
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 border-t border-border/60 text-xs text-muted-foreground">
      <span className="tabular-nums">
        {from}–{to} of {total}
      </span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onPage(page - 1)}
          disabled={disabled || page <= 0}
          aria-label="Previous page"
          className="p-1.5 rounded-lg border border-border/70 hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span className="px-2 tabular-nums">
          Page {page + 1} of {Math.max(totalPages, 1)}
        </span>
        <button
          type="button"
          onClick={() => onPage(page + 1)}
          disabled={disabled || page + 1 >= totalPages}
          aria-label="Next page"
          className="p-1.5 rounded-lg border border-border/70 hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};

function useEscape(onEscape: () => void, enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onEscape();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onEscape, enabled]);
}

/** A panel sliding in from the right, for details of one user or workspace. */
export const Drawer: React.FC<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  width?: string;
}> = ({ title, subtitle, onClose, children, footer, width = 'max-w-xl' }) => {
  const titleId = useId();
  // Escape closes a confirmation opened on top of the drawer first, not both at once.
  const closeUnlessCovered = useCallback(() => {
    if (document.querySelectorAll('[aria-modal="true"]').length <= 1) onClose();
  }, [onClose]);
  useEscape(closeUnlessCovered, true);
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-xs animate-in fade-in duration-200" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`relative h-full w-full ${width} bg-card border-l border-border shadow-2xl flex flex-col animate-in slide-in-from-right duration-300`}
      >
        <header className="px-6 py-4 border-b border-border/60 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 id={titleId} className="text-base font-bold text-foreground truncate">
              {title}
            </h3>
            {subtitle && <div className="text-xs text-muted-foreground mt-0.5">{subtitle}</div>}
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
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">{children}</div>
        {footer && <footer className="px-6 py-3 border-t border-border/60 bg-muted/20">{footer}</footer>}
      </aside>
    </div>
  );
};

export const Modal: React.FC<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  icon?: LucideIcon;
  onClose: () => void;
  busy?: boolean;
  children: React.ReactNode;
  footer?: React.ReactNode;
  width?: string;
}> = ({ title, subtitle, icon: Icon, onClose, busy = false, children, footer, width = 'max-w-lg' }) => {
  const titleId = useId();
  useEscape(() => !busy && onClose(), true);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs" onClick={() => !busy && onClose()}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
        className={`w-full ${width} max-h-[92vh] bg-card border border-border/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col`}
      >
        <div className="px-6 py-4 border-b border-border/60 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            {Icon && (
              <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0">
                <Icon className="w-5 h-5" />
              </div>
            )}
            <div className="min-w-0">
              <h3 id={titleId} className="text-base font-bold text-foreground truncate">
                {title}
              </h3>
              {subtitle && <p className="text-xs text-muted-foreground truncate">{subtitle}</p>}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            aria-label="Close"
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors disabled:opacity-30 cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6 space-y-4">{children}</div>
        {footer && <div className="px-6 py-3 border-t border-border/60 bg-muted/20 flex items-center justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
};

/**
 * Confirmation for an admin action. With `reasonLabel` it asks for an optional note that is kept in
 * the audit log. `destructive` styles it as a warning.
 */
export const ConfirmAction: React.FC<{
  title: string;
  message: React.ReactNode;
  confirmLabel: string;
  busyLabel?: string;
  destructive?: boolean;
  busy: boolean;
  reasonLabel?: string;
  onConfirm: (reason: string | null) => void;
  onCancel: () => void;
}> = ({ title, message, confirmLabel, busyLabel = 'Working…', destructive = false, busy, reasonLabel, onConfirm, onCancel }) => {
  const [reason, setReason] = useState('');
  const fieldId = useId();
  return (
    <Modal
      title={title}
      icon={destructive ? AlertTriangle : ShieldCheck}
      onClose={onCancel}
      busy={busy}
      width="max-w-md"
      footer={
        <>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="px-4 py-2 text-xs font-medium rounded-xl border border-border/70 hover:bg-muted/60 text-muted-foreground hover:text-foreground transition-colors cursor-pointer disabled:opacity-50"
          >
            Cancel
          </button>
          <Button
            variant={destructive ? 'destructive' : 'primary'}
            className="px-4 py-2 w-auto text-xs"
            onClick={() => onConfirm(reason.trim() || null)}
            isLoading={busy}
            loadingText={busyLabel}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-sm text-muted-foreground leading-relaxed">{message}</div>
      {reasonLabel && (
        <div className="space-y-1">
          <label htmlFor={fieldId} className={labelClass}>
            {reasonLabel} <span className="normal-case font-normal tracking-normal">(optional, kept in the audit log)</span>
          </label>
          <textarea
            id={fieldId}
            value={reason}
            maxLength={500}
            rows={3}
            disabled={busy}
            onChange={(event) => setReason(event.target.value)}
            className="w-full"
            placeholder="Why are you doing this?"
          />
        </div>
      )}
    </Modal>
  );
};

export const KeyValue: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="min-w-0">
    <dt className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground">{label}</dt>
    <dd className="text-sm text-foreground mt-0.5 break-words">{children}</dd>
  </div>
);

export const Avatar: React.FC<{ text: string; tone?: Tone; size?: 'sm' | 'md' | 'lg' }> = ({ text, tone = 'primary', size = 'md' }) => {
  const dimension = size === 'sm' ? 'w-7 h-7 text-[10px]' : size === 'lg' ? 'w-12 h-12 text-base' : 'w-9 h-9 text-xs';
  return (
    <div className={`rounded-full border flex items-center justify-center font-bold shrink-0 ${dimension} ${TONE_ICON[tone]}`}>
      {text}
    </div>
  );
};

export const TableShell: React.FC<{ children: React.ReactNode; footer?: React.ReactNode }> = ({ children, footer }) => (
  <div className="rounded-2xl border border-border/80 bg-card overflow-hidden shadow-2xs">
    <div className="overflow-x-auto">
      <table className="w-full text-xs text-left">{children}</table>
    </div>
    {footer}
  </div>
);

export const Th: React.FC<{ children?: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <th className={`px-4 py-3 font-semibold whitespace-nowrap ${className}`}>{children}</th>
);

export const TableHead: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <thead className="bg-muted/40 text-muted-foreground uppercase text-[10px] tracking-wide border-b border-border/70">
    <tr>{children}</tr>
  </thead>
);
