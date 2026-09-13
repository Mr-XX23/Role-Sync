import React, { useEffect, useRef, useState } from 'react';
import { FEATURE_AREAS, TOTAL_FEATURES, type Feature, type FeatureArea } from '../marketingData';
import { Reveal } from '../Reveal';
import { Container, SectionHeading } from './shared';

/* ------------------------------------------------------------------ */
/* Feature card                                                        */
/* ------------------------------------------------------------------ */

const FeatureCard: React.FC<{ feature: Feature; index: number }> = ({ feature, index }) => {
  const Icon = feature.icon;
  return (
    <Reveal delay={(index % 6) * 60} className="h-full">
      <article className="mk-card-glow group h-full rounded-xl border border-border/80 bg-card p-4 shadow-2xs transition-all duration-300 hover:-translate-y-1 hover:shadow-md">
        <div className="flex items-start justify-between gap-2">
          <div className="w-9 h-9 rounded-lg bg-muted/60 border border-border/60 flex items-center justify-center text-muted-foreground transition-all duration-300 group-hover:bg-primary/15 group-hover:border-primary/30 group-hover:text-primary group-hover:scale-105">
            <Icon className="w-4 h-4" />
          </div>
          {feature.badge && (
            <span className="font-mono text-[9px] font-bold uppercase tracking-wider rounded-full border border-emerald-500/25 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-2 py-0.5">
              {feature.badge}
            </span>
          )}
        </div>
        <h4 className="mt-3 text-sm font-bold text-foreground leading-snug">{feature.title}</h4>
        <p className="mt-1.5 text-xs text-muted-foreground leading-relaxed">{feature.description}</p>
      </article>
    </Reveal>
  );
};

/* ------------------------------------------------------------------ */
/* Area block                                                          */
/* ------------------------------------------------------------------ */

const AreaBlock: React.FC<{ area: FeatureArea; index: number }> = ({ area, index }) => {
  const Icon = area.icon;
  return (
    <div id={`feature-${area.id}`} data-area={area.id} className="scroll-mt-32">
      <Reveal variant="left">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-primary/30 via-primary/15 to-transparent border border-primary/25 flex items-center justify-center text-primary shrink-0 shadow-xs">
            <Icon className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="font-mono text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                {String(index + 1).padStart(2, '0')} · {area.features.length} features
              </span>
            </div>
            <h3 className="mt-1 font-serif text-2xl sm:text-3xl text-foreground tracking-tight">{area.label}</h3>
            <p className="mt-1 text-sm font-semibold text-primary">{area.tagline}</p>
            <p className="mt-2 text-sm text-muted-foreground leading-relaxed max-w-2xl">{area.description}</p>
          </div>
        </div>
      </Reveal>

      <div className="mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {area.features.map((f, i) => (
          <FeatureCard key={f.title} feature={f} index={i} />
        ))}
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Section                                                             */
/* ------------------------------------------------------------------ */

export const Features: React.FC = () => {
  const [active, setActive] = useState(FEATURE_AREAS[0].id);
  const listRef = useRef<HTMLDivElement>(null);

  // Scroll-spy: highlight the area whose block is closest to the top of the viewport.
  useEffect(() => {
    const root = listRef.current;
    if (!root || typeof IntersectionObserver === 'undefined') return;
    const blocks = Array.from(root.querySelectorAll<HTMLElement>('[data-area]'));
    const ratios = new Map<string, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) ratios.set((e.target as HTMLElement).dataset.area!, e.intersectionRatio);
        let best = active;
        let bestRatio = -1;
        for (const b of blocks) {
          const r = ratios.get(b.dataset.area!) ?? 0;
          if (r > bestRatio) {
            bestRatio = r;
            best = b.dataset.area!;
          }
        }
        if (bestRatio > 0) setActive(best);
      },
      { rootMargin: '-25% 0px -55% 0px', threshold: [0, 0.1, 0.25, 0.5, 0.75, 1] }
    );
    blocks.forEach((b) => observer.observe(b));
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const jump = (id: string) => {
    document.getElementById(`feature-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <section id="features" className="relative scroll-mt-20 py-20 sm:py-28">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-border to-transparent" aria-hidden />
      <Container>
        <SectionHeading
          eyebrow="Every feature, nothing hidden"
          title={
            <>
              {TOTAL_FEATURES} capabilities across {FEATURE_AREAS.length} areas.
              <br className="hidden sm:block" /> All shipped, all in one workspace.
            </>
          }
          description="This is the complete list of what RoleSync does today. No roadmap padding, no asterisks."
        />

        {/* Mobile / tablet area chips */}
        <div className="lg:hidden sticky top-14 z-30 -mx-5 sm:-mx-8 mt-10 border-y border-border/60 bg-background/85 backdrop-blur-xl">
          <div className="flex gap-2 overflow-x-auto mk-scrollbar-none px-5 sm:px-8 py-2.5">
            {FEATURE_AREAS.map((a) => {
              const Icon = a.icon;
              const isActive = a.id === active;
              return (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => jump(a.id)}
                  className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1.5 text-xs font-semibold transition-all cursor-pointer ${
                    isActive
                      ? 'border-primary/40 bg-primary/15 text-primary'
                      : 'border-border/70 bg-card text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {a.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="mt-10 lg:mt-16 grid lg:grid-cols-[240px_1fr] gap-10 xl:gap-14">
          {/* Desktop sticky rail */}
          <aside className="hidden lg:block">
            <div className="sticky top-24">
              <p className="font-mono text-[10px] font-bold uppercase tracking-widest text-muted-foreground/80 px-3 mb-2">
                Jump to area
              </p>
              <nav className="space-y-1">
                {FEATURE_AREAS.map((a) => {
                  const Icon = a.icon;
                  const isActive = a.id === active;
                  return (
                    <button
                      key={a.id}
                      type="button"
                      onClick={() => jump(a.id)}
                      className={`group relative w-full flex items-center gap-3 rounded-xl border px-3 py-2 text-left text-xs font-semibold transition-all duration-200 cursor-pointer ${
                        isActive
                          ? 'bg-card border-border/80 shadow-xs text-foreground'
                          : 'border-transparent text-muted-foreground hover:bg-muted/50 hover:text-foreground'
                      }`}
                    >
                      {isActive && <span className="absolute -left-1 w-1.5 h-5 rounded-r-full bg-primary" />}
                      <span
                        className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-all ${
                          isActive
                            ? 'bg-primary/20 text-primary border border-primary/30'
                            : 'bg-muted/50 text-muted-foreground group-hover:bg-muted group-hover:text-foreground'
                        }`}
                      >
                        <Icon className="w-4 h-4" />
                      </span>
                      <span className="truncate">{a.label}</span>
                      <span className="ml-auto font-mono text-[10px] text-muted-foreground/70">{a.features.length}</span>
                    </button>
                  );
                })}
              </nav>
            </div>
          </aside>

          {/* Blocks */}
          <div ref={listRef} className="space-y-20 min-w-0">
            {FEATURE_AREAS.map((a, i) => (
              <AreaBlock key={a.id} area={a} index={i} />
            ))}
          </div>
        </div>
      </Container>
    </section>
  );
};
