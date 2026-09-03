'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeftRight,
  CalendarDays,
  CalendarRange,
  ExternalLink,
  Newspaper,
  Radar,
  RefreshCw,
  AlertTriangle,
} from 'lucide-react';
import { getStats, getTransfers, getNews, getAgentStatus } from '@/lib/api';
import type { Stats, Transfer, Article, AgentStatus } from '@/lib/types';
import { PageHeader } from '@/components/PageHeader';
import { StatCard } from '@/components/StatCard';
import { GlassCard } from '@/components/GlassCard';
import { StatusBadge } from '@/components/StatusBadge';
import { ChartCard } from '@/components/charts/ChartCard';
import { BarChartView } from '@/components/charts/BarChartCard';
import { DataTable, Column } from '@/components/DataTable';
import { EmptyState } from '@/components/EmptyState';
import { CardSkeleton, TableSkeleton, Skeleton } from '@/components/Skeleton';
import {
  fmtDate,
  fmtDateTime,
  fmtRelative,
  fmtNumber,
  fmtInterval,
  safeDate,
  isWithinHours,
} from '@/lib/format';
import { cn } from '@/lib/utils';

// Shown when a field is empty even after the enrichment agent's web search.
const NO_INFO = <span className="italic text-slate-600">no info</span>;

const NEWS_LIMIT = 10;
const NEWS_DAYS = 7;

export default function DashboardPage() {
  const statsQ = useQuery<Stats>({
    queryKey: ['stats'],
    queryFn: getStats,
    refetchInterval: 60_000,
  });
  const transfersQ = useQuery({
    queryKey: ['transfers', { page_size: 8, sort: 'news_date', order: 'desc' }],
    queryFn: () => getTransfers({ page_size: 8, sort: 'news_date', order: 'desc' }),
    refetchInterval: 60_000,
  });
  const newsQ = useQuery({
    queryKey: [
      'news',
      { page_size: NEWS_LIMIT, days: NEWS_DAYS, exclude_irrelevant: true },
    ],
    queryFn: () =>
      getNews({ page_size: NEWS_LIMIT, days: NEWS_DAYS, exclude_irrelevant: true }),
    refetchInterval: 60_000,
  });
  const agentQ = useQuery<AgentStatus>({
    queryKey: ['agent-status'],
    queryFn: getAgentStatus,
    refetchInterval: 30_000,
  });

  const s = statsQ.data;
  const agent = agentQ.data;

  const columns: Column<Transfer>[] = [
    {
      key: 'officer',
      header: 'Officer',
      render: (r) => (
        <Link
          href={`/officers/${encodeURIComponent(r.officer_name)}`}
          className="font-medium text-white hover:text-brand-cyan"
        >
          {r.officer_name}
        </Link>
      ),
    },
    {
      key: 'from',
      header: 'From',
      render: (r) => (
        <span className="text-slate-300">
          {r.previous_district || r.previous_posting || NO_INFO}
        </span>
      ),
    },
    {
      key: 'to',
      header: 'To',
      render: (r) => (
        <span className="text-slate-300">
          {r.new_district || r.new_posting || NO_INFO}
        </span>
      ),
    },
    { key: 'state', header: 'State', render: (r) => r.state || NO_INFO },
    {
      key: 'date',
      header: 'Date',
      render: (r) => {
        // Prefer an explicit, parseable transfer date; otherwise fall back to
        // the article's publication date (the "news date").
        if (safeDate(r.transfer_date)) {
          return <span className="text-slate-400">{fmtDate(r.transfer_date)}</span>;
        }
        if (safeDate(r.news_date)) {
          return (
            <span className="text-slate-400">
              {fmtDate(r.news_date)}
              <span className="ml-1 text-[10px] uppercase tracking-wide text-slate-500">
                news
              </span>
            </span>
          );
        }
        return NO_INFO;
      },
    },
    {
      key: 'source',
      header: 'Source',
      render: (r) =>
        r.source_url ? (
          <a
            href={r.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-slate-300 hover:text-brand-cyan"
          >
            {r.source_name || 'Link'}
          </a>
        ) : (
          <span className="text-slate-400">{r.source_name || '—'}</span>
        ),
    },
  ];

  const articles = newsQ.data?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Live overview of the latest IAS transfer news and the intelligence pipeline."
      />

      {/* Row 1 — stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {statsQ.isLoading || !s ? (
          Array.from({ length: 4 }).map((_, i) => <CardSkeleton key={i} />)
        ) : (
          <>
            <StatCard
              label="News today"
              value={fmtNumber(s.news_today)}
              sub={`${fmtNumber(s.news_week)} this week`}
              icon={Newspaper}
              accent="cyan"
              delay={0}
            />
            <StatCard
              label="Transfers today"
              value={fmtNumber(s.today)}
              icon={CalendarDays}
              accent="violet"
              delay={0.05}
            />
            <StatCard
              label="This week"
              value={fmtNumber(s.this_week)}
              icon={CalendarRange}
              accent="indigo"
              delay={0.1}
            />
            <StatCard
              label="Total transfers"
              value={fmtNumber(s.total_transfers)}
              icon={ArrowLeftRight}
              accent="violet"
              delay={0.15}
            />
          </>
        )}
      </div>

      {/* Row 2 — latest news (hero) + pipeline */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2">
          <GlassCard delay={0.1} className="p-0">
            <div className="flex items-center justify-between gap-3 px-5 py-4">
              <div className="flex min-w-0 items-center gap-2.5">
                <h3 className="truncate text-sm font-semibold text-white">
                  Latest IAS transfer news
                </h3>
                <span
                  className="flex shrink-0 items-center gap-1.5 text-[11px] text-slate-400"
                  title="Auto-refreshes every minute"
                >
                  <RefreshCw
                    className={cn(
                      'h-3 w-3',
                      newsQ.isFetching && 'animate-spin text-brand-violet',
                    )}
                  />
                  Live
                </span>
              </div>
              <Link
                href="/news"
                className="shrink-0 text-xs font-medium text-brand-cyan hover:underline"
              >
                View all
              </Link>
            </div>
            <div className="px-5 pb-5">
              {newsQ.isLoading ? (
                <TableSkeleton rows={6} />
              ) : newsQ.isError ? (
                <EmptyState
                  title="Could not load the news feed"
                  message="The API did not respond. It will retry automatically."
                  icon={<AlertTriangle className="h-6 w-6" />}
                />
              ) : articles.length === 0 ? (
                <EmptyState
                  title="No articles in the last 7 days"
                  message="The discovery agent hasn't surfaced fresh news yet."
                  icon={<Newspaper className="h-6 w-6" />}
                />
              ) : (
                <ul className="space-y-2.5">
                  {articles.map((a: Article) => (
                    <NewsRow key={a.id} article={a} />
                  ))}
                </ul>
              )}
            </div>
          </GlassCard>
        </div>

        <div className="min-w-0">
          <PipelineCard
            agent={agent}
            isLoading={agentQ.isLoading}
            isError={agentQ.isError}
            lastCycleAt={s?.last_cycle_at ?? null}
          />
        </div>
      </div>

      {/* Row 3 — recent transfers */}
      <GlassCard delay={0.15} className="p-0">
        <div className="flex items-center justify-between px-5 py-4">
          <h3 className="text-sm font-semibold text-white">Recent transfers</h3>
          <Link
            href="/transfers"
            className="text-xs font-medium text-brand-cyan hover:underline"
          >
            View all
          </Link>
        </div>
        {transfersQ.isLoading ? (
          <div className="px-5 pb-5">
            <TableSkeleton rows={6} />
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={transfersQ.data?.items ?? []}
            rowKey={(r) => String(r.id)}
            empty={
              <EmptyState message="No transfers yet — the agents are still discovering." />
            }
          />
        )}
      </GlassCard>

      {/* Row 4 — by state */}
      <div className="grid grid-cols-1 gap-4">
        <ChartCard
          title="Transfers by state"
          subtitle="Distribution across cadre states"
          delay={0.2}
        >
          {statsQ.isLoading ? (
            <Skeleton className="h-[280px] w-full" />
          ) : s && s.by_state.length > 0 ? (
            <BarChartView data={s.by_state} xKey="state" yKey="count" />
          ) : (
            <EmptyState title="No state data" message="Awaiting first verified transfers." />
          )}
        </ChartCard>
      </div>
    </div>
  );
}

function NewsRow({ article: a }: { article: Article }) {
  const when = a.published_at || a.created_at;
  const isNew = isWithinHours(when, 24);
  const href = a.resolved_url || a.url;

  return (
    <li className="rounded-xl border border-white/5 bg-white/[0.03] p-3 transition hover:bg-white/[0.06]">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="group flex items-start gap-2"
          >
            <p className="line-clamp-2 text-sm font-medium text-slate-100 group-hover:text-brand-cyan">
              {a.title || 'Untitled article'}
            </p>
            <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500 group-hover:text-brand-cyan" />
          </a>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
            {isNew && (
              <span className="rounded-full bg-accent-gradient px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-white">
                New
              </span>
            )}
            <span className="truncate">{a.source_name || 'Unknown source'}</span>
            <span className="text-slate-600">·</span>
            <span title={fmtDateTime(when)}>{fmtRelative(when)}</span>
            {a.transfers_count > 0 && (
              <span className="rounded-full border border-emerald-500/25 bg-emerald-500/15 px-2 py-px text-[10px] font-medium text-emerald-300">
                {a.transfers_count} {a.transfers_count === 1 ? 'transfer' : 'transfers'}
              </span>
            )}
          </div>
        </div>
        <div className="shrink-0">
          <StatusBadge status={a.status} />
        </div>
      </div>
    </li>
  );
}

function PipelineCard({
  agent,
  isLoading,
  isError,
  lastCycleAt,
}: {
  agent: AgentStatus | undefined;
  isLoading: boolean;
  isError: boolean;
  lastCycleAt: string | null;
}) {
  const running = Boolean(agent?.running);
  const lastRun = agent?.last_run ?? lastCycleAt;
  const summary = agent?.summary;

  return (
    <GlassCard delay={0.15} className="flex h-full flex-col p-0">
      <div className="flex items-center justify-between gap-3 px-5 py-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
          <Radar className="h-4 w-4 text-brand-violet" /> Pipeline
        </h3>
        {!isLoading && !isError && (
          <span
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium',
              running
                ? 'border-emerald-500/25 bg-emerald-500/15 text-emerald-300'
                : 'border-slate-500/25 bg-slate-500/15 text-slate-300',
            )}
          >
            <span className="relative flex h-2 w-2">
              {running && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              )}
              <span
                className={cn(
                  'relative inline-flex h-2 w-2 rounded-full',
                  running ? 'bg-emerald-400' : 'bg-slate-500',
                )}
              />
            </span>
            {running ? 'Running' : 'Idle'}
          </span>
        )}
      </div>

      <div className="flex-1 px-5 pb-5">
        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : isError || !agent ? (
          <p className="text-sm text-slate-400">Pipeline status unavailable.</p>
        ) : (
          <div className="space-y-4">
            <dl className="space-y-2 text-sm">
              <div className="flex items-center justify-between gap-3">
                <dt className="text-slate-400">
                  {running ? 'Started' : 'Last run'}
                </dt>
                <dd
                  className="truncate text-right text-slate-200"
                  title={fmtDateTime(running ? agent.started_at : lastRun)}
                >
                  {running
                    ? fmtRelative(agent.started_at)
                    : lastRun
                      ? fmtRelative(lastRun)
                      : 'Never'}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-slate-400">Next run</dt>
                <dd
                  className="truncate text-right text-slate-200"
                  title={fmtDateTime(agent.next_run)}
                >
                  {running
                    ? 'In progress'
                    : agent.next_run
                      ? fmtRelative(agent.next_run)
                      : '—'}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-slate-400">Interval</dt>
                <dd className="text-right text-slate-200">
                  every {fmtInterval(agent.interval_seconds)}
                </dd>
              </div>
            </dl>

            <div>
              <p className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
                Last cycle
              </p>
              {summary ? (
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <Metric label="Articles" value={summary.articles} />
                  <Metric label="New" value={summary.new} />
                  <Metric label="Transfers" value={summary.transfers} />
                  <Metric label="Exported" value={summary.exported} />
                </div>
              ) : (
                <p className="mt-1.5 text-sm text-slate-500">
                  No completed cycle yet.
                </p>
              )}
            </div>

            {agent.last_error && (
              <p
                className="flex items-start gap-1.5 text-xs text-rose-300"
                title={agent.last_error}
              >
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span className="line-clamp-2 break-words">
                  {agent.last_error}
                </span>
              </p>
            )}
          </div>
        )}
      </div>
    </GlassCard>
  );
}

function Metric({ label, value }: { label: string; value?: number }) {
  return (
    <div className="rounded-lg bg-white/[0.04] px-3 py-2">
      <p className="text-lg font-semibold text-white">{fmtNumber(value ?? 0)}</p>
      <p className="text-[11px] text-slate-400">{label}</p>
    </div>
  );
}
