import React, { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { Send, ShieldCheck } from 'lucide-react';
import { adminApi, describeAdminError } from '../../api/adminApi';
import type { SupportTicketStatus } from '../../api/adminApi';
import { Button } from '../../components/common/Button';
import { useToast } from '../../context/ToastContext';
import { Badge, Drawer, ErrorBlock, KeyValue, LoadingBlock, Notice, inputClass, labelClass, selectClass } from './components/AdminUi';
import { formatDateTime, timeAgo } from './adminFormat';
import { useAdminQuery } from './useAdminQuery';
import { TICKET_STATUSES, TICKET_STATUS_META } from './supportMeta';

/** One ticket for the RoleSync team: the conversation, a reply box and the status controls. */
export const SupportTicketDrawer: React.FC<{
  ticketId: string;
  onClose: () => void;
  onChanged: () => void;
}> = ({ ticketId, onClose, onChanged }) => {
  const toast = useToast();
  const detail = useAdminQuery(() => adminApi.supportTicket(ticketId), `support-ticket:${ticketId}`);
  const [reply, setReply] = useState('');
  const [sending, setSending] = useState(false);
  const [nextStatus, setNextStatus] = useState<SupportTicketStatus | ''>('');
  const [note, setNote] = useState('');
  const [savingStatus, setSavingStatus] = useState(false);
  const replyId = useId();
  const statusId = useId();
  const noteId = useId();

  const ticket = detail.data?.ticket;
  const busy = sending || savingStatus;

  const sendReply = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!ticket || !reply.trim() || busy) return;
    setSending(true);
    try {
      const updated = await adminApi.replySupportTicket(ticket.ticket_id, reply.trim());
      detail.update(() => updated);
      setReply('');
      onChanged();
      toast.success(`${ticket.reporter.name} sees it on their ticket.`, 'Reply sent');
    } catch (error) {
      toast.error(describeAdminError(error), 'Couldn’t send the reply');
    } finally {
      setSending(false);
    }
  };

  const saveStatus = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!ticket || !nextStatus || nextStatus === ticket.status || busy) return;
    setSavingStatus(true);
    try {
      const updated = await adminApi.setSupportTicketStatus(ticket.ticket_id, nextStatus, note.trim() || null);
      detail.update(() => updated);
      setNextStatus('');
      setNote('');
      onChanged();
      toast.success(`The ticket is now ${TICKET_STATUS_META[nextStatus].label.toLowerCase()}.`, 'Status changed');
    } catch (error) {
      toast.error(describeAdminError(error), 'Couldn’t change the status');
    } finally {
      setSavingStatus(false);
    }
  };

  const currentMeta = ticket ? TICKET_STATUS_META[ticket.status] : null;

  return (
    <Drawer
      title={ticket?.subject ?? 'Support ticket'}
      subtitle={
        ticket ? (
          <span className="flex items-center gap-2">
            <Badge tone={currentMeta!.tone}>{currentMeta!.label}</Badge>
            <span>Opened {formatDateTime(ticket.created_at)}</span>
          </span>
        ) : undefined
      }
      onClose={onClose}
      width="max-w-2xl"
    >
      {detail.error && !detail.data ? (
        <ErrorBlock message={detail.error} onRetry={detail.reload} />
      ) : !ticket || !detail.data ? (
        <LoadingBlock />
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
            <KeyValue label="Workspace">
              <Link to={`/admin/workspaces?open=${encodeURIComponent(ticket.workspace.workspace_id)}`} className="hover:underline">
                {ticket.workspace.name}
              </Link>
              {!ticket.workspace.is_active && (
                <Badge tone="danger" className="ml-2">
                  Suspended
                </Badge>
              )}
            </KeyValue>
            <KeyValue label="Reporter">
              <span className="block">{ticket.reporter.name}</span>
              <span className="block text-xs text-muted-foreground">{ticket.reporter.email ?? 'Email unavailable'}</span>
            </KeyValue>
            <KeyValue label="Last activity">{timeAgo(ticket.updated_at)}</KeyValue>
            <KeyValue label="Replies">
              {ticket.message_count}
              {!ticket.last_message_from_support && (ticket.status === 'OPEN' || ticket.status === 'IN_PROGRESS') && (
                <span className="ml-2 text-xs text-amber-700 dark:text-amber-300">awaiting your reply</span>
              )}
            </KeyValue>
          </dl>

          <section className="space-y-2">
            <h4 className={labelClass}>What they wrote</h4>
            <div className="rounded-xl border border-border/60 bg-muted/20 px-4 py-3 text-sm text-foreground whitespace-pre-wrap leading-relaxed">
              {detail.data.description}
            </div>
          </section>

          {detail.data.messages.length > 0 && (
            <section className="space-y-2">
              <h4 className={labelClass}>Conversation</h4>
              <ol className="space-y-3">
                {detail.data.messages.map((message) => (
                  <li
                    key={message.message_id}
                    className={`rounded-xl border px-4 py-3 text-sm leading-relaxed ${
                      message.from_support ? 'border-violet-500/25 bg-violet-500/[0.06]' : 'border-border/60 bg-card'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3 mb-1.5 text-[11px]">
                      <span className={`font-semibold flex items-center gap-1 ${message.from_support ? 'text-violet-700 dark:text-violet-300' : 'text-foreground'}`}>
                        {message.from_support && <ShieldCheck className="w-3 h-3" />}
                        {message.author_name}
                      </span>
                      <span className="text-muted-foreground" title={formatDateTime(message.created_at)}>
                        {timeAgo(message.created_at)}
                      </span>
                    </div>
                    <div className="whitespace-pre-wrap text-foreground">{message.body}</div>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {ticket.status === 'CLOSED' ? (
            <Notice tone="info">This ticket is closed. Reopen it below to reply.</Notice>
          ) : (
            <form onSubmit={sendReply} className="space-y-2">
              <label htmlFor={replyId} className={labelClass}>
                Reply as RoleSync Support
              </label>
              <textarea
                id={replyId}
                rows={4}
                value={reply}
                maxLength={5000}
                disabled={busy}
                onChange={(event) => setReply(event.target.value)}
                className={`${inputClass} resize-none`}
                placeholder="What you found, what to try, or what you need from them…"
              />
              <div className="flex items-center justify-between gap-3">
                <span className="text-[11px] text-muted-foreground">
                  {ticket.status === 'OPEN' ? 'Sending the first reply moves the ticket to “In progress”.' : 'They see this on their ticket right away.'}
                </span>
                <Button
                  type="submit"
                  className="px-4 py-2 w-auto text-xs"
                  icon={<Send className="w-3.5 h-3.5" />}
                  isLoading={sending}
                  loadingText="Sending…"
                  disabled={!reply.trim() || busy}
                >
                  Send reply
                </Button>
              </div>
            </form>
          )}

          <form onSubmit={saveStatus} className="space-y-3 rounded-2xl border border-border/70 bg-muted/10 p-4">
            <div className="space-y-1">
              <label htmlFor={statusId} className={labelClass}>
                Change status
              </label>
              <select
                id={statusId}
                value={nextStatus}
                disabled={busy}
                onChange={(event) => setNextStatus(event.target.value as SupportTicketStatus | '')}
                className={`${selectClass} w-full`}
              >
                <option value="">Keep “{currentMeta!.label}”</option>
                {TICKET_STATUSES.filter((value) => value !== ticket.status).map((value) => (
                  <option key={value} value={value}>
                    {TICKET_STATUS_META[value].label}
                  </option>
                ))}
              </select>
              {nextStatus && <p className="text-[11px] text-muted-foreground">{TICKET_STATUS_META[nextStatus].description}</p>}
            </div>
            {nextStatus && (
              <div className="space-y-1">
                <label htmlFor={noteId} className={labelClass}>
                  Note <span className="normal-case font-normal tracking-normal">(optional, kept in the audit log, not shown to the reporter)</span>
                </label>
                <input
                  id={noteId}
                  type="text"
                  value={note}
                  maxLength={500}
                  disabled={busy}
                  onChange={(event) => setNote(event.target.value)}
                  className={inputClass}
                  placeholder="Why?"
                />
              </div>
            )}
            <div className="flex justify-end">
              <Button
                type="submit"
                variant={nextStatus === 'CLOSED' ? 'destructive' : 'outline'}
                className="px-4 py-2 w-auto text-xs"
                isLoading={savingStatus}
                loadingText="Saving…"
                disabled={!nextStatus || busy}
              >
                {nextStatus ? `Mark as ${TICKET_STATUS_META[nextStatus].label.toLowerCase()}` : 'Update status'}
              </Button>
            </div>
          </form>
        </>
      )}
    </Drawer>
  );
};
