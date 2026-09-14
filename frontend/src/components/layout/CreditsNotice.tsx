import React from 'react';
import { Link } from 'react-router-dom';
import { Ban, Coins, X } from 'lucide-react';
import { useCredits } from '../../context/creditsContext';

const link =
  'inline-flex items-center px-2.5 py-1 rounded-lg text-[11px] font-semibold whitespace-nowrap transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30';

/**
 * Shown under the top bar after an API refused a paid operation (HTTP 402). It doesn't block
 * anything: people can keep working with everything that doesn't need credits.
 */
export const CreditsNotice: React.FC = () => {
  const { notice, dismissNotice } = useCredits();
  if (!notice) return null;
  const suspended = notice.code === 'CREDITS_SUSPENDED';

  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex flex-wrap items-center gap-x-3 gap-y-2 px-4 md:px-8 py-2.5 border-b text-xs ${
        suspended
          ? 'bg-red-500/10 border-red-500/25 text-red-800 dark:text-red-200'
          : 'bg-amber-500/10 border-amber-500/30 text-amber-900 dark:text-amber-100'
      }`}
    >
      {suspended ? <Ban className="w-4 h-4 shrink-0" /> : <Coins className="w-4 h-4 shrink-0" />}
      <p className="flex-1 min-w-[12rem] leading-snug">
        <span className="font-semibold">
          {suspended ? 'Credits are suspended — contact support.' : 'Your workspace is out of credits.'}
        </span>{' '}
        <span className="opacity-90">
          {suspended
            ? 'New AI actions can’t start until the RoleSync team reactivates them.'
            : 'New AI actions are paused until credits are added. Anything already running finishes.'}
        </span>
      </p>
      <div className="flex items-center gap-1.5 shrink-0">
        {suspended && (
          <Link to="/salesman/support" className={`${link} border border-current/25 hover:bg-red-500/10`}>
            Contact support
          </Link>
        )}
        <Link
          to="/pricing"
          className={`${link} ${suspended ? 'border border-current/25 hover:bg-red-500/10' : 'bg-primary text-primary-foreground hover:opacity-90'}`}
        >
          {suspended ? 'Pricing' : 'Buy credits'}
        </Link>
        <button
          type="button"
          onClick={dismissNotice}
          aria-label="Dismiss notice"
          className="p-1 rounded-md opacity-70 hover:opacity-100 transition-opacity cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
};
