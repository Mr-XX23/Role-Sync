import React, { useId, useMemo, useState } from 'react';

// Lightweight, dependency-free charts for the console. Colors are Tailwind classes so they follow
// the light/dark theme; every chart shows exact values on hover or focus.

export interface BarSeries {
  name: string;
  className: string; // background class for the bar segment, e.g. "bg-primary"
}

export interface BarDatum {
  label: string; // shown under the bar (thinned out when there are many)
  values: number[]; // one per series, stacked bottom-up
}

export const StackedBarChart: React.FC<{
  data: BarDatum[];
  series: BarSeries[];
  height?: number;
  formatValue?: (value: number) => string;
  emptyLabel?: string;
}> = ({ data, series, height = 180, formatValue = (value) => String(value), emptyLabel = 'No activity in this period' }) => {
  const [active, setActive] = useState<number | null>(null);
  const totals = data.map((datum) => datum.values.reduce((sum, value) => sum + value, 0));
  const max = Math.max(0, ...totals);
  const labelEvery = Math.max(1, Math.ceil(data.length / 10));
  const focused = active !== null ? data[active] : null;

  return (
    <div className="w-full">
      <div className="flex items-center justify-between gap-3 mb-2 min-h-[1.25rem]">
        <div className="flex flex-wrap items-center gap-3">
          {series.map((item) => (
            <span key={item.name} className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <span className={`w-2.5 h-2.5 rounded-sm ${item.className}`} />
              {item.name}
            </span>
          ))}
        </div>
        {focused && active !== null && (
          <span className="text-[11px] text-foreground tabular-nums truncate">
            <span className="text-muted-foreground">{focused.label}:</span>{' '}
            {series.length > 1
              ? series.map((item, index) => `${item.name} ${formatValue(focused.values[index] ?? 0)}`).join(' · ')
              : formatValue(totals[active])}
          </span>
        )}
      </div>
      <div className="relative" style={{ height }}>
        {max === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">{emptyLabel}</div>
        )}
        <div className="absolute inset-0 flex flex-col justify-between pointer-events-none">
          {[0, 1, 2, 3].map((line) => (
            <div key={line} className="border-t border-dashed border-border/50" />
          ))}
        </div>
        <div className="absolute inset-0 flex items-end gap-[3px]" onMouseLeave={() => setActive(null)}>
          {data.map((datum, index) => {
            const total = totals[index];
            const barHeight = max > 0 ? Math.max(total > 0 ? 2 : 0, (total / max) * 100) : 0;
            return (
              <button
                key={`${datum.label}-${index}`}
                type="button"
                aria-label={`${datum.label}: ${formatValue(total)}`}
                onMouseEnter={() => setActive(index)}
                onFocus={() => setActive(index)}
                onBlur={() => setActive(null)}
                className="relative flex-1 h-full flex items-end min-w-0 cursor-default focus:outline-none group"
              >
                <span
                  className={`w-full flex flex-col-reverse rounded-t-[3px] overflow-hidden transition-opacity ${
                    active !== null && active !== index ? 'opacity-45' : 'opacity-100'
                  }`}
                  style={{ height: `${barHeight}%` }}
                >
                  {datum.values.map((value, seriesIndex) => (
                    <span
                      key={series[seriesIndex]?.name ?? seriesIndex}
                      className={series[seriesIndex]?.className ?? 'bg-primary'}
                      style={{ height: total > 0 ? `${(value / total) * 100}%` : 0 }}
                    />
                  ))}
                </span>
              </button>
            );
          })}
        </div>
      </div>
      <div className="flex gap-[3px] mt-1.5">
        {data.map((datum, index) => (
          <span key={`${datum.label}-axis-${index}`} className="flex-1 min-w-0 text-center text-[9px] text-muted-foreground whitespace-nowrap">
            {index % labelEvery === 0 ? datum.label : ''}
          </span>
        ))}
      </div>
    </div>
  );
};

/** A smooth line with a soft fill, for one daily series. */
export const AreaChart: React.FC<{
  points: { label: string; value: number }[];
  height?: number;
  colorClass?: string; // text color class; the line and fill use currentColor
  formatValue?: (value: number) => string;
  emptyLabel?: string;
}> = ({ points, height = 160, colorClass = 'text-primary', formatValue = (value) => String(value), emptyLabel = 'No activity in this period' }) => {
  const gradientId = useId().replace(/:/g, '');
  const [active, setActive] = useState<number | null>(null);
  const width = 600;
  const max = Math.max(0, ...points.map((point) => point.value));
  const coordinates = useMemo(() => {
    const step = points.length > 1 ? width / (points.length - 1) : width;
    return points.map((point, index) => ({
      x: points.length > 1 ? index * step : width / 2,
      y: max > 0 ? height - 6 - (point.value / max) * (height - 16) : height - 6,
    }));
  }, [points, max, height]);
  const line = coordinates.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
  const area = coordinates.length > 0 ? `${line} L${coordinates[coordinates.length - 1].x},${height} L${coordinates[0].x},${height} Z` : '';
  const focused = active !== null ? points[active] : null;
  const labelEvery = Math.max(1, Math.ceil(points.length / 8));

  return (
    <div className="w-full">
      <div className="h-5 text-right text-[11px] tabular-nums">
        {focused && (
          <span>
            <span className="text-muted-foreground">{focused.label}:</span> {formatValue(focused.value)}
          </span>
        )}
      </div>
      <div className="relative" style={{ height }}>
        {max === 0 && <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">{emptyLabel}</div>}
        <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className={`absolute inset-0 w-full h-full ${colorClass}`} aria-hidden="true">
          <defs>
            <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="currentColor" stopOpacity="0.28" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[0.25, 0.5, 0.75].map((fraction) => (
            <line
              key={fraction}
              x1="0"
              x2={width}
              y1={height * fraction}
              y2={height * fraction}
              className="text-border"
              stroke="currentColor"
              strokeDasharray="4 4"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {max > 0 && (
            <>
              <path d={area} fill={`url(#${gradientId})`} />
              <path d={line} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
            </>
          )}
          {active !== null && coordinates[active] && (
            <line
              x1={coordinates[active].x}
              x2={coordinates[active].x}
              y1="0"
              y2={height}
              stroke="currentColor"
              strokeOpacity="0.35"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
        <div className="absolute inset-0 flex" onMouseLeave={() => setActive(null)}>
          {points.map((point, index) => (
            <button
              key={`${point.label}-${index}`}
              type="button"
              aria-label={`${point.label}: ${formatValue(point.value)}`}
              className="flex-1 h-full cursor-default focus:outline-none"
              onMouseEnter={() => setActive(index)}
              onFocus={() => setActive(index)}
              onBlur={() => setActive(null)}
            />
          ))}
        </div>
      </div>
      <div className="flex mt-1.5">
        {points.map((point, index) => (
          <span key={`${point.label}-axis-${index}`} className="flex-1 min-w-0 text-center text-[9px] text-muted-foreground whitespace-nowrap">
            {index % labelEvery === 0 ? point.label : ''}
          </span>
        ))}
      </div>
    </div>
  );
};

export interface DonutSlice {
  label: string;
  value: number;
  colorClass: string; // text color class, e.g. "text-sky-500"
  dotClass: string; // background class for the legend, e.g. "bg-sky-500"
}

export const DonutChart: React.FC<{
  slices: DonutSlice[];
  centerLabel: string;
  centerValue: string;
  formatValue?: (value: number) => string;
  size?: number;
}> = ({ slices, centerLabel, centerValue, formatValue = (value) => String(value), size = 148 }) => {
  const [active, setActive] = useState<number | null>(null);
  const total = slices.reduce((sum, slice) => sum + slice.value, 0);
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const segments = slices.reduce<{ slice: DonutSlice; offset: number; length: number }[]>((all, slice) => {
    const offset = all.length > 0 ? all[all.length - 1].offset + all[all.length - 1].length : 0;
    return [...all, { slice, offset, length: total > 0 ? (slice.value / total) * circumference : 0 }];
  }, []);
  const focused = active !== null ? slices[active] : null;

  return (
    <div className="flex flex-col sm:flex-row items-center gap-5">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90" aria-hidden="true">
          <circle cx="50" cy="50" r={radius} fill="none" strokeWidth="11" stroke="currentColor" className="text-muted" />
          {segments.map(({ slice, offset, length }, index) =>
            length > 0 ? (
              <circle
                key={slice.label}
                cx="50"
                cy="50"
                r={radius}
                fill="none"
                strokeWidth={active === index ? 13 : 11}
                stroke="currentColor"
                className={`${slice.colorClass} transition-all duration-200`}
                strokeDasharray={`${Math.max(length - 0.6, 0.1)} ${circumference}`}
                strokeDashoffset={-offset}
                onMouseEnter={() => setActive(index)}
                onMouseLeave={() => setActive(null)}
              />
            ) : null
          )}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center pointer-events-none px-4">
          <span className="text-lg font-bold text-foreground tabular-nums leading-tight">
            {focused ? formatValue(focused.value) : centerValue}
          </span>
          <span className="text-[10px] text-muted-foreground uppercase tracking-wide truncate max-w-full">
            {focused ? focused.label : centerLabel}
          </span>
        </div>
      </div>
      <ul className="space-y-1.5 min-w-0 w-full">
        {slices.map((slice, index) => (
          <li
            key={slice.label}
            className={`flex items-center justify-between gap-3 text-xs rounded-lg px-2 py-1 transition-colors ${active === index ? 'bg-muted/60' : ''}`}
            onMouseEnter={() => setActive(index)}
            onMouseLeave={() => setActive(null)}
          >
            <span className="flex items-center gap-2 min-w-0">
              <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${slice.dotClass}`} />
              <span className="truncate text-foreground">{slice.label}</span>
            </span>
            <span className="tabular-nums text-muted-foreground shrink-0">
              {formatValue(slice.value)}
              {total > 0 && <span className="ml-1.5 text-[10px]">{Math.round((slice.value / total) * 100)}%</span>}
            </span>
          </li>
        ))}
        {slices.length === 0 && <li className="text-xs text-muted-foreground">Nothing to show yet</li>}
      </ul>
    </div>
  );
};

/** Ranked rows with a proportional bar behind each value. */
export const RankedBars: React.FC<{
  rows: { key: string; label: React.ReactNode; sublabel?: React.ReactNode; value: number }[];
  formatValue?: (value: number) => string;
  barClass?: string;
  emptyLabel?: string;
}> = ({ rows, formatValue = (value) => String(value), barClass = 'bg-primary/15', emptyLabel = 'Nothing to show yet' }) => {
  const max = Math.max(0, ...rows.map((row) => row.value));
  if (rows.length === 0) {
    return <p className="text-xs text-muted-foreground py-6 text-center">{emptyLabel}</p>;
  }
  return (
    <ul className="space-y-1.5">
      {rows.map((row) => (
        <li key={row.key} className="relative rounded-lg overflow-hidden">
          <span className={`absolute inset-y-0 left-0 ${barClass}`} style={{ width: `${max > 0 ? (row.value / max) * 100 : 0}%` }} />
          <div className="relative flex items-center justify-between gap-3 px-2.5 py-1.5 text-xs">
            <span className="min-w-0">
              <span className="block truncate text-foreground font-medium">{row.label}</span>
              {row.sublabel && <span className="block truncate text-[10px] text-muted-foreground">{row.sublabel}</span>}
            </span>
            <span className="tabular-nums text-foreground shrink-0">{formatValue(row.value)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
};

export const Meter: React.FC<{ value: number; max: number; className?: string; tone?: 'primary' | 'success' | 'warning' | 'danger' }> = ({
  value,
  max,
  className = '',
  tone = 'primary',
}) => {
  const fraction = max > 0 ? Math.min(1, value / max) : 0;
  const color = { primary: 'bg-primary', success: 'bg-emerald-500', warning: 'bg-amber-500', danger: 'bg-red-500' }[tone];
  return (
    <div className={`h-1.5 rounded-full bg-muted overflow-hidden ${className}`} role="presentation">
      <div className={`h-full rounded-full ${color} transition-all duration-500`} style={{ width: `${fraction * 100}%` }} />
    </div>
  );
};
