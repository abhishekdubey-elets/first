'use client';

import { Suspense, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { RotateCcw, SlidersHorizontal, UserRound } from 'lucide-react';
import { getOfficers } from '@/lib/api';
import type { OfficerSummary, OfficersQuery } from '@/lib/types';
import { PageHeader } from '@/components/PageHeader';
import { GlassCard } from '@/components/GlassCard';
import { FilterBar, TextField, SelectField } from '@/components/FilterBar';
import { DataTable, Column } from '@/components/DataTable';
import { Pagination } from '@/components/Pagination';
import { EmptyState } from '@/components/EmptyState';
import { OfficerAvatar } from '@/components/OfficerAvatar';
import { TableSkeleton } from '@/components/Skeleton';
import { fmtDate } from '@/lib/format';

const PAGE_SIZE = 15;

const sortOptions = [
  { value: 'recent', label: 'Most recently moved' },
  { value: 'movements', label: 'Most movements' },
  { value: 'name', label: 'Name A–Z' },
];

function OfficersDirectory() {
  const searchParams = useSearchParams();
  const initialQ = searchParams.get('q') ?? '';

  const [page, setPage] = useState(1);
  const [q, setQ] = useState(initialQ);
  const [state, setState] = useState('');
  const [batch, setBatch] = useState('');
  const [cadre, setCadre] = useState('');
  const [sort, setSort] = useState<NonNullable<OfficersQuery['sort']>>('recent');

  useEffect(() => {
    setQ(initialQ);
    setPage(1);
  }, [initialQ]);

  const query: OfficersQuery = {
    page,
    page_size: PAGE_SIZE,
    q: q || undefined,
    state: state || undefined,
    batch: batch || undefined,
    cadre: cadre || undefined,
    sort,
  };

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['officers', query],
    queryFn: () => getOfficers(query),
    placeholderData: keepPreviousData,
  });

  const reset = () => {
    setQ('');
    setState('');
    setBatch('');
    setCadre('');
    setSort('recent');
    setPage(1);
  };

  const columns: Column<OfficerSummary>[] = [
    {
      key: 'officer',
      header: 'Officer',
      render: (o) => (
        <Link
          href={`/officers/${encodeURIComponent(o.id)}`}
          className="flex items-center gap-3 font-medium text-white hover:text-brand-cyan"
        >
          <OfficerAvatar name={o.name} photoUrl={o.photo_url} />
          <span>
            {o.name}
            {o.aliases.length > 0 && (
              <span className="block text-xs font-normal text-slate-500">
                also {o.aliases.join(', ')}
              </span>
            )}
          </span>
        </Link>
      ),
    },
    {
      key: 'batch',
      header: 'Batch · Cadre',
      render: (o) => (
        <span className="text-slate-300">
          {o.batch || '—'} <span className="text-slate-500">·</span> {o.cadre || '—'}
        </span>
      ),
    },
    {
      key: 'current',
      header: 'Current posting',
      render: (o) => (
        <span className="text-slate-300">
          {o.current_role}
          {(o.current_district || o.current_state) && (
            <span className="block text-xs text-slate-500">
              {[o.current_district, o.current_state].filter(Boolean).join(', ')}
            </span>
          )}
        </span>
      ),
    },
    {
      key: 'moves',
      header: 'Moves',
      className: 'text-right',
      render: (o) => <span className="text-slate-300">{o.movements_count}</span>,
    },
    {
      key: 'last',
      header: 'Last moved',
      render: (o) => (
        <span className="text-slate-400">
          {fmtDate(o.last_movement_date)}
          {o.last_movement && (
            <span className="block text-xs text-slate-500">{o.last_movement}</span>
          )}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Officers"
        description="Everyone the agents have seen transferred, with a profile for each."
      />

      <FilterBar>
        <TextField label="Name" value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="any spelling" />
        <TextField label="State" value={state} onChange={(v) => { setState(v); setPage(1); }} placeholder="served in, e.g. Bihar" />
        <TextField label="Batch" value={batch} onChange={(v) => { setBatch(v); setPage(1); }} placeholder="e.g. 2009" />
        <TextField label="Cadre" value={cadre} onChange={(v) => { setCadre(v); setPage(1); }} placeholder="cadre" />
        <SelectField
          label="Sort by"
          value={sort}
          onChange={(v) => { setSort(v as NonNullable<OfficersQuery['sort']>); setPage(1); }}
          options={sortOptions}
        />
      </FilterBar>

      <div className="flex items-center justify-between">
        <p className="flex items-center gap-2 text-xs text-slate-400">
          <SlidersHorizontal className="h-3.5 w-3.5" />
          {data ? `${data.total.toLocaleString('en-IN')} officers` : 'Loading…'}
          {isFetching && !isLoading && <span className="text-brand-violet">· updating</span>}
        </p>
        <button onClick={reset} className="btn-ghost px-3 py-1.5 text-xs">
          <RotateCcw className="h-3.5 w-3.5" /> Reset filters
        </button>
      </div>

      <GlassCard className="p-0">
        {isLoading ? (
          <div className="p-5">
            <TableSkeleton rows={8} />
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={data?.items ?? []}
            rowKey={(o) => o.id}
            empty={
              <EmptyState
                title="No matching officers"
                message="Try another spelling or widen the filters."
                icon={<UserRound className="h-6 w-6" />}
              />
            }
          />
        )}
        {data && data.total > 0 && (
          <div className="px-5 pb-5">
            <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPageChange={setPage} />
          </div>
        )}
      </GlassCard>
    </div>
  );
}

export default function OfficersPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} />}>
      <OfficersDirectory />
    </Suspense>
  );
}
