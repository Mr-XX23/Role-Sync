import React from 'react';
import { formatPercent } from '../../utils/billingFormat';

const TONE = {
  primary: 'text-primary',
  warning: 'text-amber-500',
  danger: 'text-red-500',
};

/** A ring filled to a percentage, with the figure in the middle. */
export const UsageRing: React.FC<{
  percent: number;
  caption: string;
  tone?: keyof typeof TONE;
  size?: number;
}> = ({ percent, caption, tone = 'primary', size = 132 }) => {
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(100, Math.max(0, Number.isFinite(percent) ? percent : 0));
  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${formatPercent(clamped)} ${caption}`}
    >
      <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90" aria-hidden="true">
        <circle cx="50" cy="50" r={radius} fill="none" strokeWidth="9" stroke="currentColor" className="text-muted" />
        {clamped > 0 && (
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            strokeWidth="9"
            strokeLinecap="round"
            stroke="currentColor"
            className={`${TONE[tone]} transition-[stroke-dasharray] duration-700`}
            strokeDasharray={`${Math.max((clamped / 100) * circumference, 1)} ${circumference}`}
          />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-3">
        <span className="text-xl font-bold text-foreground tabular-nums leading-tight">{formatPercent(clamped)}</span>
        <span className="text-[10px] text-muted-foreground uppercase tracking-wide">{caption}</span>
      </div>
    </div>
  );
};
