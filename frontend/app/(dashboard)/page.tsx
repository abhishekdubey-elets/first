'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeftRight,
  CalendarDays,
  CalendarRange,
  CalendarClock,
  ExternalLink,
} from 'lucide-react';
import { getStats, getTransfers, getNews } from '@/lib/api';
import type { Stats, Transfer, Article } from '@/lib/types';
import { PageHeader } from '@/components/PageHeader';
import { StatCard } from '@/components/StatCard';
import { GlassCard } from '@/components/GlassCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { BarChartView } from '@/components/charts/BarChartCard';
import { DataTable, Column } from '@/components/DataTable';
import { EmptyState } from '@/components/EmptyState';
import { CardSkeleton, TableSkeleton, Skeleton } from '@/components/Skeleton';
import { fmtDate, fmtRelative, fmtNumber, safeDate } from '@/lib/format';

// Shown when a field is empty even after the enrichment agent's web search.
const NO_INFO = <span className="italic text-slate-600">no info</span>;

export default function DashboardPage() {
  const statsQ = useQuery<Stats>({ queryKey: ['stats'], queryFn: getStats });
  const transfersQ = useQuery({
    queryKey: ['transfers', { page_size: 8, sort: 'news_date' }],
    queryFn: () => getTransfers({ page_size: 8, sort: 'news_date', order: 'desc' }),
  });
  const newsQ = useQuery({
    queryKey: ['news', { page_size: 6 }],
    queryFn: () => getNews({ page_size: 6 }),
  });

  const s = statsQ.data;

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

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Live overview of discovered IAS transfers and intelligence signals."
      />

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {statsQ.isLoading || !s ? (
          Array.from({ length: 4 }).map((_, i) => <CardSkeleton key={i} />)
        ) : (
          <>
            <StatCard
              label="Total transfers"
              value={fmtNumber(s.total_transfers)}
              icon={ArrowLeftRight}
              accent="indigo"
              delay={0}
            />
            <StatCard
              label="Today"
              value={fmtNumber(s.today)}
              icon={CalendarDays}
              accent="violet"
              delay={0.05}
            />
            <StatCard
              label="This week"
              value={fmtNumber(s.this_week)}
              icon={CalendarRange}
              accent="cyan"
              delay={0.1}
            />
            <StatCard
              label="This month"
              value={fmtNumber(s.this_month)}
              icon={CalendarClock}
              accent="indigo"
              delay={0.15}
            />
          </>
        )}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-4">
        <ChartCard
          title="Transfers by state"
          subtitle="Distribution across cadre states"
          delay={0.1}
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

      {/* Recent transfers + News */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <GlassCard delay={0.1} className="p-0">
            <div className="flex items-center justify-between px-5 py-4">
              <h3 className="text-sm font-semibold text-white">
                Recent transfers
              </h3>
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
                rowKey={(r) => r.id}
                empty={
                  <EmptyState message="No transfers yet — the agents are still discovering." />
                }
              />
            )}
          </GlassCard>
        </div>

        <GlassCard delay={0.15} className="p-0">
          <div className="flex items-center justify-between px-5 py-4">
            <h3 className="text-sm font-semibold text-white">Latest news</h3>
            <Link
              href="/news"
              className="text-xs font-medium text-brand-cyan hover:underline"
            >
              View all
            </Link>
          </div>
          <div className="px-5 pb-5">
            {newsQ.isLoading ? (
              <TableSkeleton rows={5} />
            ) : (newsQ.data?.items?.length ?? 0) === 0 ? (
              <EmptyState message="No articles discovered yet." />
            ) : (
              <ul className="space-y-3">
                {newsQ.data!.items.map((a: Article) => (
                  <li
                    key={a.id}
                    className="rounded-xl border border-white/5 bg-white/[0.03] p-3 transition hover:bg-white/[0.06]"
                  >
                    <a
                      href={a.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="group flex items-start gap-2"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="line-clamp-2 text-sm font-medium text-slate-100 group-hover:text-brand-cyan">
                          {a.title || 'Untitled article'}
                        </p>
                        <p className="mt-1 text-xs text-slate-400">
                          {a.source_name || 'Unknown'} · {fmtRelative(a.published_at || a.created_at)}
                        </p>
                      </div>
                      <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500 group-hover:text-brand-cyan" />
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </GlassCard>
      </div>
    </div>
  );
}
