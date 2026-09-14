import React from 'react';

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** What the switch turns on or off, for screen readers. */
  label: string;
  disabled?: boolean;
  size?: 'sm' | 'md';
  title?: string;
}

/** An on/off switch (role="switch"), keyboard operable like a checkbox. */
export const Switch: React.FC<SwitchProps> = ({ checked, onChange, label, disabled = false, size = 'md', title }) => {
  const track = size === 'sm' ? 'w-8 h-[18px]' : 'w-10 h-[22px]';
  const knob = size === 'sm' ? 'w-3.5 h-3.5' : 'w-[18px] h-[18px]';
  const shift = size === 'sm' ? 'translate-x-[14px]' : 'translate-x-[18px]';
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      title={title}
      disabled={disabled}
      onClick={(event) => {
        event.stopPropagation();
        onChange(!checked);
      }}
      className={`relative inline-flex shrink-0 items-center rounded-full border transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:cursor-not-allowed disabled:opacity-50 ${track} ${
        checked ? 'bg-primary border-primary' : 'bg-muted border-border'
      }`}
    >
      <span
        className={`inline-block rounded-full bg-background shadow-sm transition-transform duration-150 translate-x-[2px] ${knob} ${checked ? shift : ''}`}
      />
    </button>
  );
};
