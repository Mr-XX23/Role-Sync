import React, { useEffect } from 'react';
import { MessageSquarePlus, X } from 'lucide-react';
import type { SessionStatus, SessionSummary } from '../../../api/salesAgentApi';

const STATUS_TONE: Record<SessionStatus, string> = {
  RUNNING: 'bg-amber-500/15 border-amber-500/35 text-amber-800 dark:text-amber-300',
  AWAITING_APPROVAL: 'bg-blue-500/15 border-blue-500/35 text-blue-800 dark:text-blue-300',
  DONE: 'bg-emerald-500/15 border-emerald-500/35 text-emerald-800 dark:text-emerald-300',
  FAILED: 'bg-red-500/15 border-red-500/35 text-red-700 dark:text-red-300',
  HALTED: 'bg-muted border-border text-muted-foreground',
};
const STATUS_LABEL: Record<SessionStatus, string> = {
  RUNNING: 'Working',
  AWAITING_APPROVAL: 'Needs approval',
  DONE: 'Done',
  FAILED: 'Failed',
  HALTED: 'Stopped',
};

export const StatusPill: React.FC<{ status: SessionStatus }> = ({ status }) => (
  <span
    className={`text-[9px] font-mono font-bold tracking-widest uppercase border px-2 py-0.5 rounded-full whitespace-nowrap ${STATUS_TONE[status]}`}
  >
    {STATUS_LABEL[status]}
  </span>
);

interface HistoryDrawerProps {
  open: boolean;
  onClose: () => void;
  sessions: SessionSummary[];
  activeId: string | null;
  onOpenSession: (sessionId: string) => void;
  onNewChat: () => void;
}

/** Past conversations, in a slide-over so the chat itself stays uncluttered. */
export const HistoryDrawer: React.FC<HistoryDrawerProps> = ({ open, onClose, sessions, activeId, onOpenSession, onNewChat }) => {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <>
      <div
        className={`fixed inset-0 z-40 bg-black/40 backdrop-blur-[2px] transition-opacity duration-200 ${
          open ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
        aria-hidden
      />
      <aside
        role="dialog"
        aria-label="Conversation history"
        aria-hidden={!open}
        className={`fixed inset-y-0 right-0 z-50 w-[22rem] max-w-[90vw] bg-card border-l border-border shadow-2xl flex flex-col transition-transform duration-300 ease-out ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <header className="flex items-center justify-between gap-3 px-4 py-3.5 border-b border-border/70">
          <div>
            <p className="text-sm font-bold text-foreground">History</p>
            <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              {sessions.length} conversation{sessions.length === 1 ? '' : 's'}
            </p>
          </div>
          <button
            type="button"
            aria-label="Close history"
            onClick={onClose}
            className="w-8 h-8 rounded-lg border border-border/70 text-muted-foreground hover:text-foreground hover:bg-muted flex items-center justify-center transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        <div className="px-3 pt-3">
          <button
            type="button"
            onClick={() => {
              onNewChat();
              onClose();
            }}
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl border border-dashed border-border hover:border-primary/40 hover:bg-primary/5 px-3 py-2.5 text-xs font-semibold text-foreground transition-colors cursor-pointer"
          >
            <MessageSquarePlus className="w-3.5 h-3.5" />
            New chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {sessions.length === 0 && <p className="px-2 py-4 text-xs text-muted-foreground">No conversations yet.</p>}
          {sessions.map((session) => (
            <button
              key={session.id}
              type="button"
              onClick={() => {
                onOpenSession(session.id);
                onClose();
              }}
              className={`w-full text-left rounded-xl px-3 py-2.5 border transition-colors cursor-pointer ${
                session.id === activeId ? 'bg-muted/70 border-border' : 'border-transparent hover:bg-muted/40'
              }`}
            >
              <p className="text-xs font-semibold text-foreground truncate">{session.title || 'Untitled conversation'}</p>
              <div className="flex items-center justify-between gap-2 mt-1.5">
                <span className="text-[10px] text-muted-foreground font-mono">
                  {new Date(session.started_at).toLocaleString([], {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
                <StatusPill status={session.status} />
              </div>
            </button>
          ))}
        </div>
      </aside>
    </>
  );
};
