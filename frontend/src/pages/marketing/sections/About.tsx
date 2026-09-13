import React from 'react';
import { Blocks, Bot, Database, Library, Server, ShieldCheck, Users } from 'lucide-react';
import { BRAND, VALUES } from '../marketingData';
import { Reveal } from '../Reveal';
import { Container, SectionHeading } from './shared';

const SERVICES = [
  { icon: ShieldCheck, name: 'Auth', note: 'identity · sessions · JWKS' },
  { icon: Users, name: 'Workspace', note: 'tenants · profiles · deals' },
  { icon: Library, name: 'Data pipeline', note: 'ingest · RAG · catalog' },
  { icon: Bot, name: 'Sales agent', note: 'LangGraph · tools · approvals' },
  { icon: Server, name: 'Gateway', note: 'routing · token verification' },
  { icon: Database, name: 'pgvector', note: 'one source of truth' },
];

export const About: React.FC = () => (
  <section id="about" className="relative scroll-mt-20 py-20 sm:py-28 overflow-hidden">
    <div className="absolute -z-10 -right-40 top-10 w-[520px] h-[520px] rounded-full bg-primary/10 blur-3xl mk-blob" aria-hidden />
    <Container>
      <div className="grid lg:grid-cols-[1fr_1fr] gap-14 items-start">
        <div>
          <SectionHeading
            align="left"
            eyebrow="About us"
            title={<>We build AI that earns the right to act.</>}
            description={
              <>
                {BRAND.name} started with a simple observation: revenue teams do not need another chatbot. They need a
                colleague who reads the same inbox, knows the same catalog, respects the same approvals and leaves an
                audit trail. So we built the agent, the knowledge layer and the guardrails as one product.
              </>
            }
          />
          <Reveal delay={240}>
            <p className="mt-5 text-base text-muted-foreground leading-relaxed">
              Today {BRAND.name} ships the Salesman Engine: an orchestrator with research, outreach and quote sub-agents,
              a production RAG pipeline on pgvector, a structured catalog with multi-location inventory, and a deals
              board the agent and your team share. Every piece is workspace-isolated and human-approved by design.
            </p>
          </Reveal>

          <div className="mt-10 grid sm:grid-cols-2 gap-4">
            {VALUES.map((v, i) => {
              const Icon = v.icon;
              return (
                <Reveal key={v.title} delay={i * 90}>
                  <div className="h-full rounded-xl border border-border/80 bg-card p-4 shadow-2xs">
                    <div className="w-9 h-9 rounded-lg bg-primary/15 border border-primary/25 text-primary flex items-center justify-center">
                      <Icon className="w-4 h-4" />
                    </div>
                    <h3 className="mt-3 text-sm font-bold text-foreground">{v.title}</h3>
                    <p className="mt-1.5 text-xs text-muted-foreground leading-relaxed">{v.description}</p>
                  </div>
                </Reveal>
              );
            })}
          </div>
        </div>

        {/* Architecture card */}
        <Reveal variant="right" delay={120} className="lg:sticky lg:top-28">
          <div className="rounded-2xl border border-border/80 bg-card shadow-xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-border/70 bg-muted/40">
              <div className="flex items-center gap-2">
                <Blocks className="w-4 h-4 text-primary" />
                <span className="text-xs font-bold text-foreground">Platform architecture</span>
              </div>
              <span className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">microservices</span>
            </div>
            <div className="p-5">
              <div className="rounded-xl border border-dashed border-primary/40 bg-primary/5 p-3 text-center">
                <p className="font-mono text-[10px] uppercase tracking-widest text-primary">React dashboard</p>
              </div>
              <div className="my-2 flex justify-center">
                <span className="h-5 w-px bg-border" />
              </div>
              <div className="rounded-xl border border-border/80 bg-background p-3 text-center">
                <p className="font-mono text-[10px] uppercase tracking-widest text-foreground">API gateway · Eureka · Config</p>
              </div>
              <div className="my-2 flex justify-center">
                <span className="h-5 w-px bg-border" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                {SERVICES.map((s, i) => {
                  const Icon = s.icon;
                  return (
                    <div
                      key={s.name}
                      className="mk-pop flex items-center gap-2.5 rounded-lg border border-border/80 bg-background px-3 py-2"
                      style={{ ['--mk-delay' as string]: `${300 + i * 80}ms` } as React.CSSProperties}
                    >
                      <div className="w-7 h-7 rounded-md bg-muted flex items-center justify-center text-primary shrink-0">
                        <Icon className="w-3.5 h-3.5" />
                      </div>
                      <div className="leading-tight min-w-0">
                        <p className="text-xs font-bold text-foreground truncate">{s.name}</p>
                        <p className="font-mono text-[9px] text-muted-foreground truncate">{s.note}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="mt-4 text-[11px] text-muted-foreground leading-relaxed">
                Spring Cloud services and Python engines register with discovery, pull config centrally and talk through
                a single signed gateway. Documents live in MinIO, vectors and catalog in PostgreSQL with pgvector, queues in Redis.
              </p>
            </div>
          </div>
        </Reveal>
      </div>
    </Container>
  </section>
);
