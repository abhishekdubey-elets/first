'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import {
  Radar,
  ArrowRight,
  Newspaper,
  Sparkles,
  Globe2,
  BarChart3,
  Table2,
  ShieldCheck,
  Bot,
  Database,
  Clock,
  CheckCircle2,
} from 'lucide-react';

const fadeUp = {
  initial: { opacity: 0, y: 18 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: '-80px' },
  transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] as const },
};

const FEATURES = [
  {
    icon: Newspaper,
    title: 'Autonomous discovery',
    body: 'Continuously scans Google News and trusted outlet feeds across English & Hindi for IAS transfer signals — no manual collection.',
  },
  {
    icon: Sparkles,
    title: 'AI extraction',
    body: 'An LLM reads each article and extracts structured records: officer, batch, cadre, from/to posting, district, and effective date.',
  },
  {
    icon: Globe2,
    title: 'Web enrichment',
    body: 'Missing fields are researched with live web search and filled automatically — gaps close over time instead of staying blank.',
  },
  {
    icon: BarChart3,
    title: 'Live analytics',
    body: 'Trends by state, cadre, district and month — the movement of the administrative machinery at a glance.',
  },
  {
    icon: Table2,
    title: 'Google Sheets sync',
    body: 'Every verified record can flow straight into your spreadsheet, ready to share with your team or newsroom.',
  },
  {
    icon: Bot,
    title: 'RAG assistant',
    body: 'Ask questions in plain language and get grounded answers cited from the underlying transfer records.',
  },
];

const STEPS = [
  { icon: Radar, title: 'Discover', body: 'Crawl news sources and queue fresh, relevant articles.' },
  { icon: Sparkles, title: 'Extract', body: 'Parse each article into structured transfer records.' },
  { icon: Globe2, title: 'Enrich', body: 'Backfill missing details via targeted web research.' },
  { icon: Database, title: 'Sync', body: 'Store, analyse, and export to your dashboard & Sheets.' },
];

const STATS = [
  { value: '24/7', label: 'Autonomous monitoring' },
  { value: '7+', label: 'News sources tracked' },
  { value: 'EN · HI', label: 'Languages covered' },
  { value: 'Hourly', label: 'Refresh cadence' },
];

function Nav() {
  return (
    <header className="sticky top-0 z-50 border-b border-white/[0.06] bg-ink-950/70 backdrop-blur-xl">
      <div className="section flex h-16 items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent-gradient shadow-glow">
            <Radar className="h-5 w-5 text-white" />
          </span>
          <span className="text-sm font-semibold text-white">
            IAS Transfer <span className="text-slate-400 font-normal">Intelligence</span>
          </span>
        </Link>
        <nav className="hidden items-center gap-8 text-sm text-slate-300 md:flex">
          <a href="#features" className="transition hover:text-white">Features</a>
          <a href="#how" className="transition hover:text-white">How it works</a>
          <a href="#stats" className="transition hover:text-white">Why it matters</a>
        </nav>
        <div className="flex items-center gap-2.5">
          <Link href="/login" className="btn-ghost px-3.5 py-1.5">Sign in</Link>
          <Link href="/dashboard" className="btn-gradient px-3.5 py-1.5">
            Open dashboard <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </header>
  );
}

function HeroMockup() {
  const rows = [
    { name: 'A. Sharma', from: 'Collector, Pune', to: 'Secy., Home Dept', state: 'Maharashtra' },
    { name: 'R. Iyer', from: 'DM, Lucknow', to: 'CEO, Dev. Authority', state: 'Uttar Pradesh' },
    { name: 'M. Verma', from: 'Jt. Secy., Finance', to: 'Collector, Indore', state: 'Madhya Pradesh' },
    { name: 'S. Nair', from: 'SDM, Kochi', to: 'Director, Tourism', state: 'Kerala' },
  ];
  return (
    <div className="card relative overflow-hidden p-4 shadow-2xl">
      <div className="mb-3 flex items-center gap-2 border-b border-white/[0.06] pb-3">
        <span className="h-2.5 w-2.5 rounded-full bg-rose-400/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-amber-400/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/70" />
        <span className="ml-3 inline-flex items-center gap-1.5 text-[11px] text-slate-400">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
          Live — updated hourly
        </span>
      </div>
      <div className="mb-4 grid grid-cols-3 gap-3">
        {[
          { k: 'Transfers', v: '1,284' },
          { k: 'This week', v: '37' },
          { k: 'States', v: '28' },
        ].map((s) => (
          <div key={s.k} className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-3">
            <p className="text-[11px] text-slate-400">{s.k}</p>
            <p className="mt-0.5 text-lg font-semibold text-white">{s.v}</p>
          </div>
        ))}
      </div>
      <div className="space-y-1.5">
        {rows.map((r) => (
          <div
            key={r.name}
            className="flex items-center justify-between rounded-lg border border-white/[0.05] bg-white/[0.02] px-3 py-2"
          >
            <div className="min-w-0">
              <p className="truncate text-xs font-medium text-white">{r.name}</p>
              <p className="truncate text-[11px] text-slate-400">
                {r.from} <span className="text-slate-600">→</span> {r.to}
              </p>
            </div>
            <span className="ml-3 shrink-0 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] text-slate-300">
              {r.state}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      <Nav />

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-grid-faint [background-size:48px_48px] [mask-image:radial-gradient(60%_50%_at_50%_0%,#000,transparent)]" />
        <div className="section relative grid items-center gap-12 py-20 lg:grid-cols-2 lg:py-28">
          <motion.div {...fadeUp}>
            <span className="eyebrow">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              Autonomous · AI-powered · Real-time
            </span>
            <h1 className="mt-5 text-4xl font-semibold leading-[1.1] text-white sm:text-5xl lg:text-6xl">
              Track every{' '}
              <span className="gradient-text">IAS officer transfer</span>{' '}
              the moment it breaks.
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-slate-300">
              An autonomous intelligence engine that discovers, extracts, enriches and
              organises IAS transfer news across India — turning scattered headlines into
              a clean, searchable, analytics-ready dataset.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link href="/dashboard" className="btn-gradient px-5 py-2.5 text-base">
                Open the dashboard <ArrowRight className="h-4 w-4" />
              </Link>
              <Link href="/login" className="btn-ghost px-5 py-2.5 text-base">
                Sign in
              </Link>
            </div>
            <div className="mt-7 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-slate-400">
              <span className="inline-flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" /> No manual collection
              </span>
              <span className="inline-flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" /> English &amp; Hindi
              </span>
              <span className="inline-flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" /> Exports to Sheets
              </span>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            className="relative"
          >
            <div className="absolute -inset-6 -z-10 rounded-[2rem] bg-accent-gradient opacity-20 blur-3xl" />
            <HeroMockup />
          </motion.div>
        </div>
      </section>

      {/* Stat band */}
      <section id="stats" className="border-y border-white/[0.06] bg-white/[0.02]">
        <div className="section grid grid-cols-2 gap-6 py-10 md:grid-cols-4">
          {STATS.map((s) => (
            <motion.div key={s.label} {...fadeUp} className="text-center">
              <p className="text-3xl font-semibold text-white">{s.value}</p>
              <p className="mt-1 text-sm text-slate-400">{s.label}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section id="features" className="section py-20 lg:py-28">
        <motion.div {...fadeUp} className="mx-auto max-w-2xl text-center">
          <span className="eyebrow"><ShieldCheck className="h-3.5 w-3.5" /> Built for accuracy</span>
          <h2 className="mt-4 text-3xl font-semibold text-white sm:text-4xl">
            From scattered news to structured intelligence
          </h2>
          <p className="mt-4 text-slate-400">
            A multi-agent pipeline does the tedious work — so you get a reliable,
            up-to-date record of administrative movement.
          </p>
        </motion.div>

        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <motion.div key={f.title} {...fadeUp} className="card card-hover p-6">
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04]">
                <f.icon className="h-5 w-5 text-brand-cyan" />
              </span>
              <h3 className="mt-4 text-base font-semibold text-white">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">{f.body}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="border-t border-white/[0.06] bg-white/[0.015]">
        <div className="section py-20 lg:py-28">
          <motion.div {...fadeUp} className="mx-auto max-w-2xl text-center">
            <span className="eyebrow"><Clock className="h-3.5 w-3.5" /> The pipeline</span>
            <h2 className="mt-4 text-3xl font-semibold text-white sm:text-4xl">
              Four agents, one clean dataset
            </h2>
          </motion.div>

          <div className="relative mt-14 grid gap-5 md:grid-cols-4">
            {STEPS.map((s, i) => (
              <motion.div key={s.title} {...fadeUp} className="card p-6">
                <div className="flex items-center justify-between">
                  <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-accent-gradient shadow-glow">
                    <s.icon className="h-5 w-5 text-white" />
                  </span>
                  <span className="text-sm font-semibold text-slate-600">0{i + 1}</span>
                </div>
                <h3 className="mt-4 text-base font-semibold text-white">{s.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">{s.body}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="section py-20 lg:py-24">
        <motion.div
          {...fadeUp}
          className="relative overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03] px-8 py-14 text-center"
        >
          <div className="pointer-events-none absolute -inset-px -z-10 bg-accent-gradient opacity-[0.07]" />
          <h2 className="mx-auto max-w-2xl text-3xl font-semibold text-white sm:text-4xl">
            See the administrative map of India update itself
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-slate-400">
            Sign in to explore the live dashboard — transfers, analytics, news feed and an
            AI assistant, all in one place.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link href="/dashboard" className="btn-gradient px-6 py-3 text-base">
              Open dashboard <ArrowRight className="h-4 w-4" />
            </Link>
            <Link href="/login" className="btn-ghost px-6 py-3 text-base">Sign in</Link>
          </div>
        </motion.div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/[0.06]">
        <div className="section flex flex-col items-center justify-between gap-4 py-8 sm:flex-row">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-gradient">
              <Radar className="h-4 w-4 text-white" />
            </span>
            <span className="text-sm text-slate-400">
              IAS Transfer Intelligence
            </span>
          </div>
          <p className="text-xs text-slate-500">
            © {new Date().getFullYear()} · Autonomous transfer intelligence · For research use
          </p>
        </div>
      </footer>
    </div>
  );
}
