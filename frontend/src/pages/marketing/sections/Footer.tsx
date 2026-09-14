import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, ArrowUp } from 'lucide-react';
import { useAppSelector } from '../../../store';
import { BRAND, FEATURE_AREAS, TOTAL_FEATURES } from '../marketingData';
import { Reveal } from '../Reveal';
import { BrandMark, Container } from './shared';

const COLUMNS = [
  {
    title: 'Product',
    links: [
      { label: 'Features', to: '/features' },
      { label: 'How it works', to: '/how-it-works' },
      { label: 'Integrations', to: '/integrations' },
      { label: 'Pricing', to: '/pricing' },
      { label: 'Security', to: '/security' },
    ],
  },
  {
    title: 'Company',
    links: [
      { label: 'About us', to: '/about' },
      { label: 'Contact', to: '/contact' },
      { label: 'Support', to: '/salesman/support' },
      { label: 'Privacy Policy', to: '/privacy' },
      { label: 'Terms of Service', to: '/terms' },
    ],
  },
  {
    title: 'Get started',
    links: [
      { label: 'Create account', to: '/register' },
      { label: 'Sign in', to: '/signin' },
      { label: 'Forgot password', to: '/forgot-password' },
    ],
  },
];

export const Footer: React.FC = () => {
  const isAuthenticated = useAppSelector((s) => s.auth.isAuthenticated);
  return (
    <footer className="relative border-t border-border/60 bg-background">
      {/* CTA band */}
      <Container className="py-16 sm:py-20">
        <Reveal variant="scale">
          <div className="relative overflow-hidden rounded-3xl border border-border/80 bg-card p-8 sm:p-12 text-center shadow-xl">
            <div className="absolute inset-0 -z-0 mk-grid opacity-70" aria-hidden />
            <div className="absolute -z-0 -top-24 left-1/2 -translate-x-1/2 w-[520px] h-[260px] rounded-full bg-primary/15 blur-3xl" aria-hidden />
            <div className="relative">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
                {TOTAL_FEATURES} features · {FEATURE_AREAS.length} areas · 1 workspace
              </p>
              <h2 className="mt-4 font-serif text-3xl sm:text-5xl text-foreground tracking-tight text-balance">
                Give your sales team an agent that asks first.
              </h2>
              <p className="mt-4 text-muted-foreground max-w-xl mx-auto text-pretty">
                Connect your tools, drop in your documents and watch the first approval card appear in minutes.
              </p>
              <div className="mt-8 flex flex-col sm:flex-row justify-center gap-3">
                <Link
                  to={isAuthenticated ? '/salesman' : '/register'}
                  className="group inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground shadow-md hover:opacity-90 active:scale-[0.98] transition-all"
                >
                  {isAuthenticated ? 'Open dashboard' : 'Create your workspace'}
                  <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
                </Link>
                <Link
                  to="/contact"
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-background px-6 py-3 text-sm font-semibold text-foreground hover:bg-muted transition-colors"
                >
                  Book a demo
                </Link>
              </div>
            </div>
          </div>
        </Reveal>
      </Container>

      {/* Links */}
      <div className="border-t border-border/60">
        <Container className="py-12">
          <div className="grid gap-10 md:grid-cols-[1.4fr_repeat(3,1fr)]">
            <div>
              <BrandMark />
              <p className="mt-4 text-sm text-muted-foreground leading-relaxed max-w-xs">{BRAND.tagline}</p>
              <p className="mt-4 font-mono text-[10px] uppercase tracking-widest text-muted-foreground/70">
                Human-approved · workspace-isolated · auditable
              </p>
            </div>
            {COLUMNS.map((c) => (
              <div key={c.title}>
                <p className="font-mono text-[10px] font-bold uppercase tracking-widest text-muted-foreground/80">{c.title}</p>
                <ul className="mt-4 space-y-2.5">
                  {c.links.map((l) => (
                    <li key={l.label}>
                      <Link to={l.to} className="text-sm text-foreground/80 hover:text-primary transition-colors">
                        {l.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="mt-12 pt-6 border-t border-border/60 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span>© {new Date().getFullYear()} {BRAND.name}. All rights reserved.</span>
              <Link to="/privacy" className="hover:text-foreground transition-colors">Privacy</Link>
              <Link to="/terms" className="hover:text-foreground transition-colors">Terms</Link>
            </div>
            <button
              type="button"
              onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              Back to top
              <ArrowUp className="w-3.5 h-3.5" />
            </button>
          </div>
        </Container>
      </div>
    </footer>
  );
};
