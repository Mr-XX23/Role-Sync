import React from 'react';
import { Sparkles } from 'lucide-react';
import { Reveal } from '../Reveal';
import { BRAND } from '../marketingData';

/** The same emblem the dashboard sidebar uses, so the marketing site feels like the product. */
export const BrandMark: React.FC<{ size?: 'sm' | 'md'; className?: string }> = ({ size = 'md', className = '' }) => {
  const box = size === 'sm' ? 'w-8 h-8 rounded-lg' : 'w-9 h-9 rounded-xl';
  const icon = size === 'sm' ? 'w-4 h-4' : 'w-4.5 h-4.5';
  return (
    <div className={`flex items-center gap-3 min-w-0 ${className}`}>
      <div
        className={`${box} bg-gradient-to-br from-primary/30 via-primary/15 to-transparent border border-primary/25 flex items-center justify-center shadow-xs text-primary shrink-0`}
      >
        <Sparkles className={`${icon} text-primary`} />
      </div>
      <div className="min-w-0 leading-none">
        <span className="font-serif text-lg font-bold text-foreground tracking-tight block">{BRAND.name}</span>
        <span className="font-mono text-[9px] font-bold text-muted-foreground uppercase tracking-widest block mt-1">
          {BRAND.subtitle}
        </span>
      </div>
    </div>
  );
};

/** Tiny uppercase mono label used above headings (mirrors the sidebar's "Platform Hub" style). */
export const Eyebrow: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <span
    className={`inline-flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground ${className}`}
  >
    <span className="w-1.5 h-1.5 rounded-full bg-primary/80" />
    {children}
  </span>
);

interface SectionHeadingProps {
  eyebrow: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  align?: 'left' | 'center';
  className?: string;
}

export const SectionHeading: React.FC<SectionHeadingProps> = ({
  eyebrow,
  title,
  description,
  align = 'center',
  className = '',
}) => (
  <div className={`${align === 'center' ? 'text-center mx-auto items-center' : 'items-start'} flex flex-col max-w-2xl ${className}`}>
    <Reveal>
      <Eyebrow>{eyebrow}</Eyebrow>
    </Reveal>
    <Reveal delay={80}>
      <h2 className="mt-4 font-serif text-3xl sm:text-4xl lg:text-[2.75rem] leading-[1.1] tracking-tight text-foreground text-balance">
        {title}
      </h2>
    </Reveal>
    {description && (
      <Reveal delay={160}>
        <p className="mt-4 text-base sm:text-lg text-muted-foreground leading-relaxed text-pretty">{description}</p>
      </Reveal>
    )}
  </div>
);

/** Consistent horizontal padding / max width for every section. */
export const Container: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <div className={`mx-auto w-full max-w-6xl px-5 sm:px-8 ${className}`}>{children}</div>
);
