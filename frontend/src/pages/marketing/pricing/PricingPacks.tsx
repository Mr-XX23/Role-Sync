import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Check, Gift, Loader2, Sparkles } from 'lucide-react';
import type { CreditPackage } from '../../../api/billingApi';
import {
  bestValueCode,
  formatCredits,
  formatMoney,
  formatPerCredit,
  savingsPercent,
} from '../../../utils/billingFormat';
import type { Checkout } from './useCheckout';

const cardBase = 'relative flex flex-col h-full rounded-2xl border bg-card p-6 shadow-2xs transition-shadow duration-300 hover:shadow-md';
const buttonBase =
  'mt-6 group inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:cursor-not-allowed disabled:opacity-60';

const Perk: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <li className="flex items-start gap-2">
    <Check className="w-3.5 h-3.5 mt-0.5 text-emerald-500 shrink-0" />
    <span>{children}</span>
  </li>
);

/** The free credits every new account's workspace gets. */
const FreeOfferCard: React.FC<{ signupCredits: number; signedIn: boolean }> = ({ signupCredits, signedIn }) => (
  <div className={`${cardBase} border-dashed border-border`}>
    <div className="flex items-center justify-between gap-2">
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">Free to start</p>
      <Gift className="w-4 h-4 text-primary" />
    </div>
    <p className="mt-3 font-serif text-4xl tracking-tight text-foreground">$0</p>
    <p className="mt-1 text-sm font-semibold text-foreground">{formatCredits(signupCredits)} credits</p>
    <p className="mt-1 text-xs text-muted-foreground">When you create your account</p>
    <ul className="mt-5 space-y-2 text-xs text-muted-foreground flex-1">
      <Perk>No card required</Perk>
      <Perk>Added to your workspace once per account</Perk>
      <Perk>Top up with a pack whenever you like</Perk>
    </ul>
    <Link
      to={signedIn ? '/salesman' : '/register'}
      className={`${buttonBase} border border-border bg-background text-foreground hover:bg-muted`}
    >
      {signedIn ? 'Open dashboard' : 'Create a free account'}
      <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
    </Link>
  </div>
);

const PackCard: React.FC<{
  pkg: CreditPackage;
  best: boolean;
  savings: number;
  disabled: boolean;
  checkout: Checkout;
  onBuy: (pkg: CreditPackage) => void;
}> = ({ pkg, best, savings, disabled, checkout, onBuy }) => {
  const pending = checkout.pendingCode === pkg.code;
  const error = checkout.error?.code === pkg.code ? checkout.error.message : null;
  const errorId = `pack-error-${pkg.code}`;
  return (
    <div className={`${cardBase} ${best ? 'border-primary/50 ring-1 ring-primary/30 shadow-lg' : 'border-border/80'}`}>
      {best && (
        <span className="absolute -top-3 left-6 inline-flex items-center gap-1 rounded-full bg-primary px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-wider text-primary-foreground shadow-xs">
          <Sparkles className="w-3 h-3" />
          Best value
        </span>
      )}
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">{pkg.name}</p>
      <p className="mt-3 font-serif text-4xl tracking-tight text-foreground">
        {formatMoney(pkg.priceMinor, pkg.currency, { trimZeros: true })}
      </p>
      <p className="mt-1 text-sm font-semibold text-foreground">{formatCredits(pkg.credits)} credits</p>
      <p className="mt-1 text-xs text-muted-foreground">
        {formatPerCredit(pkg)} per credit
        {savings > 0 && <span className="ml-1.5 font-semibold text-emerald-600 dark:text-emerald-400">Save {savings}%</span>}
      </p>
      <ul className="mt-5 space-y-2 text-xs text-muted-foreground flex-1">
        <Perk>Never expires</Perk>
        <Perk>Shared by everyone in the workspace</Perk>
        <Perk>One-time payment, nothing renews</Perk>
      </ul>
      {/* Above the button, so buttons stay level across the row. */}
      {error && (
        <p id={errorId} role="alert" className="mt-4 -mb-2 text-xs text-destructive leading-snug">
          {error}
        </p>
      )}
      <button
        type="button"
        onClick={() => onBuy(pkg)}
        disabled={disabled}
        aria-describedby={error ? errorId : undefined}
        className={`${buttonBase} ${
          best
            ? 'bg-primary text-primary-foreground shadow-md hover:opacity-90 active:scale-[0.98]'
            : 'border border-primary/40 bg-primary/10 text-primary hover:bg-primary/15 active:scale-[0.98]'
        }`}
      >
        {pending ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            {checkout.redirecting ? 'Opening secure checkout…' : 'Starting checkout…'}
          </>
        ) : (
          <>
            Buy {pkg.name}
            <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
          </>
        )}
      </button>
    </div>
  );
};

export const PricingPacks: React.FC<{
  packages: CreditPackage[];
  signupCredits: number;
  signedIn: boolean;
  /** Buying is possible right now (the workspace is known, no checkout is starting). */
  canBuy: boolean;
  checkout: Checkout;
  onBuy: (pkg: CreditPackage) => void;
}> = ({ packages, signupCredits, signedIn, canBuy, checkout, onBuy }) => {
  const best = bestValueCode(packages);
  return (
    <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4 pt-3">
      <FreeOfferCard signupCredits={signupCredits} signedIn={signedIn} />
      {packages.map((pkg) => (
        <PackCard
          key={pkg.code}
          pkg={pkg}
          best={pkg.code === best}
          savings={savingsPercent(pkg, packages)}
          disabled={!canBuy || checkout.pendingCode !== null}
          checkout={checkout}
          onBuy={onBuy}
        />
      ))}
    </div>
  );
};

export const PricingPacksSkeleton: React.FC = () => (
  <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4 pt-3" aria-busy="true" aria-label="Loading prices">
    {[0, 1, 2, 3].map((index) => (
      <div key={index} className={`${cardBase} border-border/80`}>
        <div className="h-3 w-20 rounded mk-shimmer" />
        <div className="mt-4 h-9 w-24 rounded mk-shimmer" />
        <div className="mt-3 h-3 w-28 rounded mk-shimmer" />
        <div className="mt-6 space-y-2 flex-1">
          <div className="h-2.5 w-4/5 rounded mk-shimmer" />
          <div className="h-2.5 w-3/5 rounded mk-shimmer" />
        </div>
        <div className="mt-6 h-10 w-full rounded-lg mk-shimmer" />
      </div>
    ))}
  </div>
);
