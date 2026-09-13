import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Building2, Headset, Mail, Send } from 'lucide-react';
import { Button } from '../../../components/common/Button';
import { Input } from '../../../components/common/Input';
import { BRAND } from '../marketingData';
import { Reveal } from '../Reveal';
import { Container, SectionHeading } from './shared';

const TOPICS = ['Book a demo', 'Pricing and plans', 'Enterprise connector', 'Partnership', 'Something else'];

const CHANNELS = [
  {
    icon: Mail,
    title: 'Talk to sales',
    description: 'Demos, pilots and rollout planning for your team.',
    action: { label: BRAND.contactEmail, href: `mailto:${BRAND.contactEmail}` },
  },
  {
    icon: Headset,
    title: 'Get support',
    description: 'Already a customer? File a ticket from the Support desk inside the app.',
    action: { label: 'Open support desk', to: '/salesman/support' },
  },
  {
    icon: Building2,
    title: 'Enterprise connectors',
    description: 'Need a custom database or system integration? Request it from the Connectors page.',
    action: { label: 'Request a connector', to: '/salesman/external-connector' },
  },
];

export const Contact: React.FC = () => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [topic, setTopic] = useState(TOPICS[0]);
  const [message, setMessage] = useState('');
  const [sent, setSent] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const subject = `[${topic}] ${company || name}`;
    const body = [`Name: ${name}`, `Email: ${email}`, `Company: ${company || '-'}`, '', message].join('\n');
    window.location.href = `mailto:${BRAND.contactEmail}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    setSent(true);
  };

  return (
    <section id="contact" className="relative scroll-mt-20 py-20 sm:py-28 bg-card/40 border-t border-border/60 overflow-hidden">
      <div className="absolute -z-10 -left-32 bottom-0 w-[480px] h-[480px] rounded-full bg-secondary/60 blur-3xl opacity-60" aria-hidden />
      <Container>
        <SectionHeading
          eyebrow="Contact us"
          title="Let's put an agent on your team."
          description="Tell us about your sales motion and we will show you RoleSync working against your own catalog and documents."
        />

        <div className="mt-14 grid lg:grid-cols-[0.9fr_1.1fr] gap-8 items-start">
          {/* Channels */}
          <div className="space-y-4">
            {CHANNELS.map((c, i) => {
              const Icon = c.icon;
              return (
                <Reveal key={c.title} delay={i * 100} variant="left">
                  <div className="mk-card-glow rounded-2xl border border-border/80 bg-card p-5 shadow-2xs">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-primary/15 border border-primary/25 text-primary flex items-center justify-center">
                        <Icon className="w-4.5 h-4.5" />
                      </div>
                      <h3 className="text-sm font-bold text-foreground">{c.title}</h3>
                    </div>
                    <p className="mt-3 text-xs text-muted-foreground leading-relaxed">{c.description}</p>
                    {'href' in c.action ? (
                      <a
                        href={c.action.href}
                        className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
                      >
                        {c.action.label}
                        <ArrowUpRight className="w-3.5 h-3.5" />
                      </a>
                    ) : (
                      <Link
                        to={c.action.to}
                        className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
                      >
                        {c.action.label}
                        <ArrowUpRight className="w-3.5 h-3.5" />
                      </Link>
                    )}
                  </div>
                </Reveal>
              );
            })}
          </div>

          {/* Form */}
          <Reveal variant="right" delay={150}>
            <form
              onSubmit={handleSubmit}
              className="rounded-2xl border border-border/80 bg-card p-6 sm:p-8 shadow-xl space-y-4"
              noValidate={false}
            >
              <div className="grid sm:grid-cols-2 gap-4">
                <Input
                  label="Your name"
                  id="contact-name"
                  placeholder="Jane Doe"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
                <Input
                  label="Work email"
                  id="contact-email"
                  type="email"
                  placeholder="name@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                <Input
                  label="Company"
                  id="contact-company"
                  placeholder="Acme Inc."
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                />
                <div>
                  <label htmlFor="contact-topic" className="block text-sm font-medium text-foreground mb-1.5">
                    Topic
                  </label>
                  <select
                    id="contact-topic"
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                    className="w-full px-3.5 py-2.5"
                  >
                    {TOPICS.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <label htmlFor="contact-message" className="block text-sm font-medium text-foreground mb-1.5">
                  How can we help?
                </label>
                <textarea
                  id="contact-message"
                  rows={5}
                  required
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Tell us about your team, your catalog and what you'd like the agent to take off your plate."
                  className="w-full resize-y"
                />
              </div>
              <Button type="submit" icon={<Send className="w-4 h-4" />} className="mt-2">
                {sent ? 'Opened in your mail app' : 'Send message'}
              </Button>
              <p className="text-[11px] text-muted-foreground text-center">
                This opens a pre-filled email to {BRAND.contactEmail}. We reply within one business day.
              </p>
            </form>
          </Reveal>
        </div>
      </Container>
    </section>
  );
};
