import React, { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { Brain, History, MessageSquarePlus, Sparkles } from 'lucide-react';
import { useToast } from '../../../context/ToastContext';
import { useAppSelector } from '../../../store';
import { describeAgentError, salesAgentApi } from '../../../api/salesAgentApi';
import type { AgentEventType, Decision, SessionStatus, SessionSummary } from '../../../api/salesAgentApi';
import { ApprovalCard } from './ApprovalCard';
import type { Attachment } from './attachments';
import { attachmentNote, releaseAttachment, uploadAttachments, waitForIndexed } from './attachments';
import type { ApprovalCardModel } from './chatState';
import { chatReducer, emptyChat } from './chatState';
import { Composer } from './Composer';
import type { ComposerPhase } from './Composer';
import { HistoryDrawer, StatusPill } from './HistoryDrawer';
import { MemoryPanel } from './MemoryPanel';
import { Transcript } from './Transcript';
import { useSessionEvents } from './useSessionEvents';

const STATUS_AFTER_EVENT: Partial<Record<AgentEventType, SessionStatus>> = {
  user_message: 'RUNNING',
  awaiting_approval: 'AWAITING_APPROVAL',
  approval_resolved: 'RUNNING',
  done: 'DONE',
  halted: 'HALTED',
  error: 'FAILED',
};

const ToolbarButton: React.FC<{
  label: string;
  icon: React.FC<{ className?: string }>;
  onClick: () => void;
  badge?: number;
}> = ({ label, icon: Icon, onClick, badge }) => (
  <button
    type="button"
    onClick={onClick}
    className="inline-flex items-center gap-1.5 rounded-full border border-border/80 bg-card px-3 py-1.5 text-xs font-semibold text-foreground/80 hover:text-foreground hover:bg-muted/60 hover:border-foreground/30 transition-colors cursor-pointer"
  >
    <Icon className="w-3.5 h-3.5" />
    {label}
    {badge !== undefined && badge > 0 && (
      <span className="ml-0.5 rounded-full bg-muted px-1.5 font-mono text-[10px] text-muted-foreground">{badge}</span>
    )}
  </button>
);

export const SalesAgent: React.FC = () => {
  const toast = useToast();
  const [chat, dispatch] = useReducer(chatReducer, emptyChat);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [streamAfter, setStreamAfter] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [phase, setPhase] = useState<ComposerPhase>('idle');
  const [progress, setProgress] = useState<string | null>(null);
  const [deciding, setDeciding] = useState<string | null>(null);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const role = useAppSelector((state) => state.workspace.currentWorkspace?.role);
  const bottomRef = useRef<HTMLDivElement>(null);

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await salesAgentApi.listSessions());
    } catch {
      // The chat itself reports errors; the history list just stays as it was.
    }
  }, []);

  useEffect(() => {
    let active = true;
    salesAgentApi
      .listSessions()
      .then((rows) => {
        if (active) setSessions(rows);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  useSessionEvents(chat.sessionId, streamAfter, (event) => {
    dispatch({ type: 'event', event });
    // Status changes arrive on the stream before the engine has saved them, so update the
    // history entry from the event instead of re-fetching a moment too early.
    const status = STATUS_AFTER_EVENT[event.type];
    if (status) {
      setSessions((rows) => rows.map((row) => (row.id === event.session_id ? { ...row, status } : row)));
    }
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [chat.items.length, chat.draft, chat.approvals.length, chat.outgoing]);

  const replaceAttachments = (next: Attachment[]) => {
    for (const current of attachments) {
      if (!next.some((candidate) => candidate.id === current.id)) releaseAttachment(current);
    }
    setAttachments(next);
  };

  const openSession = async (sessionId: string) => {
    try {
      const detail = await salesAgentApi.getSession(sessionId);
      dispatch({ type: 'snapshot', detail });
      setStreamAfter(detail.last_event_id);
    } catch (error) {
      toast.error(describeAgentError(error));
    }
  };

  const newConversation = () => {
    dispatch({ type: 'reset' });
    setStreamAfter(null);
    setInput('');
    replaceAttachments([]);
  };

  const blocked = phase !== 'idle' || chat.status === 'RUNNING' || chat.status === 'AWAITING_APPROVAL';
  const blockedReason =
    chat.status === 'AWAITING_APPROVAL' ? 'Review the action above to continue…' : chat.status === 'RUNNING' ? 'The agent is working…' : undefined;

  const send = async () => {
    const text = input.trim();
    if ((!text && attachments.length === 0) || blocked) {
      return;
    }
    let message = text || 'Please look at the attached files and tell me what matters in them.';
    const pendingAttachments = attachments;
    try {
      if (pendingAttachments.length > 0) {
        setPhase('uploading');
        const uploaded = await uploadAttachments(pendingAttachments, (done, total, name) =>
          setProgress(done < total ? `Uploading ${name} (${done + 1}/${total})` : null)
        );
        setPhase('indexing');
        setProgress(null);
        const outcome = await waitForIndexed(uploaded, {
          onTick: (state) => setProgress(state.pending.length ? `Reading ${state.pending.length} attachment${state.pending.length === 1 ? '' : 's'}` : null),
        });
        if (outcome.unreadable.length) {
          toast.warning(`Could not read: ${outcome.unreadable.join(', ')}. The agent will be told.`);
        }
        message = `${message}\n\n${attachmentNote(outcome)}`;
      }
      setPhase('sending');
      setProgress(null);
      dispatch({ type: 'sending', message });
      const started = await salesAgentApi.startChat(message, chat.sessionId);
      dispatch({ type: 'started', sessionId: started.session_id });
      setInput('');
      replaceAttachments([]);
      void refreshSessions();
    } catch (error) {
      dispatch({ type: 'send_failed' });
      toast.error(error instanceof Error && !('response' in error) ? error.message : describeAgentError(error));
    } finally {
      setPhase('idle');
      setProgress(null);
    }
  };

  const decide = async (
    card: ApprovalCardModel,
    decision: Decision,
    options?: { args?: Record<string, unknown>; note?: string }
  ) => {
    setDeciding(card.id);
    try {
      const action = await salesAgentApi.decide(card.id, decision, options);
      dispatch({ type: 'approval_decided', action });
    } catch (error) {
      toast.error(describeAgentError(error));
    } finally {
      setDeciding(null);
    }
  };

  const activeTitle = sessions.find((session) => session.id === chat.sessionId)?.title;
  const pending = chat.approvals.filter((card) => card.status === 'PENDING');
  const decided = chat.approvals.filter((card) => card.status !== 'PENDING');
  const empty = chat.items.length === 0 && !chat.draft && !chat.outgoing && pending.length === 0 && !chat.error;

  const composer = (variant: 'hero' | 'docked') => (
    <Composer
      variant={variant}
      value={input}
      onChange={setInput}
      attachments={attachments}
      onAttachmentsChange={replaceAttachments}
      onSend={() => void send()}
      onReject={(message) => toast.warning(message)}
      blocked={blocked}
      blockedReason={blockedReason}
      phase={phase}
      progress={progress}
      autoFocus={variant === 'hero'}
    />
  );

  return (
    <div className="h-full flex flex-col animate-in fade-in duration-500">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="flex items-center gap-2.5 min-w-0">
          {!empty && (
            <>
              <div className="w-7 h-7 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
                <Sparkles className="w-3.5 h-3.5" />
              </div>
              <p className="text-sm font-semibold text-foreground truncate">{activeTitle || 'New conversation'}</p>
              {chat.status && <StatusPill status={chat.status} />}
            </>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {!empty && <ToolbarButton label="New chat" icon={MessageSquarePlus} onClick={newConversation} />}
          <ToolbarButton label="History" icon={History} onClick={() => setHistoryOpen(true)} badge={sessions.length} />
          <ToolbarButton label="Memory" icon={Brain} onClick={() => setMemoryOpen(true)} />
        </div>
      </div>

      {empty ? (
        /* First message: headline + composer in the middle of the page */
        <div className="flex-1 flex flex-col items-center justify-center gap-7 pb-16">
          <div className="text-center space-y-2 px-4">
            <h1 className="font-serif text-4xl sm:text-5xl text-foreground tracking-tight text-balance">
              What can I do for you today?
            </h1>
            <p className="text-sm text-muted-foreground max-w-md mx-auto text-pretty">
              Research, outreach, quotes, documents and deals, using your inbox, calendar, catalog and knowledge base.
            </p>
          </div>
          <div className="w-full max-w-2xl px-1">{composer('hero')}</div>
          <p className="text-[11px] text-muted-foreground text-center max-w-md px-4">
            Attach documents or images and the agent reads them. Emails, meetings, documents and catalog changes only
            happen after you approve them.
          </p>
        </div>
      ) : (
        /* Conversation: transcript scrolls, composer stays docked at the bottom */
        <div className="flex-1 min-h-0 flex flex-col">
          <div className="flex-1 min-h-0 overflow-y-auto">
            <div className="max-w-4xl mx-auto w-full px-1 py-4 space-y-4">
              <Transcript
                items={chat.items}
                outgoing={chat.outgoing}
                draft={chat.draft}
                step={chat.step}
                running={chat.status === 'RUNNING'}
              />
              {decided.map((card) => (
                <ApprovalCard key={card.id} card={card} busy={false} onDecide={decide} />
              ))}
              {pending.map((card) => (
                <ApprovalCard key={card.id} card={card} busy={deciding === card.id} onDecide={decide} />
              ))}
              {chat.error && (
                <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-xs text-red-700 dark:text-red-300">
                  {chat.error}
                </div>
              )}
              <div ref={bottomRef} className="h-2" />
            </div>
          </div>
          <div className="shrink-0 pt-3 pb-1 bg-gradient-to-t from-background via-background to-transparent">
            <div className="max-w-3xl mx-auto w-full px-1">{composer('docked')}</div>
          </div>
        </div>
      )}

      <HistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        sessions={sessions}
        activeId={chat.sessionId}
        onOpenSession={(id) => void openSession(id)}
        onNewChat={newConversation}
      />
      {memoryOpen && <MemoryPanel canEditShared={role !== 'VIEWER'} onClose={() => setMemoryOpen(false)} />}
    </div>
  );
};

export default SalesAgent;
