import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Bot,
  Check,
  ChevronDown,
  FileText,
  Handshake,
  Library,
  Package,
  Pencil,
  Play,
  Search,
  Sparkles,
  UserRound,
  X,
} from 'lucide-react';
import { Reveal } from '../Reveal';
import { prefersReducedMotion, useSpotlight } from '../useReveal';
import { GmailIcon, GoogleCalendarIcon } from '../BrandIcons';
import { BRAND, TOTAL_FEATURES } from '../marketingData';
import { Container, Eyebrow } from './shared';

/* ------------------------------------------------------------------ */
/* Scripted agent demo                                                 */
/* ------------------------------------------------------------------ */

const TOOL_CALLS = [
  { icon: GmailIcon, label: 'search_gmail_threads · "Acme"' },
  { icon: Library, label: 'search_knowledge_vault · Q4 rollout battlecard' },
  { icon: GoogleCalendarIcon, label: 'find_free_slots · Thu · 30 min' },
  { icon: Package, label: 'check_availability · SKU-4471 × 120' },
];

// 0 user typed · 1 thinking · 2..5 tool calls · 6 approval card · 7 approved · 8 done
const STEP_DELAYS = [900, 1100, 700, 700, 700, 900, 2600, 1100, 3600];
const LAST_STEP = STEP_DELAYS.length - 1;

const useDemoStep = () => {
  const [step, setStep] = useState(prefersReducedMotion() ? LAST_STEP : 0);
  useEffect(() => {
    if (prefersReducedMotion()) return;
    const id = window.setTimeout(() => setStep((s) => (s >= LAST_STEP ? 0 : s + 1)), STEP_DELAYS[step]);
    return () => window.clearTimeout(id);
  }, [step]);
  return step;
};

const AgentDemo: React.FC = () => {
  const step = useDemoStep();
  const showTools = step >= 2;
  const visibleTools = Math.min(TOOL_CALLS.length, Math.max(0, step - 1));
  const showApproval = step >= 6;
  const approved = step >= 7;
  const done = step >= 8;

  return (
    <div className="relative rounded-2xl border border-border/80 bg-card/90 backdrop-blur-sm shadow-xl overflow-hidden">
      {/* Window chrome */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/70 bg-muted/40">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-primary/15 border border-primary/25 flex items-center justify-center text-primary">
            <Bot className="w-3.5 h-3.5" />
          </div>
          <div className="leading-none">
            <p className="text-xs font-bold text-foreground">Sales Agent</p>
            <p className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground mt-1">orchestrator · session #4f2a</p>
          </div>
        </div>
        <span className="inline-flex items-center gap-1.5 font-mono text-[9px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
          <span className="relative flex w-1.5 h-1.5">
            <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-500 opacity-75 animate-ping" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
          </span>
          streaming
        </span>
      </div>

      <div className="p-4 space-y-3 min-h-[380px] text-sm">
        {/* User */}
        <div className="flex justify-end">
          <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary text-primary-foreground px-3.5 py-2.5 text-xs leading-relaxed shadow-xs">
            Prep me for tomorrow&apos;s Acme call, then send Jane a follow-up and book 30 minutes on Thursday.
          </div>
        </div>

        {/* Thinking */}
        {step >= 1 && (
          <div className="mk-pop flex items-start gap-2.5">
            <div className="w-6 h-6 rounded-md bg-muted flex items-center justify-center text-muted-foreground shrink-0 mt-0.5">
              <Sparkles className="w-3 h-3" />
            </div>
            <div className="space-y-1.5 grow min-w-0">
              <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">reasoning</p>
              {!showTools ? (
                <div className="space-y-1.5">
                  <div className="h-2.5 w-4/5 rounded mk-shimmer" />
                  <div className="h-2.5 w-3/5 rounded mk-shimmer" />
                </div>
              ) : (
                <p className="text-xs text-foreground/90 leading-relaxed">
                  Three things to do: gather context, draft the follow-up, find a slot. I&apos;ll check stock for the SKU Jane asked about so the quote is honest.
                </p>
              )}
            </div>
          </div>
        )}

        {/* Tool calls */}
        {showTools && (
          <div className="pl-8.5 space-y-1.5">
            {TOOL_CALLS.slice(0, visibleTools).map((t, i) => {
              const Icon = t.icon;
              const complete = i < visibleTools - 1 || showApproval;
              return (
                <div
                  key={t.label}
                  className="mk-pop flex items-center gap-2 min-w-0 rounded-lg border border-border/70 bg-background/70 px-2.5 py-1.5"
                >
                  <Icon className="w-3.5 h-3.5 text-foreground shrink-0" />
                  <span className="font-mono text-[10px] text-foreground/80 truncate min-w-0">{t.label}</span>
                  <span className="ml-auto shrink-0">
                    {complete ? (
                      <Check className="w-3 h-3 text-emerald-500" />
                    ) : (
                      <span className="block w-3 h-3 rounded-full border-2 border-primary/30 border-t-primary animate-spin" />
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* Approval card */}
        {showApproval && (
          <div className="mk-pop pl-8.5">
            <div
              className={`rounded-xl border p-3 transition-colors duration-500 ${
                approved ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-primary/40 bg-primary/5'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="font-mono text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
                  {approved ? 'approved · undo available' : 'needs your approval'}
                </p>
                <GmailIcon className="w-3.5 h-3.5" />
              </div>
              <p className="mt-1.5 text-xs font-semibold text-foreground">send_email → jane@acme.com</p>
              <p className="text-[11px] text-muted-foreground leading-relaxed mt-1">
                Subject: Q4 rollout, next steps. Attaches battlecard summary and a quote for 120 × SKU-4471 at 8% off (limit 10%).
              </p>
              <div className="mt-2.5 flex items-center gap-1.5">
                {approved ? (
                  <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 px-2 py-1 text-[10px] font-bold">
                    <Check className="w-3 h-3" /> Approved
                  </span>
                ) : (
                  <>
                    <span className="inline-flex items-center gap-1 rounded-md bg-primary text-primary-foreground px-2 py-1 text-[10px] font-bold">
                      <Check className="w-3 h-3" /> Approve
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[10px] font-semibold text-foreground">
                      <Pencil className="w-3 h-3" /> Edit
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[10px] font-semibold text-muted-foreground">
                      <X className="w-3 h-3" /> Reject
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Result */}
        {done && (
          <div className="mk-pop flex items-start gap-2.5">
            <div className="w-6 h-6 rounded-md bg-primary/15 flex items-center justify-center text-primary shrink-0 mt-0.5">
              <Bot className="w-3 h-3" />
            </div>
            <p className="text-xs text-foreground/90 leading-relaxed">
              Sent. Thursday 10:00 is booked with Jane, and the deal <span className="font-semibold">Acme, Q4 rollout</span> moved to Proposal with the quote attached. Stock reserved.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Floating side cards                                                 */
/* ------------------------------------------------------------------ */

const FloatCard: React.FC<{
  className?: string;
  delay?: number;
  rot?: number;
  children: React.ReactNode;
}> = ({ className = '', delay = 0, rot = 0, children }) => (
  <div
    className={`mk-float absolute hidden xl:flex items-center gap-2.5 rounded-xl border border-border/80 bg-card/95 backdrop-blur-sm shadow-lg px-3 py-2.5 ${className}`}
    style={{ ['--mk-delay' as string]: `${delay}ms`, ['--mk-rot' as string]: `${rot}deg` } as React.CSSProperties}
  >
    {children}
  </div>
);

/* ------------------------------------------------------------------ */
/* Hero                                                                */
/* ------------------------------------------------------------------ */

export const Hero: React.FC = () => {
  const spot = useSpotlight<HTMLElement>();
  return (
    <section id="top" ref={spot} className="relative overflow-hidden pt-32 pb-20 sm:pt-40 sm:pb-28 mk-spotlight">
      {/* Background */}
      <div className="absolute inset-0 -z-10 mk-grid" aria-hidden />
      <div
        className="absolute -z-10 -top-32 -left-24 w-[520px] h-[520px] rounded-full blur-3xl opacity-60 mk-blob bg-primary/15"
        aria-hidden
      />
      <div
        className="absolute -z-10 top-20 -right-32 w-[560px] h-[560px] rounded-full blur-3xl opacity-70 mk-blob bg-secondary"
        style={{ ['--mk-delay' as string]: '-6s' } as React.CSSProperties}
        aria-hidden
      />

      <Container>
        <div className="grid lg:grid-cols-[1.05fr_0.95fr] gap-14 lg:gap-10 items-center">
          {/* Copy */}
          <div className="max-w-xl min-w-0">
            <Reveal variant="blur">
              <Eyebrow className="rounded-full border border-border/70 bg-card/70 px-3 py-1.5">
                {BRAND.subtitle} · Salesman Engine
              </Eyebrow>
            </Reveal>
            <Reveal delay={90}>
              <h1 className="mt-6 font-serif text-[2.6rem] leading-[1.02] sm:text-6xl lg:text-[4.2rem] tracking-tight text-foreground text-balance">
                Sales work, done by an agent that <span className="mk-gradient-text">asks first.</span>
              </h1>
            </Reveal>
            <Reveal delay={180}>
              <p className="mt-6 text-base sm:text-lg text-muted-foreground leading-relaxed text-pretty">
                {BRAND.name} connects your inbox, calendar, documents and catalog to an AI sales agent that researches,
                drafts, prices and books, then pauses for your approval before anything real happens.
              </p>
            </Reveal>
            <Reveal delay={260}>
              <div className="mt-8 flex flex-col sm:flex-row gap-3">
                <Link
                  to="/register"
                  className="group inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground shadow-md hover:opacity-90 active:scale-[0.98] transition-all"
                >
                  Start free
                  <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
                </Link>
                <Link
                  to="/features"
                  className="group inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-card/70 px-5 py-3 text-sm font-semibold text-foreground hover:bg-muted transition-colors"
                >
                  <Play className="w-4 h-4 text-primary" />
                  Explore all {TOTAL_FEATURES} features
                </Link>
              </div>
            </Reveal>
            <Reveal delay={340}>
              <ul className="mt-8 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
                {['Human-approved actions', 'Workspace isolated', 'Undo built in', 'No card required'].map((t) => (
                  <li key={t} className="inline-flex items-center gap-1.5">
                    <Check className="w-3.5 h-3.5 text-emerald-500" />
                    {t}
                  </li>
                ))}
              </ul>
            </Reveal>
          </div>

          {/* Demo */}
          <Reveal variant="scale" delay={200} className="relative min-w-0 lg:pl-6">
            <div className="absolute -inset-6 -z-10 rounded-[2rem] bg-gradient-to-br from-primary/10 via-transparent to-secondary/60 blur-2xl" aria-hidden />
            <AgentDemo />

            <FloatCard className="-left-10 top-10" delay={0} rot={-3}>
              <div className="w-8 h-8 rounded-lg bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
                <Handshake className="w-4 h-4" />
              </div>
              <div className="leading-tight">
                <p className="text-xs font-bold text-foreground">Deal → Negotiation</p>
                <p className="font-mono text-[10px] text-muted-foreground">$48,000 · Acme</p>
              </div>
            </FloatCard>

            <FloatCard className="-right-8 top-1/3" delay={-2000} rot={2}>
              <div className="w-8 h-8 rounded-lg bg-primary/15 text-primary flex items-center justify-center">
                <FileText className="w-4 h-4" />
              </div>
              <div className="leading-tight">
                <p className="text-xs font-bold text-foreground">battlecard.pdf</p>
                <p className="font-mono text-[10px] text-muted-foreground">Indexed · 42 chunks</p>
              </div>
            </FloatCard>

            <FloatCard className="-left-6 bottom-8" delay={-4000} rot={2}>
              <div className="w-8 h-8 rounded-lg bg-secondary text-secondary-foreground flex items-center justify-center">
                <Search className="w-4 h-4" />
              </div>
              <div className="leading-tight">
                <p className="text-xs font-bold text-foreground">Prospect brief ready</p>
                <p className="font-mono text-[10px] text-muted-foreground">6 sources cited</p>
              </div>
            </FloatCard>

            <FloatCard className="right-6 -bottom-6" delay={-1000} rot={-2}>
              <div className="w-8 h-8 rounded-lg bg-muted text-foreground flex items-center justify-center">
                <UserRound className="w-4 h-4" />
              </div>
              <div className="leading-tight">
                <p className="text-xs font-bold text-foreground">Writes in your voice</p>
                <p className="font-mono text-[10px] text-muted-foreground">persona · tone · rules</p>
              </div>
            </FloatCard>
          </Reveal>
        </div>

        <Reveal delay={500} className="mt-16 flex justify-center">
          <Link
            to="/features"
            className="inline-flex flex-col items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Scroll to features"
          >
            <span className="font-mono text-[10px] uppercase tracking-widest">scroll</span>
            <ChevronDown className="w-4 h-4 animate-bounce" />
          </Link>
        </Reveal>
      </Container>
    </section>
  );
};
