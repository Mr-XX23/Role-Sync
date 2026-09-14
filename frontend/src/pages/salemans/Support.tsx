import React, { useCallback, useEffect, useEffectEvent, useState } from 'react';
import { ArrowLeft, Inbox, LifeBuoy, Loader2, MessageSquare, RefreshCw, Send } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { useToast } from '../../context/ToastContext';
import { useAppSelector } from '../../store';
import { describeSupportError, supportApi } from '../../api/supportApi';
import type { SupportTicket, SupportTicketStatus } from '../../api/supportApi';
import { formatDateTime, timeAgo } from './userManagement/memberFormat';

const STATUS_META: Record<SupportTicketStatus, { label: string; badge: string; hint: string }> = {
  OPEN: {
    label: 'Open',
    badge: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/25',
    hint: 'Waiting for the RoleSync team.',
  },
  IN_PROGRESS: {
    label: 'In progress',
    badge: 'bg-sky-500/10 text-sky-700 dark:text-sky-300 border-sky-500/25',
    hint: 'The team has answered and is on it.',
  },
  RESOLVED: {
    label: 'Resolved',
    badge: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/25',
    hint: 'Answered. Write back if it isn’t fixed and it reopens.',
  },
  CLOSED: {
    label: 'Closed',
    badge: 'bg-slate-500/10 text-slate-600 dark:text-slate-300 border-slate-500/25',
    hint: 'Closed by the team. Open a new ticket if you still need help.',
  },
};

const textareaClass =
  'w-full bg-background border border-border rounded-lg px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/50 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-primary/10 focus:border-primary shadow-2xs resize-none disabled:opacity-60';

const StatusBadge: React.FC<{ status: SupportTicketStatus }> = ({ status }) => (
  <span className={`inline-flex items-center px-2 py-0.5 rounded-md border text-[10px] font-mono font-bold uppercase tracking-wider whitespace-nowrap ${STATUS_META[status].badge}`}>
    {STATUS_META[status].label}
  </span>
);

interface Loaded<T> {
  key: string; // what was asked for
  request: string; // key + reload counter: the request this answers
  data: T | null;
  error: string | null;
}

/**
 * Loads something for a key; when the key changes the old answer is dropped, `reload()` asks
 * again while the old answer stays visible, and answers to superseded requests are ignored.
 * (Nothing is set synchronously inside the effect, which React's lint rule forbids.)
 */
function useLoad<T>(load: (() => Promise<T>) | null, key: string) {
  const [reloads, setReloads] = useState(0);
  const [loaded, setLoaded] = useState<Loaded<T> | null>(null);
  const request = `${key}#${reloads}`;
  const hasLoad = load !== null;
  // Always the latest `load`, without making the effect depend on its identity: its inputs are all in `key`.
  const fetchData = useEffectEvent(() => (load ? load() : Promise.reject(new Error('Nothing to load'))));

  useEffect(() => {
    if (!hasLoad) return undefined;
    let current = true;
    fetchData().then(
      (data) => {
        if (current) setLoaded({ key, request, data, error: null });
      },
      (error: unknown) => {
        if (!current) return;
        setLoaded((previous) => ({
          key,
          request,
          data: previous?.key === key ? previous.data : null,
          error: describeSupportError(error),
        }));
      }
    );
    return () => {
      current = false;
    };
  }, [key, request, hasLoad]);

  const reload = useCallback(() => setReloads((count) => count + 1), []);
  const update = useCallback((change: (data: T) => T) => {
    setLoaded((previous) => (previous && previous.data !== null ? { ...previous, data: change(previous.data) } : previous));
  }, []);

  const sameKey = loaded?.key === key ? loaded : null;
  return {
    data: sameKey?.data ?? null,
    error: sameKey?.error ?? null,
    loading: hasLoad && loaded?.request !== request,
    reload,
    update,
  };
}

/**
 * The Support Desk: file a ticket with the RoleSync team and follow the answers. Owners and
 * admins can also see every ticket of the workspace. The team answers from the Super Admin Console.
 */
export const Support: React.FC = () => {
  const toast = useToast();
  const workspaceId = useAppSelector((state) => state.workspace.currentWorkspace?.workspaceId) ?? '';
  const role = useAppSelector((state) => state.workspace.currentWorkspace?.role);
  const canSeeEveryone = role === 'OWNER' || role === 'ADMIN';

  const [subject, setSubject] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [everyoneWanted, setEveryone] = useState(false);
  const everyone = everyoneWanted && canSeeEveryone;
  const list = useLoad<SupportTicket[]>(
    workspaceId ? () => supportApi.list(everyone) : null,
    `${workspaceId}:${everyone}`
  );

  // The open ticket is remembered with its workspace, so switching workspace closes it.
  const [selection, setSelection] = useState<{ workspaceId: string; ticketId: string } | null>(null);
  const openId = selection && selection.workspaceId === workspaceId ? selection.ticketId : null;
  const open = useLoad<SupportTicket>(openId ? () => supportApi.get(openId) : null, `${workspaceId}:${openId ?? ''}`);
  const ticket = openId ? open.data : null;

  const [replyBody, setReplyBody] = useState('');
  const [replying, setReplying] = useState(false);

  const select = (ticketId: string | null) => {
    setSelection(ticketId ? { workspaceId, ticketId } : null);
    setReplyBody('');
  };

  /** Keeps the list row in step with a ticket we just loaded or changed. */
  const mergeIntoList = (changed: SupportTicket) =>
    list.update((rows) => {
      const summary = { ...changed, messages: null };
      return rows.some((row) => row.ticketId === changed.ticketId)
        ? rows.map((row) => (row.ticketId === changed.ticketId ? summary : row))
        : [summary, ...rows];
    });

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!subject.trim() || !description.trim() || submitting) return;
    setSubmitting(true);
    try {
      const created = await supportApi.create(subject.trim(), description.trim());
      setSubject('');
      setDescription('');
      mergeIntoList(created);
      select(created.ticketId);
      toast.success('The RoleSync team will answer here on your ticket.', 'Ticket sent');
    } catch (error) {
      toast.error(describeSupportError(error), 'Couldn’t send the ticket');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReply = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!ticket || !replyBody.trim() || replying) return;
    setReplying(true);
    try {
      const updated = await supportApi.reply(ticket.ticketId, replyBody.trim());
      open.update(() => updated);
      mergeIntoList(updated);
      setReplyBody('');
      if (ticket.status === 'RESOLVED' && updated.status === 'OPEN') {
        toast.info('Your message reopened the ticket for the team.', 'Reply sent');
      } else {
        toast.success('The team will see your reply on the ticket.', 'Reply sent');
      }
    } catch (error) {
      toast.error(describeSupportError(error), 'Couldn’t send the reply');
    } finally {
      setReplying(false);
    }
  };

  const tickets = list.data;

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-16">
      {/* Header */}
      <section className="space-y-2">
        <h2 className="font-serif text-3xl font-bold text-primary tracking-tight">Support Desk</h2>
        <p className="text-sm text-muted-foreground max-w-xl leading-relaxed">
          Tell the RoleSync team what’s wrong or what you need. They answer here, on your ticket, and you can write back
          until it’s closed.
        </p>
      </section>

      {!workspaceId ? (
        <div className="bg-card border border-border p-6 rounded-2xl shadow-2xs text-sm text-muted-foreground">
          Pick or create a workspace first.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-start">
          {/* New ticket */}
          <div className="lg:col-span-2 bg-card border border-border p-6 rounded-2xl shadow-2xs space-y-4">
            <div className="flex items-center gap-2 border-b border-border/60 pb-4">
              <MessageSquare className="w-5 h-5 text-primary" />
              <h3 className="font-serif text-lg font-bold text-foreground">File a ticket</h3>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4 text-left">
              <Input
                label="Subject"
                id="support-ticket-subject"
                type="text"
                value={subject}
                maxLength={200}
                onChange={(event) => setSubject(event.target.value)}
                placeholder="e.g. Product CSV import skips rows"
                disabled={submitting}
                required
              />

              <div className="space-y-1.5 w-full">
                <label htmlFor="support-ticket-desc" className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground block">
                  What happened
                </label>
                <textarea
                  id="support-ticket-desc"
                  rows={6}
                  value={description}
                  maxLength={5000}
                  onChange={(event) => setDescription(event.target.value)}
                  className={textareaClass}
                  placeholder="What you were doing, what you expected, and what happened instead. Include names of products, deals or documents if they matter."
                  disabled={submitting}
                  required
                />
                <p className="text-[11px] text-muted-foreground text-right tabular-nums">{description.length}/5000</p>
              </div>

              <div className="pt-1 flex justify-end">
                <Button
                  type="submit"
                  isLoading={submitting}
                  loadingText="Sending…"
                  icon={<Send className="w-4 h-4" />}
                  disabled={!subject.trim() || !description.trim()}
                  className="w-auto px-6 py-2.5 text-xs font-semibold rounded-xl"
                >
                  Send to support
                </Button>
              </div>
            </form>
          </div>

          {/* Tickets */}
          <div className="lg:col-span-3 bg-card border border-border p-6 rounded-2xl shadow-2xs space-y-4 min-h-[24rem]">
            <div className="flex items-center justify-between gap-3 border-b border-border/60 pb-4">
              <div className="flex items-center gap-2 min-w-0">
                {openId ? (
                  <button
                    type="button"
                    onClick={() => select(null)}
                    className="p-1 -ml-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
                    aria-label="Back to tickets"
                  >
                    <ArrowLeft className="w-4 h-4" />
                  </button>
                ) : (
                  <LifeBuoy className="w-5 h-5 text-primary shrink-0" />
                )}
                <h3 className="font-serif text-lg font-bold text-foreground truncate">
                  {openId ? (ticket?.subject ?? 'Ticket') : everyone ? 'Workspace tickets' : 'Your tickets'}
                </h3>
              </div>
              {!openId && (
                <div className="flex items-center gap-2 shrink-0">
                  {canSeeEveryone && (
                    <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={everyoneWanted}
                        onChange={(event) => setEveryone(event.target.checked)}
                        className="accent-primary"
                      />
                      Everyone’s tickets
                    </label>
                  )}
                  <button
                    type="button"
                    onClick={list.reload}
                    disabled={list.loading}
                    aria-label="Refresh tickets"
                    title="Refresh"
                    className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer disabled:opacity-50"
                  >
                    <RefreshCw className={`w-4 h-4 ${list.loading ? 'animate-spin' : ''}`} />
                  </button>
                </div>
              )}
            </div>

            {openId ? (
              open.error && !ticket ? (
                <div className="text-sm text-destructive py-6">{open.error}</div>
              ) : !ticket ? (
                <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading…
                </div>
              ) : (
                <div className="space-y-5">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                    <StatusBadge status={ticket.status} />
                    <span>{STATUS_META[ticket.status].hint}</span>
                    <span className="ml-auto" title={formatDateTime(ticket.createdAt)}>
                      {ticket.reporter.mine ? 'You' : ticket.reporter.name} · {timeAgo(ticket.createdAt)}
                    </span>
                  </div>

                  <div className="rounded-xl border border-border/60 bg-muted/20 px-4 py-3 text-sm text-foreground whitespace-pre-wrap leading-relaxed">
                    {ticket.description}
                  </div>

                  {ticket.messages && ticket.messages.length > 0 && (
                    <ol className="space-y-3">
                      {ticket.messages.map((message) => (
                        <li
                          key={message.messageId}
                          className={`rounded-xl border px-4 py-3 text-sm leading-relaxed ${
                            message.fromSupport ? 'border-violet-500/25 bg-violet-500/[0.06]' : 'border-border/60 bg-card'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-3 mb-1.5 text-[11px]">
                            <span className={`font-semibold ${message.fromSupport ? 'text-violet-700 dark:text-violet-300' : 'text-foreground'}`}>
                              {message.fromSupport ? 'RoleSync Support' : message.mine ? 'You' : message.authorName}
                            </span>
                            <span className="text-muted-foreground" title={formatDateTime(message.createdAt)}>
                              {timeAgo(message.createdAt)}
                            </span>
                          </div>
                          <div className="whitespace-pre-wrap text-foreground">{message.body}</div>
                        </li>
                      ))}
                    </ol>
                  )}

                  {ticket.canReply ? (
                    <form onSubmit={handleReply} className="space-y-2 pt-1">
                      <label htmlFor="support-ticket-reply" className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground block">
                        Write back
                      </label>
                      <textarea
                        id="support-ticket-reply"
                        rows={3}
                        value={replyBody}
                        maxLength={5000}
                        onChange={(event) => setReplyBody(event.target.value)}
                        className={textareaClass}
                        placeholder={ticket.status === 'RESOLVED' ? 'Still not working? Tell the team and the ticket reopens.' : 'Add details or answer the team’s question…'}
                        disabled={replying}
                      />
                      <div className="flex justify-end">
                        <Button
                          type="submit"
                          isLoading={replying}
                          loadingText="Sending…"
                          icon={<Send className="w-4 h-4" />}
                          disabled={!replyBody.trim()}
                          className="w-auto px-5 py-2 text-xs font-semibold rounded-xl"
                        >
                          Send reply
                        </Button>
                      </div>
                    </form>
                  ) : (
                    <p className="text-xs text-muted-foreground border-t border-border/60 pt-3">
                      This ticket is closed. If you still need help, file a new ticket.
                    </p>
                  )}
                </div>
              )
            ) : list.error && !tickets ? (
              <div className="text-sm text-destructive py-6">{list.error}</div>
            ) : !tickets ? (
              <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin" /> Loading tickets…
              </div>
            ) : tickets.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
                <Inbox className="w-8 h-8 text-muted-foreground/60" />
                <p className="text-sm font-semibold text-foreground">No tickets yet</p>
                <p className="text-xs text-muted-foreground max-w-xs">
                  {everyone
                    ? 'Nobody in this workspace has contacted support.'
                    : 'Anything you send to support shows up here with the team’s answers.'}
                </p>
              </div>
            ) : (
              <ul className={`divide-y divide-border/60 -mx-2 ${list.loading ? 'opacity-60' : ''}`}>
                {tickets.map((row) => (
                  <li key={row.ticketId}>
                    <button
                      type="button"
                      onClick={() => select(row.ticketId)}
                      className="w-full text-left px-2 py-3 rounded-lg hover:bg-muted/30 transition-colors cursor-pointer"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-foreground truncate">{row.subject}</p>
                          <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
                            {everyone && !row.reporter.mine ? `${row.reporter.name} · ` : ''}
                            {row.messageCount === 0
                              ? 'No replies yet'
                              : row.lastMessageFromSupport
                                ? `Support replied ${timeAgo(row.lastMessageAt)}`
                                : `${row.messageCount} ${row.messageCount === 1 ? 'reply' : 'replies'}`}
                            {' · '}
                            <span title={formatDateTime(row.createdAt)}>opened {timeAgo(row.createdAt)}</span>
                          </p>
                        </div>
                        <StatusBadge status={row.status} />
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
export default Support;
