import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown, Search } from 'lucide-react';

export interface DropdownOption {
  value: string;
  label: string;
  sub?: string;
  disabled?: boolean;
}

/** A dropdown that stays inside its modal, optionally with a search box. */
export const SearchableSelect: React.FC<{
  options: DropdownOption[];
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  searchable?: boolean;
  id?: string;
}> = ({ options, value, onChange, placeholder = 'Select…', searchable = false, id }) => {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const ref = useRef<HTMLDivElement>(null);

  // close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const selected = options.find((o) => o.value === value);
  const filtered = search
    ? options.filter(
        (o) =>
          o.label.toLowerCase().includes(search.toLowerCase()) ||
          (o.sub && o.sub.toLowerCase().includes(search.toLowerCase()))
      )
    : options;

  return (
    <div ref={ref} className="relative">
      <button
        id={id}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
          setSearch('');
        }}
        className="w-full px-3 py-2.5 text-xs rounded-xl bg-background border border-border/80 text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/40 flex items-center justify-between gap-2 cursor-pointer text-left"
      >
        <span className="truncate">{selected ? selected.label : placeholder}</span>
        <ChevronDown
          className={`w-3.5 h-3.5 shrink-0 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-card border border-border/80 rounded-xl shadow-lg overflow-hidden">
          {searchable && (
            <div className="p-2 border-b border-border/60">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search…"
                  autoFocus
                  className="w-full pl-8 pr-3 py-2 text-xs rounded-lg bg-background border border-border/60 text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary/40"
                />
              </div>
            </div>
          )}
          <div className="max-h-48 overflow-y-auto" role="listbox">
            {filtered.length === 0 ? (
              <div className="px-3 py-4 text-xs text-muted-foreground text-center">No results found</div>
            ) : (
              filtered.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  role="option"
                  aria-selected={o.value === value}
                  disabled={o.disabled}
                  onClick={() => {
                    onChange(o.value);
                    setOpen(false);
                    setSearch('');
                  }}
                  className={`w-full text-left px-3 py-2.5 text-xs transition-colors border-b border-border/30 last:border-b-0 disabled:opacity-50 disabled:cursor-not-allowed ${
                    o.value === value
                      ? 'bg-primary/10 text-primary font-semibold'
                      : 'text-foreground hover:bg-muted/60 cursor-pointer'
                  }`}
                >
                  <div className="truncate">{o.label}</div>
                  {o.sub && <div className="text-[11px] text-muted-foreground truncate mt-0.5">{o.sub}</div>}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
