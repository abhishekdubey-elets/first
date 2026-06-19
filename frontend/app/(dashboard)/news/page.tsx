'use client';

import { useState } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { ExternalLink, Newspaper, RefreshCw } from 'lucide-react';
import { getNews } from '@/lib/api';
import type { Article } from '@/lib/types';
import { PageHeader } from '@/components/PageHeader';
import { GlassCard } from '@/components/GlassCard';
import { SelectField } from '@/components/FilterBar';
import { StatusBadge } from '@/components/StatusBadge';
import { Pagination } from '@/components/Pagination';
import { EmptyState } from '@/components/EmptyState';
import { Skeleton } from '@/components/Skeleton';
import { fmtDateTime, fmtRelative } from '@/lib/format';

const PAGE_SIZE = 12;

const statusOptions = [
  { value: '', label: 'All articles' },
  { value: 'discovered', label: 'Discovered' },
  { value: 'extracted', label: 'Extracted' },
  { value: 'parsed', label: 'Parsed' },
  { value: 'irrelevant', label: 'Irrelevant' },
  { value: 'failed', label: 'Failed' },
];

export default function NewsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['news-feed', { page, status }],
    queryFn: () =>
      getNews({ page, page_size: PAGE_SIZE, status: status || undefined }),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="News Feed"
        description="Articles discovered by the crawler — auto-refreshing every 30 seconds."
        action={
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 text-xs text-slate-400">
              <RefreshCw
                className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin text-brand-violet' : ''}`}
              />
              Live
            </span>
            <div className="w-48">
              <SelectField
                label=""
                value={status}
                onChange={(v) => {
                  setStatus(v);
                  setPage(1);
                }}
                options={statusOptions}
              />
            </div>
          </div>
        }
      />

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-36 w-full rounded-2xl" />
          ))}
        </div>
      ) : (data?.items.length ?? 0) === 0 ? (
        <GlassCard>
          <EmptyState
            title="No articles yet"
            message="The discovery agent hasn't surfaced any news for this filter."
            icon={<Newspaper className="h-6 w-6" />}
          />
        </GlassCard>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {data!.items.map((a: Article, i) => (
              <GlassCard key={a.id} hover delay={i * 0.03} className="flex flex-col">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-xs font-medium text-slate-300">
                    {a.source_name || 'Unknown source'}
                  </span>
                  <StatusBadge status={a.status} />
                </div>
                <h3 className="mt-3 line-clamp-3 flex-1 text-sm font-medium text-slate-100">
                  {a.title || 'Untitled article'}
                </h3>
                <div className="mt-3 flex items-center justify-between gap-2 text-xs text-slate-400">
                  <span title={fmtDateTime(a.published_at || a.created_at)}>
                    {fmtRelative(a.published_at || a.created_at)}
                  </span>
                  {a.language && (
                    <span className="uppercase">{a.language}</span>
                  )}
                </div>
                <a
                  href={a.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-brand-cyan hover:underline"
                >
                  Read article <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </GlassCard>
            ))}
          </div>

          <GlassCard className="py-3">
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={data!.total}
              onPageChange={setPage}
            />
          </GlassCard>
        </>
      )}
    </div>
  );
}
