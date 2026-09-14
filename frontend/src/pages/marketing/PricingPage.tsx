import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Check, Info, Lock, RefreshCw, X } from 'lucide-react';
import './marketing.css';
import { billingApi } from '../../api/billingApi';
import type { CreditPackage } from '../../api/billingApi';
import { useBillingQuery } from '../../hooks/useBillingQuery';
import { useEnsureWorkspace } from '../../hooks/useEnsureWorkspace';
import { withRedirect } from '../../utils/authRedirect';
import { formatCredits } from '../../utils/billingFormat';
import { Reveal } from './Reveal';
import { Footer } from './sections/Footer';
import { MarketingNav } from './sections/MarketingNav';
import { Container, Eyebrow } from './sections/shared';
import { PricingExamples } from './pricing/PricingExamples';
import { PricingFaq } from './pricing/PricingFaq';
import { PricingPacks, PricingPacksSkeleton } from './pricing/PricingPacks';
import { PricingWorkspace } from './pricing/PricingWorkspace';
import { useCheckout } from './pricing/useCheckout';

const HIGHLIGHTS = ['No subscription', 'Credits never expire', 'Shared by your whole workspace', 'Secure checkout with Stripe'];

const CheckoutCancelled: React.FC<{ onDismiss: () => void }> = ({ onDismiss }) => (
  <div
    role="status"
    className="mx-auto mb-10 max-w-2xl flex items-start gap-3 rounded-xl border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-sm text-amber-900 dark:text-amber-100"
  >
    <Info className="w-4 h-4 mt-0.5 shrink-0" />
    <p className="flex-1 leading-relaxed">
      <span className="font-semibold">Checkout cancelled.</span> You weren’t charged. Pick a pack whenever you’re ready.
    </p>
    <button
      type="button"
      onClick={onDismiss}
      aria-label="Dismiss"
      className="p-1 -m-1 rounded-md opacity-70 hover:opacity-100 transition-opacity cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
    >
      <X className="w-4 h-4" />
    </button>
  </div>
);

const PricesUnavailable: React.FC<{ message: string; retrying: boolean; onRetry: () => void }> = ({
  message,
  retrying,
  onRetry,
}) => (
  <div
    role="alert"
    className="rounded-2xl border border-red-500/30 bg-red-500/10 px-5 py-4 text-sm text-red-700 dark:text-red-300 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
  >
    <span>
      <span className="font-semibold">Prices couldn’t be loaded.</span> {message}
    </span>
    <button
      type="button"
      onClick={onRetry}
      disabled={retrying}
      className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted transition-colors cursor-pointer disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
    >
      <RefreshCw className={`w-3.5 h-3.5 ${retrying ? 'animate-spin' : ''}`} />
      Try again
    </button>
  </div>
);

/**
 * Public pricing: the sign-up offer, credit packs, what credits buy and how they work. Signed-in
 * visitors buy for their active workspace; others sign in first and come back here.
 */
export const PricingPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [cancelDismissed, setCancelDismissed] = useState(false);
  const pricing = useBillingQuery(() => billingApi.publicPricing(), 'public-pricing');
  const ensured = useEnsureWorkspace();
  const checkout = useCheckout();

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, []);

  const cancelled = searchParams.get('checkout') === 'cancelled' && !cancelDismissed;
  const data = pricing.data;
  const workspaceReady = ensured.status === 'ready' && ensured.workspace !== null && ensured.workspace.isActive !== false;

  const buy = (pkg: CreditPackage) => {
    if (!ensured.signedIn) {
      navigate(withRedirect('/signin', '/pricing'));
      return;
    }
    checkout.buy(pkg);
  };

  return (
    <div className="mk-page min-h-screen bg-background text-foreground font-sans antialiased">
      <MarketingNav />
      <main>
        <section className="relative overflow-hidden pt-32 pb-12 sm:pt-40 sm:pb-16">
          <div className="absolute inset-0 mk-grid pointer-events-none" aria-hidden />
          <div
            className="absolute -top-40 left-1/2 -translate-x-1/2 w-[640px] max-w-full h-[420px] rounded-full blur-3xl opacity-60 mk-blob bg-primary/15 pointer-events-none"
            aria-hidden
          />
          <Container className="relative">
            {cancelled && <CheckoutCancelled onDismiss={() => setCancelDismissed(true)} />}
            <div className="mx-auto max-w-3xl text-center flex flex-col items-center">
              <Reveal variant="blur">
                <Eyebrow className="rounded-full border border-border/70 bg-card/70 px-3 py-1.5">Pricing</Eyebrow>
              </Reveal>
              <Reveal delay={90}>
                <h1 className="mt-6 font-serif text-[2.5rem] leading-[1.05] sm:text-6xl tracking-tight text-foreground text-balance">
                  Pay for the work your agent <span className="mk-gradient-text">actually does.</span>
                </h1>
              </Reveal>
              <Reveal delay={180}>
                <p className="mt-6 text-base sm:text-lg text-muted-foreground leading-relaxed text-pretty">
                  Every account starts with {data ? `${formatCredits(data.signupCredits)} free credits` : 'free credits'}.
                  When your workspace needs more, buy a credit pack: there’s no subscription, and credits never expire.
                </p>
              </Reveal>
              <Reveal delay={260}>
                <ul className="mt-7 flex flex-wrap justify-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
                  {HIGHLIGHTS.map((text) => (
                    <li key={text} className="inline-flex items-center gap-1.5">
                      <Check className="w-3.5 h-3.5 text-emerald-500" />
                      {text}
                    </li>
                  ))}
                </ul>
              </Reveal>
            </div>
          </Container>
        </section>

        <section id="packs" className="relative scroll-mt-20 pb-16 sm:pb-24">
          <Container>
            <div className="mb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
              <div>
                <Eyebrow>Credit packs</Eyebrow>
                <h2 className="mt-3 font-serif text-2xl sm:text-3xl tracking-tight text-foreground">Top up whenever you need to</h2>
              </div>
              <PricingWorkspace ensured={ensured} />
            </div>

            {pricing.error && !data ? (
              <PricesUnavailable message={pricing.error} retrying={pricing.loading} onRetry={pricing.reload} />
            ) : !data ? (
              <PricingPacksSkeleton />
            ) : (
              <>
                <PricingPacks
                  packages={data.packages}
                  signupCredits={data.signupCredits}
                  signedIn={ensured.signedIn}
                  canBuy={!ensured.signedIn || workspaceReady}
                  checkout={checkout}
                  onBuy={buy}
                />
                {data.packages.length === 0 && (
                  <p className="mt-4 text-sm text-muted-foreground">Credit packs aren’t on sale right now. Check back soon.</p>
                )}
              </>
            )}

            <p className="mt-6 flex items-center gap-2 text-xs text-muted-foreground">
              <Lock className="w-3.5 h-3.5 shrink-0" />
              {data ? `Prices in ${data.currency.toUpperCase()}. ` : ''}Payments are processed securely by Stripe.
            </p>
          </Container>
        </section>

        {data && <PricingExamples examples={data.examples} creditPriceUsd={data.creditPriceUsd} />}
        <PricingFaq signupCredits={data?.signupCredits ?? null} creditPriceUsd={data?.creditPriceUsd ?? null} />
      </main>
      <Footer />
    </div>
  );
};

export default PricingPage;
