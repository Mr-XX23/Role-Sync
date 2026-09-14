import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, FileText, ShieldCheck } from 'lucide-react';
import '../marketing/marketing.css';
import { BRAND } from '../marketing/marketingData';
import { MarketingNav } from '../marketing/sections/MarketingNav';
import { Footer } from '../marketing/sections/Footer';
import { Container, Eyebrow } from '../marketing/sections/shared';
import { LEGAL_DOCUMENTS, formatUpdated } from './legalContent';
import type { LegalSlug } from './legalContent';

const OTHER: Record<LegalSlug, { slug: LegalSlug; label: string }> = {
  privacy: { slug: 'terms', label: 'Terms of Service' },
  terms: { slug: 'privacy', label: 'Privacy Policy' },
};

/** Public Privacy Policy / Terms of Service page, sharing the marketing site's chrome. */
export const LegalPage: React.FC<{ slug: LegalSlug }> = ({ slug }) => {
  const doc = LEGAL_DOCUMENTS[slug];
  const other = OTHER[slug];
  const [active, setActive] = useState(doc.sections[0]?.id ?? '');

  useEffect(() => {
    const previous = document.title;
    document.title = `${doc.title} — ${BRAND.name}`;
    window.scrollTo({ top: 0 });
    return () => {
      document.title = previous;
    };
  }, [doc.title]);

  // Highlight the section nearest the top of the viewport in the side index.
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    const headings = doc.sections
      .map((section) => document.getElementById(section.id))
      .filter((el): el is HTMLElement => el !== null);
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: '-20% 0px -70% 0px', threshold: 0 }
    );
    headings.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [doc]);

  const Icon = slug === 'privacy' ? ShieldCheck : FileText;

  return (
    <div className="mk-page min-h-screen bg-background text-foreground font-sans antialiased">
      <MarketingNav />
      <main className="pt-28 sm:pt-32 pb-20">
        <Container>
          {/* Header */}
          <div className="max-w-3xl">
            <Eyebrow>Legal</Eyebrow>
            <div className="mt-4 flex items-start gap-4">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-primary/30 via-primary/15 to-transparent border border-primary/25 flex items-center justify-center text-primary shrink-0 shadow-xs">
                <Icon className="w-5 h-5" />
              </div>
              <div>
                <h1 className="font-serif text-4xl sm:text-5xl tracking-tight text-foreground">{doc.title}</h1>
                <p className="mt-2 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
                  Last updated {formatUpdated(doc.updated)}
                </p>
              </div>
            </div>
            <p className="mt-5 text-base sm:text-lg text-muted-foreground leading-relaxed text-pretty">{doc.summary}</p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Link
                to={LEGAL_DOCUMENTS[other.slug].path}
                className="inline-flex items-center gap-1.5 rounded-full border border-border/80 bg-card px-3.5 py-1.5 text-xs font-semibold text-foreground/80 hover:text-foreground hover:border-foreground/30 transition-colors"
              >
                Read the {other.label}
                <ArrowUpRight className="w-3.5 h-3.5" />
              </Link>
              <a
                href={`mailto:${BRAND.contactEmail}`}
                className="inline-flex items-center gap-1.5 rounded-full border border-border/80 bg-card px-3.5 py-1.5 text-xs font-semibold text-foreground/80 hover:text-foreground hover:border-foreground/30 transition-colors"
              >
                Ask a question
                <ArrowUpRight className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>

          <div className="mt-12 grid lg:grid-cols-[15rem_1fr] gap-10 xl:gap-16">
            {/* Index */}
            <aside className="hidden lg:block">
              <nav className="sticky top-24">
                <p className="font-mono text-[10px] font-bold uppercase tracking-widest text-muted-foreground/80 px-3 mb-2">
                  On this page
                </p>
                <ul className="space-y-0.5 border-l border-border/70">
                  {doc.sections.map((section) => (
                    <li key={section.id}>
                      <a
                        href={`#${section.id}`}
                        onClick={(event) => {
                          event.preventDefault();
                          document.getElementById(section.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }}
                        className={`block -ml-px border-l-2 pl-3 pr-2 py-1.5 text-xs leading-snug transition-colors ${
                          active === section.id
                            ? 'border-primary text-foreground font-semibold'
                            : 'border-transparent text-muted-foreground hover:text-foreground'
                        }`}
                      >
                        {section.title.replace(/^\d+\.\s*/, '')}
                      </a>
                    </li>
                  ))}
                </ul>
              </nav>
            </aside>

            {/* Body */}
            <article className="min-w-0 max-w-3xl">
              {doc.sections.map((section) => (
                <section key={section.id} id={section.id} className="scroll-mt-24 py-6 first:pt-0 border-b border-border/60 last:border-b-0">
                  <h2 className="font-serif text-2xl text-foreground tracking-tight">{section.title}</h2>
                  {section.paragraphs?.map((text) => (
                    <p key={text} className="mt-3 text-sm sm:text-[15px] text-foreground/85 leading-relaxed">
                      {text}
                    </p>
                  ))}
                  {section.bullets && (
                    <ul className="mt-3 space-y-2">
                      {section.bullets.map((text) => (
                        <li key={text} className="flex gap-3 text-sm sm:text-[15px] text-foreground/85 leading-relaxed">
                          <span className="mt-[0.55em] w-1.5 h-1.5 rounded-full bg-primary/70 shrink-0" />
                          <span>{text}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {section.after?.map((text) => (
                    <p key={text} className="mt-3 text-sm sm:text-[15px] text-foreground/85 leading-relaxed">
                      {text}
                    </p>
                  ))}
                </section>
              ))}
            </article>
          </div>
        </Container>
      </main>
      <Footer />
    </div>
  );
};

export default LegalPage;
