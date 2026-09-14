import React from 'react';
import { ChevronDown } from 'lucide-react';
import { formatCredits } from '../../../utils/billingFormat';
import { Container, SectionHeading } from '../sections/shared';

function faq(signupCredits: number | null, creditPriceUsd: number | null) {
  const price = creditPriceUsd ? `$${creditPriceUsd.toFixed(creditPriceUsd < 0.01 ? 4 : 2)}` : null;
  return [
    {
      question: 'Who uses the credits?',
      answer:
        'Credits belong to a workspace, not to one person. Everyone you add to the workspace draws from the same balance, so a team never buys credits member by member.',
    },
    {
      question: 'Do credits expire?',
      answer: 'No. Credits stay in your workspace until they are used.',
    },
    {
      question: 'Is this a subscription?',
      answer:
        'No, it’s pay-as-you-go. Buy a pack when you need more credits. Nothing renews and nothing is charged automatically.',
    },
    {
      question: 'How are payments handled?',
      answer:
        'Checkout runs on Stripe. Your card details go straight to Stripe and never reach RoleSync’s servers. Credits are added as soon as Stripe confirms the payment.',
    },
    {
      question: 'What happens when credits run out?',
      answer:
        'New AI actions pause until you top up; anything already running still finishes. Your deals, documents and catalog stay available, because only work that uses AI or outside services needs credits.',
    },
    {
      question: 'What does a credit cost?',
      answer: `${price ? `One credit is ${price} at list price, and bigger packs cost less per credit. ` : 'Bigger packs cost less per credit. '}${
        signupCredits ? `Every new account also gets ${formatCredits(signupCredits)} free credits to start.` : ''
      }`.trim(),
    },
  ];
}

/** Short answers about how credits work. */
export const PricingFaq: React.FC<{ signupCredits: number | null; creditPriceUsd: number | null }> = ({
  signupCredits,
  creditPriceUsd,
}) => (
  <section id="pricing-faq" className="relative scroll-mt-20 py-16 sm:py-20">
    <Container>
      <SectionHeading eyebrow="Questions" title="How credits work" />
      <div className="mt-10 mx-auto max-w-3xl rounded-2xl border border-border/80 bg-card shadow-2xs divide-y divide-border/60 overflow-hidden">
        {faq(signupCredits, creditPriceUsd).map((item) => (
          <details key={item.question} className="group">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 text-sm font-semibold text-foreground hover:bg-muted/40 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/30 [&::-webkit-details-marker]:hidden">
              {item.question}
              <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0 transition-transform duration-200 group-open:rotate-180" />
            </summary>
            <p className="px-5 pb-4 -mt-1 text-sm text-muted-foreground leading-relaxed">{item.answer}</p>
          </details>
        ))}
      </div>
    </Container>
  </section>
);
