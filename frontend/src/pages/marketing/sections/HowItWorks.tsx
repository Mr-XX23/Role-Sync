import React from 'react';
import { HOW_IT_WORKS } from '../marketingData';
import { Reveal } from '../Reveal';
import { useInView } from '../useReveal';
import { Container, SectionHeading } from './shared';

export const HowItWorks: React.FC = () => {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.3 });
  return (
    <section id="how-it-works" className="relative scroll-mt-20 py-20 sm:py-28 bg-card/40 border-y border-border/60 overflow-hidden">
      <div className="absolute inset-0 -z-10 mk-dots opacity-40" aria-hidden />
      <Container>
        <SectionHeading
          eyebrow="How it works"
          title="Connect. Ingest. Ask. Approve."
          description="Four steps from a cold inbox to a booked meeting, with you holding the pen at every real-world action."
        />

        <div ref={ref} className="relative mt-16">
          {/* Animated connector line (desktop) */}
          <svg
            className="absolute left-0 right-0 top-8 hidden lg:block h-px w-full overflow-visible"
            viewBox="0 0 100 1"
            preserveAspectRatio="none"
            aria-hidden
          >
            <line
              x1="6"
              y1="0.5"
              x2="94"
              y2="0.5"
              pathLength={1}
              className={`mk-draw ${inView ? 'is-visible' : ''}`}
              stroke="var(--primary)"
              strokeOpacity="0.5"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
              strokeDasharray="1"
            />
          </svg>

          <ol className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {HOW_IT_WORKS.map((step, i) => {
              const Icon = step.icon;
              return (
                <Reveal key={step.title} delay={i * 140} variant="up">
                  <li className="relative flex flex-col items-start">
                    <div className="relative">
                      <div className="mk-ping-ring w-16 h-16 rounded-2xl bg-card border border-primary/30 shadow-md flex items-center justify-center text-primary">
                        <Icon className="w-6 h-6" />
                      </div>
                      <span className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-primary text-primary-foreground font-mono text-[10px] font-bold flex items-center justify-center shadow-xs">
                        {i + 1}
                      </span>
                    </div>
                    <h3 className="mt-5 font-serif text-2xl text-foreground">{step.title}</h3>
                    <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{step.description}</p>
                  </li>
                </Reveal>
              );
            })}
          </ol>
        </div>
      </Container>
    </section>
  );
};
