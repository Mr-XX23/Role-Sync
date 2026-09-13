import React, { useState } from 'react';
import { Clock, CheckCircle2, AlertCircle, X, ShieldAlert, Sparkles, Timer, Zap, Power } from 'lucide-react';
import { Button } from '../../../components/common/Button';
import { useToast } from '../../../context/ToastContext';

export interface AutoSyncOption {
  id: string; // 'off', '2m', '30m', '1h', '6h', '24h'
  title: string;
  subtitle: string;
  intervalMinutes: number;
  badge: string;
  nextRunDesc: string;
  recommended?: boolean;
}

export const AUTO_SYNC_SCHEDULES: AutoSyncOption[] = [
  {
    id: 'off',
    title: 'Off (Manual Only)',
    subtitle: 'Sync only when you manually click "Sync Now". Automatic background sync is paused.',
    intervalMinutes: 0,
    badge: 'Manual',
    nextRunDesc: 'No automatic sync scheduled',
  },
  {
    id: '2m',
    title: 'Every 2 Minutes',
    subtitle: 'Fast sync for testing and rapid real-time updates.',
    intervalMinutes: 2,
    badge: 'Fast',
    nextRunDesc: 'Next sync in ~2 minutes',
  },
  {
    id: '30m',
    title: 'Every 30 Minutes',
    subtitle: 'Keeps your records fresh throughout the day with optimal performance.',
    intervalMinutes: 30,
    badge: 'Recommended',
    nextRunDesc: 'Next sync in ~30 minutes',
    recommended: true,
  },
  {
    id: '1h',
    title: 'Every 1 Hour',
    subtitle: 'Regular hourly sync capturing steady updates throughout the day.',
    intervalMinutes: 60,
    badge: 'Hourly',
    nextRunDesc: 'Next sync in ~1 hour',
  },
  {
    id: '6h',
    title: 'Every 6 Hours',
    subtitle: 'Periodic sync 4 times a day across standard business hours.',
    intervalMinutes: 360,
    badge: '4x Daily',
    nextRunDesc: 'Next sync in ~6 hours',
  },
  {
    id: '24h',
    title: 'Every 24 Hours',
    subtitle: 'Runs once overnight every day at 2:00 AM outside active work hours.',
    intervalMinutes: 1440,
    badge: 'Daily',
    nextRunDesc: 'Next sync tonight at 2:00 AM',
  },
];

export interface AutoSyncModalProps {
  isOpen: boolean;
  onClose: () => void;
  connectorId: string;
  connectorName: string;
  logoUrl?: string;
  currentFrequency?: string; // 'off', '2m', '30m', '1h', '6h', '24h', etc.
  initialAutoSyncEnabled?: boolean;
  initialWebhookEnabled?: boolean;
  isLocked?: boolean;
  isConnected?: boolean;
  onSaveSchedule: (
    frequency: string,
    intervalMinutes: number,
    autoSyncEnabled: boolean,
    webhookEnabled: boolean
  ) => Promise<void>;
}

export const AutoSyncModal: React.FC<AutoSyncModalProps> = ({
  isOpen,
  onClose,
  connectorId: _connectorId,
  connectorName,
  logoUrl,
  currentFrequency = 'off',
  initialAutoSyncEnabled,
  initialWebhookEnabled,
  isLocked = false,
  isConnected = true,
  onSaveSchedule,
}) => {
  const toast = useToast();

  // Normalize initial selection (defaults to 'off')
  const normalizedInitial = (() => {
    const raw = (currentFrequency || 'off').toLowerCase().replace(' auto', '').trim();
    if (['off', 'manual', 'disabled'].includes(raw)) return 'off';
    if (['2m', '30m', '1h', '6h', '24h'].includes(raw)) return raw;
    if (raw.includes('24h') || raw.includes('2 am') || raw.includes('daily')) return '24h';
    if (raw.includes('6h')) return '6h';
    if (raw.includes('1h') || raw.includes('hourly')) return '1h';
    if (raw.includes('2m')) return '2m';
    if (raw.includes('30m')) return '30m';
    return 'off';
  })();

  const [autoSyncEnabled, setAutoSyncEnabled] = useState<boolean>(() => {
    if (typeof initialAutoSyncEnabled === 'boolean') return initialAutoSyncEnabled;
    return normalizedInitial !== 'off';
  });

  const [selectedFreq, setSelectedFreq] = useState<string>(normalizedInitial);

  const [webhookEnabled, setWebhookEnabled] = useState<boolean>(() => {
    if (typeof initialWebhookEnabled === 'boolean') return initialWebhookEnabled;
    return false;
  });

  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!isOpen) return null;

  const effectiveFreq = autoSyncEnabled ? (selectedFreq === 'off' ? '30m' : selectedFreq) : 'off';
  const currentOption = AUTO_SYNC_SCHEDULES.find((s) => s.id === effectiveFreq) || AUTO_SYNC_SCHEDULES[0];

  const handleToggleAutoSync = () => {
    if (autoSyncEnabled) {
      setAutoSyncEnabled(false);
      setSelectedFreq('off');
    } else {
      setAutoSyncEnabled(true);
      if (selectedFreq === 'off') {
        setSelectedFreq('30m');
      }
    }
  };

  const handleSelectSchedule = (optId: string) => {
    if (optId === 'off') {
      setAutoSyncEnabled(false);
      setSelectedFreq('off');
    } else {
      setAutoSyncEnabled(true);
      setSelectedFreq(optId);
    }
  };

  const handleApply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isConnected) {
      const msg = `Please connect and authenticate ${connectorName} before configuring its sync schedule.`;
      setErrorMsg(msg);
      toast.warning(msg, 'Connection Required');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      const finalFreq = autoSyncEnabled ? (selectedFreq === 'off' ? '30m' : selectedFreq) : 'off';
      const finalOption = AUTO_SYNC_SCHEDULES.find((s) => s.id === finalFreq) || AUTO_SYNC_SCHEDULES[0];

      await onSaveSchedule(finalFreq, finalOption.intervalMinutes, autoSyncEnabled, webhookEnabled);
      toast.success(
        `Sync settings updated: Auto-Sync is ${autoSyncEnabled ? `ON (${finalOption.title})` : 'OFF'}, Webhooks Trigger is ${
          webhookEnabled ? 'ON' : 'OFF'
        } for ${connectorName}.`,
        'Settings Saved'
      );
      onClose();
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message ||
        'Failed to update sync settings. Please check server connectivity.';
      setErrorMsg(detail);
      toast.error(detail, 'Save Failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-xs transition-opacity duration-300 animate-in fade-in"
        onClick={onClose}
      />

      {/* Modal Card */}
      <div className="relative w-full max-w-2xl bg-card border border-border rounded-2xl shadow-2xl z-10 animate-in zoom-in-95 duration-200 overflow-hidden text-left flex flex-col max-h-[92vh]">
        {/* Header */}
        <div className="p-6 border-b border-border/80 flex justify-between items-start bg-muted/20">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center p-2.5 shadow-3xs shrink-0">
              {logoUrl ? (
                <img src={logoUrl} alt={connectorName} className="w-full h-full object-contain" />
              ) : (
                <Clock className="w-5 h-5 text-emerald-500" />
              )}
            </div>
            <div>
              <h3 className="text-lg font-semibold text-foreground tracking-tight">
                Sync & Trigger Settings
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Configure automated sync schedule and real-time updates for {connectorName}.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg border border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground transition-all cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Lock Warning Banner */}
        {isLocked && (
          <div className="bg-amber-500/10 border-b border-amber-500/20 px-6 py-2.5 flex items-center gap-2 text-xs font-semibold text-amber-600 dark:text-amber-400">
            <ShieldAlert className="w-4 h-4 shrink-0" />
            <span>Active sync running: Updated settings will take effect on the next scheduled cycle.</span>
          </div>
        )}

        {/* Form Body */}
        <form onSubmit={handleApply} className="p-6 space-y-5 overflow-y-auto flex-1">
          {errorMsg && (
            <div className="p-3.5 bg-destructive/10 border border-destructive/20 rounded-xl text-xs text-destructive flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* OPTION 1: SCHEDULED AUTO-SYNC */}
          <div className="p-4 rounded-xl border border-border/80 bg-muted/20 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`p-2.5 rounded-xl ${autoSyncEnabled ? 'bg-emerald-500/15 text-emerald-500' : 'bg-muted text-muted-foreground'}`}>
                  <Power className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-semibold text-foreground">
                      Automated Background Sync
                    </h4>
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${autoSyncEnabled ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400' : 'bg-muted text-muted-foreground'}`}>
                      {autoSyncEnabled ? 'Active' : 'Paused'}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Automatically sync new records and updates on a recurring schedule.
                  </p>
                </div>
              </div>

              {/* Toggle Switch */}
              <button
                type="button"
                onClick={handleToggleAutoSync}
                disabled={isSubmitting}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  autoSyncEnabled ? 'bg-emerald-500' : 'bg-muted-foreground/30'
                }`}
                role="switch"
                aria-checked={autoSyncEnabled}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                    autoSyncEnabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>

            {/* Schedule Option Cards */}
            <div className="space-y-2 pt-2 border-t border-border/60">
              <div className="flex items-center justify-between py-1">
                <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <Timer className="w-3.5 h-3.5 text-emerald-500" />
                  Sync Frequency
                </span>
                <span className="text-[11px] text-muted-foreground">
                  Current: <strong className="text-foreground">{currentOption.title}</strong>
                </span>
              </div>

              <div className="space-y-2">
                {AUTO_SYNC_SCHEDULES.map((opt) => {
                  const isSelected = effectiveFreq === opt.id;
                  const isOff = opt.id === 'off';
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      disabled={isSubmitting}
                      onClick={() => handleSelectSchedule(opt.id)}
                      className={`w-full p-3.5 rounded-xl border text-left transition-all flex items-center justify-between cursor-pointer group ${
                        isSelected
                          ? isOff
                            ? 'bg-muted/50 border-border ring-1 ring-border text-foreground shadow-3xs'
                            : 'bg-emerald-500/10 border-emerald-500/60 ring-1 ring-emerald-500/30 text-foreground shadow-3xs'
                          : 'bg-card border-border/70 hover:border-emerald-500/40 hover:bg-muted/30 text-muted-foreground'
                      }`}
                    >
                      <div className="space-y-0.5 pr-3">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={`text-xs font-semibold ${isSelected ? 'text-foreground font-bold' : 'text-foreground/90 group-hover:text-foreground'}`}>
                            {opt.title}
                          </span>
                          {opt.recommended && (
                            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25 flex items-center gap-1">
                              <Sparkles className="w-2.5 h-2.5" /> Recommended
                            </span>
                          )}
                          {opt.badge && !opt.recommended && (
                            <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-muted text-muted-foreground border border-border/60">
                              {opt.badge}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground leading-relaxed">{opt.subtitle}</p>
                      </div>

                      <div
                        className={`w-5 h-5 rounded-full border flex items-center justify-center shrink-0 transition-all ${
                          isSelected
                            ? isOff
                              ? 'bg-foreground border-foreground text-background'
                              : 'bg-emerald-500 border-emerald-500 text-white'
                            : 'border-border/80 bg-background group-hover:border-emerald-500/50'
                        }`}
                      >
                        {isSelected && <CheckCircle2 className="w-3.5 h-3.5" />}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* OPTION 2: REAL-TIME WEBHOOK UPDATES */}
          <div className="p-4 rounded-xl border border-border/80 bg-muted/20 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`p-2.5 rounded-xl ${webhookEnabled ? 'bg-emerald-500/15 text-emerald-500' : 'bg-muted text-muted-foreground'}`}>
                  <Zap className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-semibold text-foreground">
                      Real-Time Webhook Updates
                    </h4>
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${webhookEnabled ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400' : 'bg-muted text-muted-foreground'}`}>
                      {webhookEnabled ? 'Active' : 'Off'}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Instantly sync new items as soon as they are created or modified in {connectorName}.
                  </p>
                </div>
              </div>

              {/* Toggle Switch */}
              <button
                type="button"
                onClick={() => setWebhookEnabled(!webhookEnabled)}
                disabled={isSubmitting}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  webhookEnabled ? 'bg-emerald-500' : 'bg-muted-foreground/30'
                }`}
                role="switch"
                aria-checked={webhookEnabled}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                    webhookEnabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Schedule Summary Box */}
          <div className="p-3.5 rounded-xl bg-muted/30 border border-border/80 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2.5">
              <Clock className="w-4 h-4 text-emerald-500 shrink-0" />
              <div>
                <p className="font-medium text-foreground">
                  {autoSyncEnabled ? (
                    <>Syncing <strong className="text-emerald-500 font-semibold">{currentOption.title}</strong></>
                  ) : (
                    <>Automated sync is <strong className="text-muted-foreground">paused</strong></>
                  )}
                </p>
                <p className="text-[11px] text-muted-foreground">{currentOption.nextRunDesc}</p>
              </div>
            </div>
            <span className="text-xs font-semibold px-2.5 py-1 bg-background border border-border/80 rounded-lg text-foreground">
              {autoSyncEnabled ? currentOption.title : 'Manual Only'}
            </span>
          </div>

          {/* Bottom Actions */}
          <div className="pt-3 flex justify-end gap-2 border-t border-border/60">
            <Button variant="outline" type="button" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button
              variant="primary"
              type="submit"
              isLoading={isSubmitting}
              loadingText="Saving Settings..."
              disabled={isSubmitting}
            >
              Save & Apply Settings
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AutoSyncModal;
