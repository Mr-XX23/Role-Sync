import React from 'react';
import type { CreditExample } from '../../../api/billingApi';
import { formatCreditsLabel } from '../../../utils/billingFormat';
import { Reveal } from '../Reveal';
import { Container, Eyebrow } from '../sections/shared';

function approxUsd(credits: number, creditPriceUsd: number): string {
  const usd = credits * creditPriceUsd;
  if (!(usd > 0)) return '';
  return usd < 0.01 ? 'under $0.01' : `≈ $${usd.toFixed(2)}`;
}

/** What typical actions use, so a pack's size means something. */
export const PricingExamples: React.FC<{ examples: CreditExample[]; creditPriceUsd: number }> = ({
  examples,
  creditPriceUsd,
}) => {
  if (examples.length === 0) return null;
  return (
    <section id="what-credits-buy" className="relative scroll-mt-20 py-16 sm:py-20 bg-card/40 border-y border-border/60">
      <Container>
        <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] items-start">
          <div className="max-w-md">
            <Reveal>
              <Eyebrow>What credits buy</Eyebrow>
            </Reveal>
            <Reveal delay={80}>
              <h2 className="mt-4 font-serif text-3xl sm:text-4xl leading-[1.1] tracking-tight text-foreground text-balance">
                You pay for what each action actually uses.
              </h2>
            </Reveal>
            <Reveal delay={160}>
              <p className="mt-4 text-base text-muted-foreground leading-relaxed text-pretty">
                A quick answer takes a few credits. Reading a long document or researching a prospect on the web takes
                more. Work that doesn’t use AI, like editing deals or your catalog, is free.
              </p>
            </Reveal>
          </div>

          <Reveal variant="right" delay={120}>
            <ul className="rounded-2xl border border-border/80 bg-card shadow-2xs divide-y divide-border/60 overflow-hidden">
              {examples.map((example) => (
                <li key={example.label} className="flex items-center justify-between gap-4 px-5 py-3.5">
                  <span className="text-sm text-foreground">{example.label}</span>
                  <span className="text-right shrink-0">
                    <span className="block text-sm font-semibold text-foreground tabular-nums">
                      {formatCreditsLabel(example.credits)}
                    </span>
                    <span className="block text-[11px] text-muted-foreground tabular-nums">
                      {approxUsd(example.credits, creditPriceUsd)}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-muted-foreground">
              Typical amounts: the exact charge depends on how long the conversation or document is.
            </p>
          </Reveal>
        </div>
      </Container>
    </section>
  );
};
