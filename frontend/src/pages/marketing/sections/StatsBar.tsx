import React from 'react';
import { STATS, TECH_STACK } from '../marketingData';
import { useCountUp, useInView } from '../useReveal';
import { Container } from './shared';

const Stat: React.FC<{ value: number; suffix: string; label: string; delay: number }> = ({ value, suffix, label, delay }) => {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.4 });
  const n = useCountUp(value, inView, 1500 + delay);
  return (
    <div ref={ref} className="text-center sm:text-left">
      <p className="font-serif text-4xl sm:text-5xl text-foreground tracking-tight tabular-nums">
        {n}
        <span className="text-primary">{suffix}</span>
      </p>
      <p className="mt-1.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
    </div>
  );
};

export const StatsBar: React.FC = () => (
  <section className="relative border-y border-border/60 bg-card/40">
    <Container className="py-12 sm:py-14">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-8 sm:gap-10">
        {STATS.map((s, i) => (
          <Stat key={s.label} value={s.value} suffix={s.suffix} label={s.label} delay={i * 120} />
        ))}
      </div>
    </Container>

    {/* Tech marquee */}
    <div className="mk-marquee relative overflow-hidden border-t border-border/60 py-3.5" aria-label="Built with">
      <div className="pointer-events-none absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-background to-transparent z-10" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-background to-transparent z-10" />
      <div className="mk-marquee-track flex w-max gap-3" style={{ ['--mk-duration' as string]: '55s' } as React.CSSProperties}>
        {[...TECH_STACK, ...TECH_STACK].map((t, i) => (
          <span
            key={`${t}-${i}`}
            className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-card px-3.5 py-1.5 font-mono text-[11px] font-medium text-muted-foreground whitespace-nowrap"
          >
            <span className="w-1 h-1 rounded-full bg-primary/70" />
            {t}
          </span>
        ))}
      </div>
    </div>
  </section>
);
