'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { ExternalLink, Newspaper, RefreshCw, Search, X } from 'lucide-react';
import { getNews } from '@/lib/api';
import type { Article, NewsQuery } from '@/lib/types';
import { PageHeader } from '@/components/PageHeader';
import { GlassCard } from '@/components/GlassCard';
import { SelectField } from '@/components/FilterBar';
import { StatusBadge } from '@/components/StatusBadge';
import { Pagination } from '@/components/Pagination';
import { EmptyState } from '@/components/EmptyState';
import { Skeleton } from '@/components/Skeleton';
import {
  fmtDateTime,
  fmtRelative,
  dayLabel,
  isWithinHours,
} from '@/lib/format';
import { cn } from '@/lib/utils';

const PAGE_SIZE = 12;
const DEFAULT_DAYS = '15';

const statusOptions = [
  { value: '', label: 'All statuses' },
  { value: 'discovered', label: 'Discovered' },
  { value: 'extracted', label: 'Extracted' },
  { value: 'parsed', label: 'Parsed' },
  { value: 'irrelevant', label: 'Irrelevant' },
  { value: 'failed', label: 'Failed' },
];

const periodOptions = [
  { value: '1', label: 'Last 24 hours' },
  { value: '3', label: 'Last 3 days' },
  { value: '7', label: 'Last 7 days' },
  { value: '15', label: 'Last 15 days' },
  { value: '', label: 'All time' },
];

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export default function NewsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [withTransfers, setWithTransfers] = useState(false);
  const [hideIrrelevant, setHideIrrelevant] = useState(true);
  const [days, setDays] = useState(DEFAULT_DAYS);

  const q = useDebounced(search.trim(), 300);

  // Any filter change goes back to the first page. Immediate filters reset
  // synchronously with the change; the debounced search resets when it lands.
  useEffect(() => {
    setPage(1);
  }, [q]);
  const onStatus = (v: string) => { setStatus(v); setPage(1); };
  const onDays = (v: string) => { setDays(v); setPage(1); };
  const onWithTransfers = (v: boolean) => { setWithTransfers(v); setPage(1); };
  const onHideIrrelevant = (v: boolean) => { setHideIrrelevant(v); setPage(1); };

  const query: NewsQuery = {
    page,
    page_size: PAGE_SIZE,
    status: status || undefined,
    q: q || undefined,
    with_transfers: withTransfers || undefined,
    exclude_irrelevant: hideIrrelevant || undefined,
    days: days ? Number(days) : undefined,
  };

  const { data, isLoading, isFetching, isError } = useQuery({
    queryKey: ['news', query],
    queryFn: () => getNews(query),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  });

  // Group by day, preserving the server's newest-first order within a page.
  const groups = useMemo(() => {
    const out: { label: string; items: Article[] }[] = [];
    for (const a of data?.items ?? []) {
      const label = dayLabel(a.published_at || a.created_at);
      const last = out[out.length - 1];
      if (last && last.label === label) last.items.push(a);
      else out.push({ label, items: [a] });
    }
    return out;
  }, [data]);

  const total = data?.total ?? 0;
  const hasFilters =
    Boolean(q) || Boolean(status) || withTransfers || days !== DEFAULT_DAYS || !hideIrrelevant;

  const resetFilters = () => {
    setSearch('');
    setStatus('');
    setWithTransfers(false);
    setHideIrrelevant(true);
    setDays(DEFAULT_DAYS);
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="News Feed"
        description="Latest IAS transfer articles discovered by the crawler — newest first, auto-refreshing every minute."
        action={
          <span className="flex items-center gap-1.5 text-xs text-slate-400">
            <RefreshCw
              className={cn(
                'h-3.5 w-3.5',
                isFetching && 'animate-spin text-brand-violet',
              )}
            />
            Live
          </span>
        }
      />

      {/* Filters */}
      <div className="glass rounded-2xl p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1.5 sm:col-span-2">
            <span className="text-xs font-medium text-slate-400">Search titles</span>
            <span className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="e.g. collector, transferred, Maharashtra…"
                className="input-glass pl-9 pr-9"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-500 hover:text-slate-200"
                  aria-label="Clear search"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </span>
          </label>
          <SelectField
            label="Period"
            value={days}
            onChange={onDays}
            options={periodOptions}
          />
          <SelectField
            label="Status"
            value={status}
            onChange={onStatus}
            options={statusOptions}
          />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2">
          <Toggle
            checked={withTransfers}
            onChange={onWithTransfers}
            label="Only with transfers"
          />
          <Toggle
            checked={hideIrrelevant}
            onChange={onHideIrrelevant}
            label="Hide irrelevant"
          />
          <span className="ml-auto flex items-center gap-3 text-xs text-slate-400">
            {data ? `${total.toLocaleString('en-IN')} articles` : 'Loading…'}
            {hasFilters && (
              <button
                type="button"
                onClick={resetFilters}
                className="text-brand-cyan hover:underline"
              >
                Reset
              </button>
            )}
          </span>
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full rounded-2xl" />
          ))}
        </div>
      ) : isError && !data ? (
        <GlassCard>
          <EmptyState
            title="Could not load the news feed"
            message="The API did not respond. It will retry automatically."
            icon={<Newspaper className="h-6 w-6" />}
          />
        </GlassCard>
      ) : (data?.items.length ?? 0) === 0 ? (
        <GlassCard>
          <EmptyState
            title="No articles found"
            message={
              hasFilters
                ? 'Nothing matches these filters — try widening the period or clearing the search.'
                : "The discovery agent hasn't surfaced any news yet."
            }
            icon={<Newspaper className="h-6 w-6" />}
          />
        </GlassCard>
      ) : (
        <>
          <div
            className={cn(
              'space-y-8 transition-opacity',
              isFetching && !isLoading && 'opacity-80',
            )}
          >
            {groups.map((g, gi) => (
              <section key={`${g.label}-${gi}`}>
                <div className="mb-3 flex items-center gap-3">
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    {g.label}
                  </h2>
                  <span className="text-[11px] text-slate-500">
                    {g.items.length} {g.items.length === 1 ? 'article' : 'articles'}
                  </span>
                  <span className="h-px flex-1 bg-white/10" />
                </div>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {g.items.map((a, i) => (
                    <ArticleCard key={a.id} article={a} delay={i * 0.03} />
                  ))}
                </div>
              </section>
            ))}
          </div>

          <GlassCard className="py-3">
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={total}
              onPageChange={setPage}
            />
          </GlassCard>
        </>
      )}
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex items-center gap-2.5"
    >
      <span
        className={cn(
          'relative h-5 w-9 rounded-full transition-colors',
          checked ? 'bg-accent-gradient' : 'bg-white/10',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform',
            checked ? 'translate-x-[18px]' : 'translate-x-0.5',
          )}
        />
      </span>
      <span className="text-sm text-slate-200">{label}</span>
    </button>
  );
}

function ArticleCard({ article: a, delay }: { article: Article; delay: number }) {
  const when = a.published_at || a.created_at;
  const isNew = isWithinHours(when, 24);
  const href = a.resolved_url || a.url;

  return (
    <GlassCard hover delay={delay} className="flex min-w-0 flex-col">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {isNew && (
            <span className="shrink-0 rounded-full bg-accent-gradient px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-white">
              New
            </span>
          )}
          <span className="truncate text-xs font-medium text-slate-300">
            {a.source_name || 'Unknown source'}
          </span>
        </div>
        <StatusBadge status={a.status} />
      </div>
      <h3 className="mt-3 line-clamp-3 flex-1 text-sm font-medium text-slate-100">
        {a.title || 'Untitled article'}
      </h3>
      <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
        <span title={fmtDateTime(when)}>{fmtRelative(when)}</span>
        {a.transfers_count > 0 && (
          <span className="rounded-full border border-emerald-500/25 bg-emerald-500/15 px-2 py-px text-[10px] font-medium text-emerald-300">
            {a.transfers_count} {a.transfers_count === 1 ? 'transfer' : 'transfers'}
          </span>
        )}
        {a.language && (
          <span className="ml-auto uppercase text-slate-500">{a.language}</span>
        )}
      </div>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-brand-cyan hover:underline"
      >
        Read article <ExternalLink className="h-3.5 w-3.5" />
      </a>
    </GlassCard>
  );
}
