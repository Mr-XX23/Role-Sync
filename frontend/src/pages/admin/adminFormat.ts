import { parseServerTime } from '../salemans/userManagement/memberFormat';

export { formatDate, formatDateTime, initials, parseServerTime, timeAgo } from '../salemans/userManagement/memberFormat';

const integer = new Intl.NumberFormat();
const compact = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 });

export function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : integer.format(value);
}

/** 1,234 → "1.2K": for tokens and other large counts. */
export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return Math.abs(value) < 10000 ? integer.format(value) : compact.format(value);
}

/** Dollars. Fractions of a cent stay visible, because one agent call often costs less than a cent. */
export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (value === 0) return '$0.00';
  if (Math.abs(value) < 0.01) return `$${value.toFixed(4)}`;
  return value.toLocaleString(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatPrice(cents: number | null, currency: string): string {
  if (cents === null) return 'Custom';
  if (cents === 0) return 'Free';
  try {
    return (cents / 100).toLocaleString(undefined, { style: 'currency', currency, maximumFractionDigits: cents % 100 === 0 ? 0 : 2 });
  } catch {
    return `${(cents / 100).toFixed(2)} ${currency}`;
  }
}

/** "2026-09-14" (a UTC day) → "Sep 14". */
export function formatDay(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return day;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

export function shortId(value: string | null | undefined): string {
  return value ? value.slice(0, 8) : '—';
}

export function percent(part: number, whole: number): number {
  return whole > 0 ? Math.round((part / whole) * 100) : 0;
}

export function humanize(value: string): string {
  const text = value.replace(/[_:-]+/g, ' ').trim().toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function isRecent(value: string | null | undefined, days: number): boolean {
  const date = parseServerTime(value);
  return date !== null && Date.now() - date.getTime() <= days * 86400000;
}

/** Downloads rows as a CSV file (Excel-friendly: BOM, quoted cells). */
export function downloadCsv(filename: string, rows: (string | number | boolean | null | undefined)[][]): void {
  const cell = (value: string | number | boolean | null | undefined) => {
    const text = value === null || value === undefined ? '' : String(value);
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const body = rows.map((row) => row.map(cell).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob([`﻿${body}`], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
