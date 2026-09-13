import React, { useEffect, useState } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { ArrowRight, Menu, X } from 'lucide-react';
import { ThemeToggle } from '../../../components/ThemeToggle';
import { useAppSelector } from '../../../store';
import { NAV_LINKS } from '../marketingData';
import { BrandMark } from './shared';

export const MarketingNav: React.FC = () => {
  const [scrolled, setScrolled] = useState(false);
  const [progress, setProgress] = useState(0);
  const [open, setOpen] = useState(false);
  const isAuthenticated = useAppSelector((s) => s.auth.isAuthenticated);

  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setScrolled(y > 12);
      setProgress(max > 0 ? Math.min(1, y / max) : 0);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  const primaryCta = isAuthenticated
    ? { label: 'Open dashboard', to: '/select-role' }
    : { label: 'Get started', to: '/register' };

  return (
    <header className="fixed inset-x-0 top-0 z-50">
      {/* Reading progress */}
      <div className="absolute top-0 left-0 h-0.5 w-full bg-transparent">
        <div
          className="h-full bg-primary origin-left transition-transform duration-150 ease-out"
          style={{ transform: `scaleX(${progress})` }}
        />
      </div>

      <div
        className={`transition-all duration-300 ${
          scrolled ? 'bg-background/80 backdrop-blur-xl border-b border-border/60 shadow-2xs' : 'bg-transparent'
        }`}
      >
        <div className="mx-auto max-w-6xl px-5 sm:px-8">
          <div className={`flex items-center justify-between transition-all duration-300 ${scrolled ? 'h-14' : 'h-[72px]'}`}>
            <Link to="/" className="shrink-0" aria-label="RoleSync home" onClick={() => setOpen(false)}>
              <BrandMark size={scrolled ? 'sm' : 'md'} />
            </Link>

            {/* Desktop links */}
            <nav className="hidden md:flex items-center gap-1 rounded-full border border-border/60 bg-card/60 backdrop-blur-sm p-1">
              {NAV_LINKS.map((l) => (
                <NavLink
                  key={l.to}
                  to={l.to}
                  className={({ isActive }) =>
                    `px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all duration-200 ${
                      isActive ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'
                    }`
                  }
                >
                  {l.label}
                </NavLink>
              ))}
            </nav>

            <div className="hidden md:flex items-center gap-2">
              <ThemeToggle />
              {!isAuthenticated && (
                <Link
                  to="/signin"
                  className="px-3.5 py-2 rounded-lg text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
                >
                  Sign in
                </Link>
              )}
              <Link
                to={primaryCta.to}
                className="group inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-semibold shadow-xs hover:opacity-90 active:scale-[0.98] transition-all"
              >
                {primaryCta.label}
                <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
              </Link>
            </div>

            {/* Mobile toggle */}
            <div className="flex md:hidden items-center gap-2">
              <ThemeToggle />
              <button
                type="button"
                aria-label={open ? 'Close menu' : 'Open menu'}
                aria-expanded={open}
                onClick={() => setOpen((v) => !v)}
                className="w-9 h-9 rounded-lg border border-border/60 bg-card/60 flex items-center justify-center text-foreground hover:bg-muted transition-colors cursor-pointer"
              >
                {open ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </div>

        {/* Mobile menu */}
        <div
          className={`md:hidden overflow-hidden transition-[max-height,opacity] duration-300 ${
            open ? 'max-h-[420px] opacity-100 border-t border-border/60 bg-background/95 backdrop-blur-xl' : 'max-h-0 opacity-0'
          }`}
        >
          <nav className="px-5 py-4 flex flex-col gap-1">
            {NAV_LINKS.map((l, i) => (
              <NavLink
                key={l.to}
                to={l.to}
                onClick={() => setOpen(false)}
                style={{ ['--mk-delay' as string]: `${i * 40}ms` } as React.CSSProperties}
                className={({ isActive }) =>
                  `mk-pop px-3 py-2.5 rounded-xl text-sm font-semibold transition-colors ${
                    isActive ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'
                  }`
                }
              >
                {l.label}
              </NavLink>
            ))}
            <div className="mt-3 grid grid-cols-2 gap-2">
              {!isAuthenticated && (
                <Link
                  to="/signin"
                  onClick={() => setOpen(false)}
                  className="px-3 py-2.5 rounded-lg border border-border text-sm font-semibold text-center text-foreground hover:bg-muted transition-colors"
                >
                  Sign in
                </Link>
              )}
              <Link
                to={primaryCta.to}
                onClick={() => setOpen(false)}
                className={`px-3 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-semibold text-center hover:opacity-90 transition-opacity ${
                  isAuthenticated ? 'col-span-2' : ''
                }`}
              >
                {primaryCta.label}
              </Link>
            </div>
          </nav>
        </div>
      </div>
    </header>
  );
};
