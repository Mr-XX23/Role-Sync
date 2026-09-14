import React from 'react';
import { Link } from 'react-router-dom';
import { Ban, Coins, Plus } from 'lucide-react';
import { useCredits } from '../../context/creditsContext';
import { formatCredits, formatCreditsCompact, formatCreditsLabel } from '../../utils/billingFormat';

const TONE = {
  normal: 'border-border/80 text-foreground hover:bg-muted',
  warning: 'border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-200 hover:bg-amber-500/15',
  danger: 'border-red-500/35 bg-red-500/10 text-red-700 dark:text-red-300 hover:bg-red-500/15',
};

const focusRing = 'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30';

/**
 * The workspace's credit balance in the top bar, linking to the usage page, with a way to buy more.
 * Shows nothing until the balance has loaded, or when it can't be.
 */
export const CreditsChip: React.FC = () => {
  const { credits } = useCredits();
  if (!credits) return null;

  const suspended = credits.status === 'SUSPENDED';
  const empty = credits.balance <= 0;
  const tone = suspended || empty ? 'danger' : credits.lowBalance ? 'warning' : 'normal';
  const description = suspended
    ? 'Credits are suspended for this workspace'
    : empty
      ? 'This workspace is out of credits'
      : `${formatCredits(credits.balance)} credits available${credits.lowBalance ? ', running low' : ''}`;

  return (
    <div className="flex items-center gap-1.5 shrink-0">
      <Link
        to="/salesman/credits"
        title={`${description}. View credit usage.`}
        aria-label={`${description}. View credit usage.`}
        className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-xl border text-xs font-semibold tabular-nums whitespace-nowrap transition-colors ${TONE[tone]} ${focusRing}`}
      >
        {suspended ? (
          <Ban className="w-3.5 h-3.5 shrink-0" />
        ) : (
          <Coins className={`w-3.5 h-3.5 shrink-0 ${tone === 'normal' ? 'text-primary' : ''}`} />
        )}
        {suspended ? (
          'Suspended'
        ) : (
          <>
            <span className="sm:hidden">{formatCreditsCompact(credits.balance)}</span>
            <span className="hidden sm:inline">{formatCreditsLabel(credits.balance)}</span>
          </>
        )}
      </Link>
      <Link
        to="/pricing"
        title="Buy credits"
        className={`hidden md:flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-primary text-primary-foreground text-xs font-semibold whitespace-nowrap shadow-2xs hover:opacity-90 active:scale-[0.98] transition-all ${focusRing}`}
      >
        <Plus className="w-3.5 h-3.5" />
        Buy credits
      </Link>
    </div>
  );
};
