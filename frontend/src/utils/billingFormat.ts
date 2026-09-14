import type { CreditPackage } from '../api/billingApi';

// Formatting for credits and money, shared by the pricing page, the workspace dashboard and the console.

const wholeNumber = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
const oneDecimal = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });
const compactNumber = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 });

function missing(value: number | null | undefined): value is null | undefined {
  return value === null || value === undefined || !Number.isFinite(value);
}

/** A balance in whole credits, rounded down as everywhere credits are shown: 487.9 → "487". */
export function formatCredits(value: number | null | undefined): string {
  return missing(value) ? '—' : wholeNumber.format(Math.floor(value));
}

/** "487 credits", "1 credit". */
export function formatCreditsLabel(value: number | null | undefined): string {
  if (missing(value)) return '—';
  const whole = Math.floor(value);
  return `${wholeNumber.format(whole)} ${whole === 1 ? 'credit' : 'credits'}`;
}

/** Short balance for tight spaces: 487, 12.5K. */
export function formatCreditsCompact(value: number | null | undefined): string {
  if (missing(value)) return '—';
  const whole = Math.floor(value);
  return Math.abs(whole) < 10000 ? wholeNumber.format(whole) : compactNumber.format(whole);
}

/** An amount used, where a fraction of a credit still matters: 2.565 → "2.6". */
export function formatCreditAmount(value: number | null | undefined): string {
  return missing(value) ? '—' : oneDecimal.format(value);
}

export function formatPercent(value: number | null | undefined): string {
  return missing(value) ? '—' : `${oneDecimal.format(value)}%`;
}

function fractionDigits(currency: string): number {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: currency.toUpperCase() }).resolvedOptions()
      .maximumFractionDigits ?? 2;
  } catch {
    return 2;
  }
}

/**
 * Money from the currency's minor unit: (1000, "usd") → "$10.00". `trimZeros` drops ".00" from
 * whole amounts ("$10"), for prices.
 */
export function formatMoney(minor: number | null | undefined, currency: string, { trimZeros = false } = {}): string {
  if (missing(minor)) return '—';
  const digits = fractionDigits(currency);
  const major = minor / 10 ** digits;
  const whole = Number.isInteger(major);
  try {
    return major.toLocaleString(undefined, {
      style: 'currency',
      currency: currency.toUpperCase(),
      minimumFractionDigits: trimZeros && whole ? 0 : digits,
      maximumFractionDigits: digits,
    });
  } catch {
    return `${major.toFixed(digits)} ${currency.toUpperCase()}`;
  }
}

/** What one credit costs in a pack: "$0.009". */
export function formatPerCredit(pkg: CreditPackage): string {
  if (!(pkg.credits > 0)) return '—';
  const major = pkg.priceMinor / 10 ** fractionDigits(pkg.currency) / pkg.credits;
  try {
    return major.toLocaleString(undefined, {
      style: 'currency',
      currency: pkg.currency.toUpperCase(),
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    });
  } catch {
    return `${major.toFixed(4)} ${pkg.currency.toUpperCase()}`;
  }
}

/** Dollars for costs; fractions of a cent stay visible because single operations cost less than one. */
export function formatUsd(value: number | null | undefined): string {
  if (missing(value)) return '—';
  if (value === 0) return '$0.00';
  if (Math.abs(value) < 0.01) return `$${value.toFixed(4)}`;
  return value.toLocaleString(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function perCredit(pkg: CreditPackage): number {
  return pkg.credits > 0 ? pkg.priceMinor / pkg.credits : Number.POSITIVE_INFINITY;
}

/**
 * The pack with the cheapest credits, when packs differ at all (ties go to the bigger pack). Packs
 * in other currencies than the first aren't compared.
 */
export function bestValueCode(packages: CreditPackage[]): string | null {
  const comparable = packages.filter((pkg) => pkg.credits > 0 && pkg.currency === packages[0]?.currency);
  if (comparable.length < 2) return null;
  const sorted = [...comparable].sort((a, b) => perCredit(a) - perCredit(b) || b.credits - a.credits);
  return perCredit(sorted[0]) < perCredit(sorted[sorted.length - 1]) ? sorted[0].code : null;
}

/** How much cheaper a pack's credits are than the dearest pack's, in whole percent (0 when not). */
export function savingsPercent(pkg: CreditPackage, packages: CreditPackage[]): number {
  const comparable = packages.filter((other) => other.credits > 0 && other.currency === pkg.currency);
  const dearest = Math.max(...comparable.map(perCredit));
  if (!Number.isFinite(dearest) || dearest <= 0) return 0;
  return Math.max(0, Math.round((1 - perCredit(pkg) / dearest) * 100));
}

/** "2026-09-14" or a full timestamp → "Sep 14" (UTC day). */
export function formatDayLabel(day: string): string {
  const date = new Date(`${day.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return day;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' });
}
