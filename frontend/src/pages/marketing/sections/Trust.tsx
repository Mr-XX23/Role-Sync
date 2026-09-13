import React from 'react';
import { TRUST_PILLARS } from '../marketingData';
import { Reveal } from '../Reveal';
import { Container, SectionHeading } from './shared';

export const Trust: React.FC = () => (
  <section id="security" className="relative scroll-mt-20 py-20 sm:py-28 bg-card/40 border-y border-border/60">
    <Container>
      <SectionHeading
        eyebrow="Built for trust"
        title="Autonomy you can audit, isolation you can prove."
        description="The agent is powerful because it is constrained. Every boundary below is enforced in code, not in a policy document."
      />
      <div className="mt-14 grid gap-4 sm:grid-cols-2">
        {TRUST_PILLARS.map((p, i) => {
          const Icon = p.icon;
          return (
            <Reveal key={p.title} delay={i * 110} variant={i % 2 === 0 ? 'left' : 'right'}>
              <div className="mk-card-glow group h-full rounded-2xl border border-border/80 bg-card p-6 shadow-2xs transition-all duration-300 hover:shadow-md">
                <div className="flex items-center gap-3">
                  <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary/30 via-primary/15 to-transparent border border-primary/25 text-primary flex items-center justify-center transition-transform group-hover:rotate-6">
                    <Icon className="w-5 h-5" />
                  </div>
                  <h3 className="font-serif text-xl text-foreground">{p.title}</h3>
                </div>
                <p className="mt-4 text-sm text-muted-foreground leading-relaxed">{p.description}</p>
              </div>
            </Reveal>
          );
        })}
      </div>
    </Container>
  </section>
);
