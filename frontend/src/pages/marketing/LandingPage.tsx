import React, { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import './marketing.css';
import { BRAND, ROUTE_TO_SECTION } from './marketingData';
import { MarketingNav } from './sections/MarketingNav';
import { Hero } from './sections/Hero';
import { StatsBar } from './sections/StatsBar';
import { Features } from './sections/Features';
import { HowItWorks } from './sections/HowItWorks';
import { Integrations } from './sections/Integrations';
import { Trust } from './sections/Trust';
import { About } from './sections/About';
import { Roadmap } from './sections/Roadmap';
import { Contact } from './sections/Contact';
import { Footer } from './sections/Footer';

/**
 * Public marketing site. One scrolling page; the routes /features, /about, /contact …
 * all render it and scroll to the matching section so every section is deep-linkable.
 */
export const LandingPage: React.FC = () => {
  const { pathname } = useLocation();
  // First navigation (a deep link or a hard refresh) jumps straight to the section; later ones animate.
  const hasScrolledOnce = useRef(false);

  useEffect(() => {
    const previous = document.title;
    document.title = `${BRAND.name} — ${BRAND.tagline}`;
    return () => {
      document.title = previous;
    };
  }, []);

  useEffect(() => {
    const id = ROUTE_TO_SECTION[pathname] ?? 'top';
    const behavior: ScrollBehavior = hasScrolledOnce.current ? 'smooth' : 'auto';
    hasScrolledOnce.current = true;
    if (id === 'top') {
      window.scrollTo({ top: 0, behavior });
      return;
    }
    // Wait one frame so the section has laid out before we scroll to it.
    const frame = requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ behavior, block: 'start' });
    });
    return () => cancelAnimationFrame(frame);
  }, [pathname]);

  return (
    <div className="mk-page min-h-screen bg-background text-foreground font-sans antialiased">
      <MarketingNav />
      <main>
        <Hero />
        <StatsBar />
        <Features />
        <HowItWorks />
        <Integrations />
        <Trust />
        <About />
        <Roadmap />
        <Contact />
      </main>
      <Footer />
    </div>
  );
};

export default LandingPage;
