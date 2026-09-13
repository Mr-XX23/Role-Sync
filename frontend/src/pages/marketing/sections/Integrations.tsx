import React from 'react';
import { CalendarDays, Clock, FileText, FolderOpen, Globe, KeyRound, Mail, MessagesSquare, Sparkles, Webhook } from 'lucide-react';
import { Reveal } from '../Reveal';
import { Container, SectionHeading } from './shared';

const ORBIT_ITEMS = [
  { icon: Mail, label: 'Gmail', angle: 0 },
  { icon: FolderOpen, label: 'Drive', angle: 60 },
  { icon: CalendarDays, label: 'Calendar', angle: 120 },
  { icon: MessagesSquare, label: 'Slack', angle: 180 },
  { icon: FileText, label: 'Notion', angle: 240 },
  { icon: Globe, label: 'Web', angle: 300 },
];

const SYNC_MODES = [
  { icon: KeyRound, title: 'One-click OAuth', description: 'Authorise in a popup. RoleSync never asks you to paste an API key for Google, Slack or Notion.' },
  { icon: Clock, title: 'Scheduled sync', description: 'Every 2 minutes, 30 minutes, hourly, 6-hourly or daily, per connector, with full re-sync on demand.' },
  { icon: Webhook, title: 'Webhook push', description: 'Providers push changes the moment they happen, so the agent reads today’s thread, not yesterday’s.' },
];

const Orbit: React.FC = () => (
  <div className="relative mx-auto w-[300px] h-[300px] sm:w-[360px] sm:h-[360px]">
    {/* rings */}
    <div className="absolute inset-0 rounded-full border border-border/70" />
    <div className="absolute inset-[18%] rounded-full border border-dashed border-border/70" />
    <div className="absolute inset-[36%] rounded-full bg-primary/10 blur-xl" />

    {/* centre */}
    <div className="absolute inset-0 flex items-center justify-center">
      <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-primary/30 via-primary/15 to-transparent border border-primary/30 shadow-lg flex flex-col items-center justify-center text-primary bg-card">
        <Sparkles className="w-6 h-6" />
        <span className="font-mono text-[9px] font-bold uppercase tracking-widest mt-1 text-foreground">Vault</span>
      </div>
    </div>

    {/* orbiting items: the ring rotates, each item counter-rotates so labels stay upright */}
    <div className="mk-orbit absolute inset-0" style={{ ['--mk-duration' as string]: '36s' } as React.CSSProperties}>
      {ORBIT_ITEMS.map((it) => {
        const Icon = it.icon;
        return (
          <div
            key={it.label}
            className="absolute left-1/2 top-1/2"
            style={{ transform: `rotate(${it.angle}deg) translate(0, -150px)` }}
          >
            <div
              className="mk-orbit -translate-x-1/2 -translate-y-1/2"
              data-reverse="true"
              style={{ ['--mk-duration' as string]: '36s' } as React.CSSProperties}
            >
              <div className="flex flex-col items-center gap-1" style={{ transform: `rotate(${-it.angle}deg)` }}>
                <div className="w-11 h-11 rounded-xl bg-card border border-border/80 shadow-md flex items-center justify-center text-foreground">
                  <Icon className="w-5 h-5 text-primary" />
                </div>
                <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted-foreground">{it.label}</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  </div>
);

export const Integrations: React.FC = () => (
  <section id="integrations" className="relative scroll-mt-20 py-20 sm:py-28 overflow-hidden">
    <div className="absolute -z-10 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] rounded-full bg-secondary/40 blur-3xl opacity-50" aria-hidden />
    <Container>
      <div className="grid lg:grid-cols-2 gap-14 items-center">
        <div>
          <SectionHeading
            align="left"
            eyebrow="Integrations"
            title="Your inbox, files, calendar and chat, one search away."
            description="Five native connectors feed the Knowledge Vault and the agent's tools. Keep them fresh on a schedule or by webhook, and audit every sync run."
          />
          <div className="mt-10 space-y-4">
            {SYNC_MODES.map((m, i) => {
              const Icon = m.icon;
              return (
                <Reveal key={m.title} delay={i * 100} variant="left">
                  <div className="flex items-start gap-4 rounded-xl border border-border/80 bg-card p-4 shadow-2xs">
                    <div className="w-10 h-10 rounded-lg bg-primary/15 border border-primary/25 text-primary flex items-center justify-center shrink-0">
                      <Icon className="w-4.5 h-4.5" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-foreground">{m.title}</h3>
                      <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{m.description}</p>
                    </div>
                  </div>
                </Reveal>
              );
            })}
          </div>
        </div>
        <Reveal variant="scale" delay={150}>
          <Orbit />
        </Reveal>
      </div>
    </Container>
  </section>
);
