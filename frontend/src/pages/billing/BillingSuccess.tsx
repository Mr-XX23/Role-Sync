import React from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Clock, Hourglass, Loader2, RefreshCw, RotateCcw, XCircle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { PaymentOrder } from '../../api/billingApi';
import { useCredits } from '../../context/creditsContext';
import { useAppSelector } from '../../store';
import { formatCredits, formatCreditsLabel, formatMoney } from '../../utils/billingFormat';
import { formatDateTime } from '../salemans/userManagement/memberFormat';
import { useOrderPolling } from './useOrderPolling';
import type { OrderPhase } from './useOrderPolling';

type Tone = 'progress' | 'success' | 'warning' | 'danger';

const TONE: Record<Tone, string> = {
  progress: 'bg-primary/10 text-primary border-primary/20',
  success: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/25',
  warning: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25',
  danger: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/25',
};

const primaryLink =
  'inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 active:scale-[0.98] transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40';
const outlineLink =
  'inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-background px-4 py-2.5 text-sm font-semibold text-foreground hover:bg-muted transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30';

interface View {
  tone: Tone;
  icon: LucideIcon;
  spin?: boolean;
  title: string;
  body: React.ReactNode;
}

function describe(phase: OrderPhase, order: PaymentOrder | null, error: string | null, workspaceName: string): View {
  if (phase === 'failed') {
    return { tone: 'danger', icon: AlertTriangle, title: 'We couldn’t check this payment', body: error ?? 'Try again in a moment.' };
  }
  if (phase === 'timeout') {
    return {
      tone: 'warning',
      icon: Hourglass,
      title: 'Your payment is still being confirmed',
      body: error
        ? `We couldn’t reach billing to confirm it (${error}). If you paid, your credits appear in your balance shortly.`
        : 'Stripe hasn’t confirmed it yet. Your credits appear in your balance shortly, and you can safely leave this page.',
    };
  }
  if (phase === 'checking' || !order) {
    return {
      tone: 'progress',
      icon: Loader2,
      spin: true,
      title: 'Confirming your payment…',
      body: 'Waiting for Stripe to confirm it. This usually takes a few seconds.',
    };
  }
  switch (order.status) {
    case 'SUCCEEDED':
      return {
        tone: 'success',
        icon: CheckCircle2,
        title: 'Payment received',
        body: (
          <>
            <span className="font-semibold text-foreground">{formatCreditsLabel(order.credits)}</span> were added to{' '}
            <span className="font-semibold text-foreground">{workspaceName}</span>. Everyone in the workspace can use them.
          </>
        ),
      };
    case 'EXPIRED':
      return {
        tone: 'warning',
        icon: Clock,
        title: 'Checkout expired',
        body: 'The checkout timed out before the payment was completed, so no credits were added. You can start a new one.',
      };
    case 'REFUNDED':
      return {
        tone: 'warning',
        icon: RotateCcw,
        title: 'This payment was refunded',
        body: 'The payment was refunded, so it doesn’t add credits. Contact support if that’s unexpected.',
      };
    default:
      return {
        tone: 'danger',
        icon: XCircle,
        title: 'Payment failed',
        body: `${order.failureReason ? `${order.failureReason}. ` : 'The payment didn’t go through. '}No credits were added.`,
      };
  }
}

const OrderDetails: React.FC<{ order: PaymentOrder }> = ({ order }) => (
  <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-3 rounded-xl border border-border/70 bg-muted/20 px-4 py-3 text-left">
    <div className="min-w-0">
      <dt className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground">Pack</dt>
      <dd className="text-sm text-foreground truncate">{order.packageCode}</dd>
    </div>
    <div className="min-w-0">
      <dt className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground">Credits</dt>
      <dd className="text-sm text-foreground tabular-nums">{formatCredits(order.credits)}</dd>
    </div>
    <div className="min-w-0">
      <dt className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground">Amount</dt>
      <dd className="text-sm text-foreground tabular-nums">{formatMoney(order.amountMinor, order.currency)}</dd>
    </div>
    <div className="min-w-0">
      <dt className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground">
        {order.paidAt ? 'Paid' : 'Started'}
      </dt>
      <dd className="text-sm text-foreground">{formatDateTime(order.paidAt ?? order.createdAt)}</dd>
    </div>
  </dl>
);

const ResultCard: React.FC<{ view: View; order?: PaymentOrder | null; children: React.ReactNode }> = ({ view, order, children }) => {
  const Icon = view.icon;
  return (
    <div className="min-h-full flex items-start sm:items-center justify-center py-6 sm:py-12">
      <section
        aria-live="polite"
        aria-busy={view.tone === 'progress'}
        className="w-full max-w-lg bg-card border border-border/80 rounded-2xl shadow-2xs p-6 sm:p-8 text-center animate-in fade-in duration-300"
      >
        <div className={`mx-auto w-14 h-14 rounded-2xl border flex items-center justify-center ${TONE[view.tone]}`}>
          <Icon className={`w-7 h-7 ${view.spin ? 'animate-spin' : ''}`} />
        </div>
        <h2 className="mt-5 font-serif text-2xl font-bold text-foreground">{view.title}</h2>
        <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{view.body}</p>
        {order && <OrderDetails order={order} />}
        <div className="mt-6 flex flex-wrap justify-center gap-2">{children}</div>
      </section>
    </div>
  );
};

/**
 * Where Stripe sends the buyer back to (`/billing/success?orderId=…`). Follows the order until the
 * payment settles, then refreshes the workspace's balance.
 */
export const BillingSuccess: React.FC = () => {
  const [searchParams] = useSearchParams();
  const orderId = searchParams.get('orderId')?.trim() || null;
  const { credits, refresh } = useCredits();
  const workspaceName = useAppSelector((state) => state.workspace.currentWorkspace?.name) ?? 'your workspace';
  const poll = useOrderPolling(orderId, {
    onSettled: (order) => {
      if (order.status === 'SUCCEEDED') refresh();
    },
  });

  if (!orderId) {
    return (
      <ResultCard
        view={{
          tone: 'warning',
          icon: AlertTriangle,
          title: 'No payment to show',
          body: 'This page needs the order from your checkout. If you just paid, your credits appear in your balance shortly.',
        }}
      >
        <Link to="/salesman/credits" className={primaryLink}>
          View credits
        </Link>
        <Link to="/pricing" className={outlineLink}>
          See pricing
        </Link>
      </ResultCard>
    );
  }

  const view = describe(poll.phase, poll.order, poll.error, workspaceName);
  const succeeded = poll.phase === 'settled' && poll.order?.status === 'SUCCEEDED';
  const settledWithoutCredits = poll.phase === 'settled' && !succeeded;

  return (
    <ResultCard view={view} order={poll.order}>
      {succeeded && (
        <>
          {credits && (
            <p className="w-full text-xs text-muted-foreground mb-1">
              Balance now: <span className="font-semibold text-foreground tabular-nums">{formatCreditsLabel(credits.balance)}</span>
            </p>
          )}
          <Link to="/salesman/credits" className={primaryLink}>
            View credit usage
          </Link>
          <Link to="/salesman/sales-agent" className={outlineLink}>
            Back to the sales agent
          </Link>
        </>
      )}
      {settledWithoutCredits && (
        <>
          <Link to="/pricing" className={primaryLink}>
            Back to pricing
          </Link>
          <Link to="/salesman/support" className={outlineLink}>
            Contact support
          </Link>
        </>
      )}
      {(poll.phase === 'timeout' || poll.phase === 'failed') && (
        <>
          <button type="button" onClick={poll.retry} className={primaryLink}>
            <RefreshCw className="w-4 h-4" />
            Check again
          </button>
          <Link to="/salesman/credits" className={outlineLink}>
            View credits
          </Link>
          <Link to="/pricing" className={outlineLink}>
            Pricing
          </Link>
        </>
      )}
    </ResultCard>
  );
};

export default BillingSuccess;
