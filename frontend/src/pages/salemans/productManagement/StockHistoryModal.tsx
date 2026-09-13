import React, { useState, useEffect, useMemo } from 'react';
import { X, History, Loader2, AlertCircle, RefreshCw } from 'lucide-react';
import {
  catalogApi,
  type Variant,
  type Location,
  type Product,
  type StockMovementEntry,
  type StockMovementSummaryResponse,
} from '../../../api/catalogApi';
import { useAppSelector } from '../../../store';
import { SearchableSelect, type DropdownOption } from './SearchableSelect';
import {
  ENTRY_STYLES,
  HISTORY_FILTERS,
  type HistoryFilter,
  describeVariant,
  formatLocationType,
} from './stockMovementLabels';

interface StockHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  variants: Variant[];
  products: Product[];
  locations: Location[];
  initialVariantId?: string;
  initialLocationId?: string;
}

type Period = 'today' | '7d' | '30d' | 'month' | 'all' | 'custom';

const PERIODS: { key: Period; label: string }[] = [
  { key: 'today', label: 'Today' },
  { key: '7d', label: 'Last 7 days' },
  { key: '30d', label: 'Last 30 days' },
  { key: 'month', label: 'This month' },
  { key: 'all', label: 'All time' },
  { key: 'custom', label: 'Custom range' },
];

const PAGE_SIZE = 50;

const daysAgo = (days: number): Date => {
  const date = new Date();
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() - days);
  return date;
};

/** The period as an inclusive start and exclusive end, in the viewer's time zone. */
const periodRange = (period: Period, customFrom: string, customTo: string): { date_from?: string; date_to?: string } => {
  switch (period) {
    case 'today':
      return { date_from: daysAgo(0).toISOString() };
    case '7d':
      return { date_from: daysAgo(6).toISOString() };
    case '30d':
      return { date_from: daysAgo(29).toISOString() };
    case 'month': {
      const now = new Date();
      return { date_from: new Date(now.getFullYear(), now.getMonth(), 1).toISOString() };
    }
    case 'custom': {
      const range: { date_from?: string; date_to?: string } = {};
      if (customFrom) range.date_from = new Date(`${customFrom}T00:00:00`).toISOString();
      if (customTo) {
        const end = new Date(`${customTo}T00:00:00`);
        end.setDate(end.getDate() + 1);
        range.date_to = end.toISOString();
      }
      return range;
    }
    default:
      return {};
  }
};

const errorDetail = (err: unknown, fallback: string): string => {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
};

const formatWhen = (at: string) =>
  new Date(at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });

const signed = (value: number) => (value > 0 ? `+${value}` : value < 0 ? `−${Math.abs(value)}` : '0');

const TOTAL_COLUMNS: { key: 'received' | 'sold' | 'shipped_out' | 'shipped_in' | 'damaged' | 'lost' | 'returned'; label: string }[] = [
  { key: 'received', label: 'Received' },
  { key: 'sold', label: 'Sold' },
  { key: 'shipped_out', label: 'Shipped out' },
  { key: 'shipped_in', label: 'Shipped in' },
  { key: 'damaged', label: 'Damaged' },
  { key: 'lost', label: 'Lost' },
  { key: 'returned', label: 'Returned' },
];

export const StockHistoryModal: React.FC<StockHistoryModalProps> = ({
  isOpen,
  onClose,
  variants,
  products,
  locations,
  initialVariantId,
  initialLocationId,
}) => {
  const me = useAppSelector((state) => state.auth.user?.userId);

  // The parent mounts this modal when it opens, so every open starts from these filters.
  const [tab, setTab] = useState<'history' | 'totals'>('history');
  const [variantId, setVariantId] = useState<string>(initialVariantId ?? '');
  const [locationId, setLocationId] = useState<string>(initialLocationId ?? '');
  const [period, setPeriod] = useState<Period>('30d');
  const [customFrom, setCustomFrom] = useState<string>('');
  const [customTo, setCustomTo] = useState<string>('');
  const [filter, setFilter] = useState<HistoryFilter>('ALL');
  const [reloads, setReloads] = useState(0);

  // Each answer is kept with the query it answers; anything else on screen is still loading.
  const [history, setHistory] = useState<{ key: string; entries: StockMovementEntry[]; total: number } | null>(null);
  const [totals, setTotals] = useState<{ key: string; summary: StockMovementSummaryResponse } | null>(null);
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);

  const { date_from: dateFrom, date_to: dateTo } = useMemo(
    () => periodRange(period, customFrom, customTo),
    [period, customFrom, customTo]
  );
  const queryKey = JSON.stringify([tab, variantId, locationId, dateFrom, dateTo, filter, reloads]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    const scope = {
      variant_id: variantId || undefined,
      location_id: locationId || undefined,
      date_from: dateFrom,
      date_to: dateTo,
    };
    const request =
      tab === 'history'
        ? catalogApi
            .listMovements({
              ...scope,
              reasons: HISTORY_FILTERS.find((f) => f.key === filter)?.reasons,
              limit: PAGE_SIZE,
            })
            .then((page) => {
              if (!cancelled) setHistory({ key: queryKey, entries: page.items, total: page.total });
            })
        : catalogApi.getMovementSummary(scope).then((summary) => {
            if (!cancelled) setTotals({ key: queryKey, summary });
          });
    request.catch((err) => {
      if (!cancelled) setFailure({ key: queryKey, message: errorDetail(err, 'Could not load stock history.') });
    });
    return () => {
      cancelled = true;
    };
  }, [isOpen, queryKey, tab, variantId, locationId, dateFrom, dateTo, filter]);

  if (!isOpen) return null;

  const error = failure?.key === queryKey ? failure.message : null;
  const entries = history?.key === queryKey ? history.entries : [];
  const total = history?.key === queryKey ? history.total : 0;
  const summary = totals?.key === queryKey ? totals.summary : null;
  const isLoading = !error && (tab === 'history' ? history?.key !== queryKey : totals?.key !== queryKey);
  const retry = () => setReloads((n) => n + 1);

  const loadMore = async () => {
    const key = queryKey;
    setIsLoadingMore(true);
    try {
      const page = await catalogApi.listMovements({
        variant_id: variantId || undefined,
        location_id: locationId || undefined,
        date_from: dateFrom,
        date_to: dateTo,
        reasons: HISTORY_FILTERS.find((f) => f.key === filter)?.reasons,
        limit: PAGE_SIZE,
        offset: entries.length,
      });
      setHistory((current) =>
        current && current.key === key
          ? { key, entries: [...current.entries, ...page.items], total: page.total }
          : current
      );
    } catch (err) {
      setFailure({ key, message: errorDetail(err, 'Could not load more stock history.') });
    } finally {
      setIsLoadingMore(false);
    }
  };

  const productOptions: DropdownOption[] = [
    { value: '', label: 'All products' },
    ...variants.map((v) => ({ value: v.id, label: describeVariant(v, products), sub: `SKU: ${v.sku}` })),
  ];
  const locationOptions: DropdownOption[] = [
    { value: '', label: 'All locations' },
    ...locations.map((l) => ({ value: l.id, label: l.name, sub: formatLocationType(l.type) })),
  ];

  const stockNow = summary
    ? summary.locations.reduce(
        (sum, place) => ({
          onHand: sum.onHand + place.qty_on_hand,
          reserved: sum.reserved + place.qty_reserved,
          available: sum.available + place.qty_available,
        }),
        { onHand: 0, reserved: 0, available: 0 }
      )
    : null;

  const inputClass =
    'w-full px-3 py-2.5 text-xs rounded-xl bg-background border border-border/80 text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/40';

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs animate-in fade-in duration-200">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="stock-history-title"
        className="relative w-full max-w-6xl bg-card border border-border/80 rounded-2xl shadow-2xl flex flex-col max-h-[90vh]"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-border/60 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
              <History className="w-5 h-5" />
            </div>
            <div>
              <h3 id="stock-history-title" className="font-semibold text-foreground text-base">
                Stock History
              </h3>
              <p className="text-xs text-muted-foreground">
                Every change to stock, and the totals for each location
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center p-1 rounded-xl bg-muted/50 border border-border/60" role="tablist">
              {(
                [
                  { key: 'history', label: 'Movements' },
                  { key: 'totals', label: 'Totals by location' },
                ] as const
              ).map((option) => (
                <button
                  key={option.key}
                  type="button"
                  role="tab"
                  aria-selected={tab === option.key}
                  onClick={() => setTab(option.key)}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                    tab === option.key ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="px-6 py-3.5 border-b border-border/50 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div>
            <label htmlFor="history-product" className="block text-[11px] font-medium text-muted-foreground mb-1">
              Product
            </label>
            <SearchableSelect
              id="history-product"
              options={productOptions}
              value={variantId}
              onChange={setVariantId}
              searchable
            />
          </div>
          <div>
            <label htmlFor="history-location" className="block text-[11px] font-medium text-muted-foreground mb-1">
              Location
            </label>
            <SearchableSelect id="history-location" options={locationOptions} value={locationId} onChange={setLocationId} />
          </div>
          <div>
            <label htmlFor="history-period" className="block text-[11px] font-medium text-muted-foreground mb-1">
              Period
            </label>
            <select
              id="history-period"
              value={period}
              onChange={(e) => setPeriod(e.target.value as Period)}
              className={inputClass}
            >
              {PERIODS.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          {period === 'custom' && (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label htmlFor="history-from" className="block text-[11px] font-medium text-muted-foreground mb-1">
                  From
                </label>
                <input
                  id="history-from"
                  type="date"
                  value={customFrom}
                  max={customTo || undefined}
                  onChange={(e) => setCustomFrom(e.target.value)}
                  className={inputClass}
                />
              </div>
              <div>
                <label htmlFor="history-to" className="block text-[11px] font-medium text-muted-foreground mb-1">
                  To
                </label>
                <input
                  id="history-to"
                  type="date"
                  value={customTo}
                  min={customFrom || undefined}
                  onChange={(e) => setCustomTo(e.target.value)}
                  className={inputClass}
                />
              </div>
            </div>
          )}
        </div>

        <div className="p-6 space-y-4 overflow-y-auto">
          {error && (
            <div
              role="alert"
              className="p-3 rounded-xl bg-destructive/10 border border-destructive/25 text-destructive text-xs flex items-center justify-between gap-2"
            >
              <span className="flex items-start gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-px" />
                {error}
              </span>
              <button
                type="button"
                onClick={retry}
                className="underline inline-flex items-center gap-1 cursor-pointer shrink-0"
              >
                <RefreshCw className="w-3 h-3" />
                Retry
              </button>
            </div>
          )}

          {tab === 'history' ? (
            <>
              <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Kind of change">
                {HISTORY_FILTERS.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    aria-pressed={filter === option.key}
                    onClick={() => setFilter(option.key)}
                    className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-colors cursor-pointer ${
                      filter === option.key
                        ? 'bg-primary text-primary-foreground font-semibold shadow-xs'
                        : 'bg-muted/60 text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
                {!isLoading && (
                  <span className="text-xs text-muted-foreground ml-auto">
                    {total} {total === 1 ? 'movement' : 'movements'}
                  </span>
                )}
              </div>

              <div className="rounded-xl border border-border/70 overflow-x-auto">
                <table className="w-full text-xs text-left border-collapse">
                  <thead>
                    <tr className="bg-muted/40 text-[11px] uppercase tracking-wide text-muted-foreground border-b border-border/60">
                      <th className="px-3 py-2.5 font-semibold whitespace-nowrap">When</th>
                      <th className="px-3 py-2.5 font-semibold">What</th>
                      <th className="px-3 py-2.5 font-semibold">Product</th>
                      <th className="px-3 py-2.5 font-semibold">Location</th>
                      <th className="px-3 py-2.5 font-semibold text-right">Change</th>
                      <th className="px-3 py-2.5 font-semibold text-right whitespace-nowrap">On hand after</th>
                      <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Customer / supplier</th>
                      <th className="px-3 py-2.5 font-semibold">Reference</th>
                      <th className="px-3 py-2.5 font-semibold">Note</th>
                      <th className="px-3 py-2.5 font-semibold">By</th>
                    </tr>
                  </thead>
                  <tbody>
                    {isLoading ? (
                      <tr>
                        <td colSpan={10} className="px-3 py-10 text-center text-muted-foreground">
                          <span className="inline-flex items-center gap-2">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            Loading stock history…
                          </span>
                        </td>
                      </tr>
                    ) : entries.length === 0 ? (
                      <tr>
                        <td colSpan={10} className="px-3 py-10 text-center text-muted-foreground">
                          No stock changes match these filters.
                        </td>
                      </tr>
                    ) : (
                      entries.map((entry) => {
                        const style = ENTRY_STYLES[entry.type] ?? ENTRY_STYLES.CORRECTION;
                        const Icon = style.icon;
                        const isHold = entry.type === 'RESERVED' || entry.type === 'RELEASED';
                        return (
                          <tr key={entry.id} className="border-b border-border/40 last:border-b-0 hover:bg-muted/30 align-top">
                            <td className="px-3 py-2.5 whitespace-nowrap text-muted-foreground">{formatWhen(entry.at)}</td>
                            <td className="px-3 py-2.5 whitespace-nowrap">
                              <span
                                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[11px] font-semibold ${style.className}`}
                              >
                                <Icon className="w-3 h-3" />
                                {style.label}
                              </span>
                            </td>
                            <td className="px-3 py-2.5 min-w-44">
                              <div className="font-medium text-foreground">
                                {entry.product_name}
                                {entry.variant_label ? ` — ${entry.variant_label}` : ''}
                              </div>
                              <div className="text-[11px] text-muted-foreground font-mono">{entry.sku}</div>
                            </td>
                            <td className="px-3 py-2.5 min-w-36">
                              <div className="text-foreground">{entry.location_name}</div>
                              {entry.other_location_name && (
                                <div className="text-[11px] text-muted-foreground">
                                  {entry.type === 'SHIPPED_OUT' ? 'to' : 'from'} {entry.other_location_name}
                                </div>
                              )}
                            </td>
                            <td
                              className={`px-3 py-2.5 text-right font-mono font-semibold whitespace-nowrap ${
                                isHold
                                  ? 'text-muted-foreground'
                                  : entry.delta > 0
                                  ? 'text-emerald-600 dark:text-emerald-400'
                                  : 'text-rose-600 dark:text-rose-400'
                              }`}
                            >
                              {isHold ? `${entry.delta} ${entry.type === 'RESERVED' ? 'held' : 'freed'}` : signed(entry.delta)}
                            </td>
                            <td className="px-3 py-2.5 text-right font-mono text-muted-foreground">
                              {entry.on_hand_after ?? '—'}
                            </td>
                            <td className="px-3 py-2.5 min-w-32 text-foreground">{entry.counterparty || '—'}</td>
                            <td className="px-3 py-2.5 font-mono text-[11px] text-foreground whitespace-nowrap">
                              {entry.reference || '—'}
                            </td>
                            <td className="px-3 py-2.5 min-w-48 text-muted-foreground">{entry.note || ''}</td>
                            <td className="px-3 py-2.5 whitespace-nowrap text-muted-foreground" title={entry.created_by ?? undefined}>
                              {!entry.created_by ? '—' : entry.created_by === me ? 'You' : 'Team member'}
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>

              {!isLoading && entries.length < total && (
                <div className="flex justify-center">
                  <button
                    type="button"
                    onClick={loadMore}
                    disabled={isLoadingMore}
                    className="px-4 py-2 text-xs font-semibold rounded-xl border border-border/80 hover:bg-muted/60 text-foreground transition-colors inline-flex items-center gap-2 cursor-pointer disabled:opacity-50"
                  >
                    {isLoadingMore && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                    Show more ({total - entries.length} left)
                  </button>
                </div>
              )}
            </>
          ) : (
            <>
              <div className="rounded-xl border border-border/70 overflow-x-auto">
                <table className="w-full text-xs text-left border-collapse">
                  <thead>
                    <tr className="bg-muted/40 text-[11px] uppercase tracking-wide text-muted-foreground border-b border-border/60">
                      <th className="px-3 py-2.5 font-semibold">Location</th>
                      {TOTAL_COLUMNS.map((column) => (
                        <th key={column.key} className="px-3 py-2.5 font-semibold text-right whitespace-nowrap">
                          {column.label}
                        </th>
                      ))}
                      <th className="px-3 py-2.5 font-semibold text-right">Corrections</th>
                      <th className="px-3 py-2.5 font-semibold text-right whitespace-nowrap">Net change</th>
                      <th className="px-3 py-2.5 font-semibold text-right whitespace-nowrap border-l border-border/60">
                        On hand now
                      </th>
                      <th className="px-3 py-2.5 font-semibold text-right">Reserved</th>
                      <th className="px-3 py-2.5 font-semibold text-right">Available</th>
                    </tr>
                  </thead>
                  <tbody>
                    {isLoading || !summary ? (
                      <tr>
                        <td colSpan={13} className="px-3 py-10 text-center text-muted-foreground">
                          {isLoading ? (
                            <span className="inline-flex items-center gap-2">
                              <Loader2 className="w-4 h-4 animate-spin" />
                              Adding up stock changes…
                            </span>
                          ) : (
                            'No totals yet.'
                          )}
                        </td>
                      </tr>
                    ) : summary.locations.length === 0 ? (
                      <tr>
                        <td colSpan={13} className="px-3 py-10 text-center text-muted-foreground">
                          No locations match these filters.
                        </td>
                      </tr>
                    ) : (
                      summary.locations.map((place) => (
                        <tr key={place.location_id} className="border-b border-border/40 hover:bg-muted/30">
                          <td className="px-3 py-2.5 min-w-40">
                            <div className="font-medium text-foreground">{place.location_name}</div>
                            <div className="text-[11px] text-muted-foreground">
                              {formatLocationType(place.location_type)}
                              {place.sellable ? '' : ' · not sellable'}
                            </div>
                          </td>
                          {TOTAL_COLUMNS.map((column) => (
                            <td
                              key={column.key}
                              className={`px-3 py-2.5 text-right font-mono ${
                                place[column.key] ? 'text-foreground' : 'text-muted-foreground/60'
                              }`}
                            >
                              {place[column.key]}
                            </td>
                          ))}
                          <td className="px-3 py-2.5 text-right font-mono text-muted-foreground whitespace-nowrap">
                            {place.corrected_up || place.corrected_down
                              ? `+${place.corrected_up} / −${place.corrected_down}`
                              : '0'}
                          </td>
                          <td
                            className={`px-3 py-2.5 text-right font-mono font-semibold ${
                              place.net_change > 0
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : place.net_change < 0
                                ? 'text-rose-600 dark:text-rose-400'
                                : 'text-muted-foreground'
                            }`}
                          >
                            {signed(place.net_change)}
                          </td>
                          <td className="px-3 py-2.5 text-right font-mono font-semibold text-foreground border-l border-border/60">
                            {place.qty_on_hand}
                          </td>
                          <td className="px-3 py-2.5 text-right font-mono text-muted-foreground">{place.qty_reserved}</td>
                          <td className="px-3 py-2.5 text-right font-mono text-muted-foreground">
                            {place.sellable ? place.qty_available : '—'}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                  {summary && stockNow && summary.locations.length > 1 && !isLoading && (
                    <tfoot>
                      <tr className="bg-muted/40 font-semibold border-t border-border/60">
                        <td className="px-3 py-2.5 text-foreground">All locations</td>
                        {TOTAL_COLUMNS.map((column) => (
                          <td key={column.key} className="px-3 py-2.5 text-right font-mono text-foreground">
                            {summary.totals[column.key]}
                          </td>
                        ))}
                        <td className="px-3 py-2.5 text-right font-mono text-muted-foreground whitespace-nowrap">
                          {summary.totals.corrected_up || summary.totals.corrected_down
                            ? `+${summary.totals.corrected_up} / −${summary.totals.corrected_down}`
                            : '0'}
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono text-foreground">
                          {signed(summary.totals.net_change)}
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono text-foreground border-l border-border/60">
                          {stockNow.onHand}
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono text-muted-foreground">{stockNow.reserved}</td>
                        <td className="px-3 py-2.5 text-right font-mono text-muted-foreground">{stockNow.available}</td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Received, sold, shipped, damaged, lost, returned and corrections add up the selected period; on hand,
                reserved and available are as of now. Shipments between your own locations show as shipped out at one
                and shipped in at the other.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
