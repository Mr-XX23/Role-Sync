import React from 'react';
import { ROADMAP } from '../marketingData';
import { Reveal } from '../Reveal';
import { Container, Eyebrow } from './shared';

export const Roadmap: React.FC = () => (
  <section className="relative py-16 sm:py-20">
    <Container>
      <div className="rounded-3xl border border-border/80 bg-gradient-to-br from-card via-card to-secondary/40 p-6 sm:p-10 shadow-2xs overflow-hidden relative">
        <div className="absolute -z-0 -right-20 -bottom-24 w-72 h-72 rounded-full bg-primary/10 blur-3xl" aria-hidden />
        <div className="relative grid lg:grid-cols-[0.8fr_1.2fr] gap-8 items-center">
          <div>
            <Reveal>
              <Eyebrow>On the roadmap</Eyebrow>
            </Reveal>
            <Reveal delay={80}>
              <h2 className="mt-4 font-serif text-3xl sm:text-4xl text-foreground tracking-tight text-balance">
                What we are building next.
              </h2>
            </Reveal>
            <Reveal delay={160}>
              <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
                Designed, documented and in progress. Listed here so the feature catalog above stays honest.
              </p>
            </Reveal>
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            {ROADMAP.map((r, i) => {
              const Icon = r.icon;
              return (
                <Reveal key={r.title} delay={i * 90} variant="scale">
                  <div className="h-full rounded-xl border border-dashed border-border bg-background/70 p-4">
                    <div className="flex items-center justify-between">
                      <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center text-muted-foreground">
                        <Icon className="w-4 h-4" />
                      </div>
                      <span className="font-mono text-[9px] font-bold uppercase tracking-wider rounded-full border border-border px-2 py-0.5 text-muted-foreground">
                        soon
                      </span>
                    </div>
                    <h3 className="mt-3 text-sm font-bold text-foreground">{r.title}</h3>
                    <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{r.description}</p>
                  </div>
                </Reveal>
              );
            })}
          </div>
        </div>
      </div>
    </Container>
  </section>
);
