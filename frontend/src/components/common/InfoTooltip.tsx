import React, { useEffect, useId, useState } from 'react';
import { Info } from 'lucide-react';

interface InfoTooltipProps {
  /** What the icon explains, for screen readers ("About the sales agent"). */
  label: string;
  children: React.ReactNode;
  /** Which edge of the icon the tooltip lines up with. */
  align?: 'start' | 'end';
}

/**
 * An info icon that shows an explanation on hover, keyboard focus or tap. The tooltip stays
 * open while the pointer moves onto it, and Escape dismisses it.
 */
export const InfoTooltip: React.FC<InfoTooltipProps> = ({ label, children, align = 'start' }) => {
  const id = useId();
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const open = (hovered || focused) && !dismissed;

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDismissed(true);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open]);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => {
        setHovered(false);
        setDismissed(false);
      }}
    >
      <button
        type="button"
        aria-label={label}
        aria-describedby={id}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setFocused(false);
          setDismissed(false);
        }}
        className={`p-1 rounded-full transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 ${
          open ? 'text-foreground bg-muted/60' : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'
        }`}
      >
        <Info className="w-4 h-4" />
      </button>
      {/* The top padding bridges the gap to the icon, so moving the pointer onto the text keeps it open. */}
      <span
        id={id}
        role="tooltip"
        className={`absolute top-full z-50 pt-2 w-80 max-w-[calc(100vw-2rem)] transition-opacity duration-150 ${
          align === 'end' ? 'right-0' : 'left-0'
        } ${open ? 'visible opacity-100' : 'invisible opacity-0'}`}
      >
        <span className="block rounded-xl border border-border bg-popover px-4 py-3 text-xs font-normal leading-relaxed text-popover-foreground shadow-lg">
          {children}
        </span>
      </span>
    </span>
  );
};
