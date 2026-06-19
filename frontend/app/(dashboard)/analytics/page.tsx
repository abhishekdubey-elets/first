'use client';

import { useQuery } from '@tanstack/react-query';
import { Trophy, Users } from 'lucide-react';
import { getAnalytics } from '@/lib/api';
import type { Analytics } from '@/lib/types';
import { PageHeader } from '@/components/PageHeader';
import { GlassCard } from '@/components/GlassCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { BarChartView } from '@/components/charts/BarChartCard';
import { LineChartView } from '@/components/charts/LineChartCard';
import { EmptyState } from '@/components/EmptyState';
import { Skeleton } from '@/components/Skeleton';
import { fmtNumber } from '@/lib/format';

export default function AnalyticsPage() {
  const { data, isLoading } = useQuery<Analytics>({
    queryKey: ['analytics'],
    queryFn: getAnalytics,
  });

  const topStates = (data?.by_state ?? [])
    .slice()
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);

  const topCadres = (data?.by_cadre ?? [])
    .slice()
    .sort((a, b) => b.count - a.count)
    .slice(0, 6);

  const topDistricts = (data?.by_district ?? [])
    .slice()
    .sort((a, b) => b.count - a.count)
    .slice(0, 10);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        description="Trends and concentrations across states, cadres, districts and time."
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard title="Transfers by state" subtitle="All recorded transfers">
          {isLoading ? (
            <Skeleton className="h-[280px] w-full" />
          ) : (data?.by_state.length ?? 0) > 0 ? (
            <BarChartView data={data!.by_state} xKey="state" yKey="count" />
          ) : (
            <EmptyState />
          )}
        </ChartCard>

        <ChartCard title="Transfers by month" subtitle="Discovery volume over time" delay={0.05}>
          {isLoading ? (
            <Skeleton className="h-[280px] w-full" />
          ) : (data?.by_month.length ?? 0) > 0 ? (
            <LineChartView data={data!.by_month} xKey="month" yKey="count" />
          ) : (
            <EmptyState />
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <GlassCard delay={0.1}>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
            <Trophy className="h-4 w-4 text-brand-cyan" /> Top states
          </h3>
          {isLoading ? (
            <div className="mt-4 space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : topStates.length === 0 ? (
            <p className="mt-3 text-sm text-slate-400">No data yet.</p>
          ) : (
            <ol className="mt-4 space-y-2">
              {topStates.map((s, i) => (
                <li
                  key={s.state}
                  className="flex items-center justify-between rounded-lg bg-white/[0.03] px-3 py-2 text-sm"
                >
                  <span className="flex items-center gap-2.5">
                    <span className="flex h-5 w-5 items-center justify-center rounded-md bg-accent-gradient text-[11px] font-semibold text-white">
                      {i + 1}
                    </span>
                    <span className="text-slate-200">{s.state}</span>
                  </span>
                  <span className="font-medium text-white">
                    {fmtNumber(s.count)}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </GlassCard>

        <GlassCard delay={0.15}>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
            <Users className="h-4 w-4 text-brand-violet" /> Most active cadres
          </h3>
          {isLoading ? (
            <div className="mt-4 space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : topCadres.length === 0 ? (
            <p className="mt-3 text-sm text-slate-400">No data yet.</p>
          ) : (
            <ul className="mt-4 space-y-2">
              {topCadres.map((c) => {
                const max = topCadres[0]?.count || 1;
                const pct = Math.max(6, (c.count / max) * 100);
                return (
                  <li key={c.cadre} className="text-sm">
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-slate-200">{c.cadre || '—'}</span>
                      <span className="text-xs text-slate-400">
                        {fmtNumber(c.count)}
                      </span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/5">
                      <div
                        className="h-full rounded-full bg-accent-gradient"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </GlassCard>

        <ChartCard
          title="District transfer frequency"
          subtitle="Top 10 districts"
          delay={0.2}
        >
          {isLoading ? (
            <Skeleton className="h-[320px] w-full" />
          ) : topDistricts.length > 0 ? (
            <BarChartView
              data={topDistricts}
              xKey="district"
              yKey="count"
              horizontal
              height={320}
            />
          ) : (
            <EmptyState />
          )}
        </ChartCard>
      </div>
    </div>
  );
}
