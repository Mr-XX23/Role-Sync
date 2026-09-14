import React from 'react';

export type PeriodDays = 7 | 30 | 90;

const OPTIONS: { value: PeriodDays; label: string; long: string }[] = [
  { value: 7, label: '7 days', long: 'Last 7 days' },
  { value: 30, label: '30 days', long: 'Last 30 days' },
  { value: 90, label: '90 days', long: 'Last 90 days' },
];

/** Picks the reporting window for usage figures. */
export const PeriodPicker: React.FC<{ value: PeriodDays; onChange: (value: PeriodDays) => void; disabled?: boolean }> = ({
  value,
  onChange,
  disabled = false,
}) => (
  <div role="radiogroup" aria-label="Period" className="inline-flex items-center p-0.5 rounded-xl border border-border/80 bg-muted/40">
    {OPTIONS.map((option) => {
      const selected = option.value === value;
      return (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={selected}
          aria-label={option.long}
          disabled={disabled}
          onClick={() => onChange(option.value)}
          className={`px-3 py-1.5 rounded-[10px] text-xs font-semibold transition-all cursor-pointer disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 ${
            selected
              ? 'bg-card text-foreground shadow-xs border border-border/70'
              : 'text-muted-foreground hover:text-foreground border border-transparent'
          }`}
        >
          {option.label}
        </button>
      );
    })}
  </div>
);
