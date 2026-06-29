'use client';

import { Suspense, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { Search, SlidersHorizontal, RotateCcw } from 'lucide-react';
import { getTransfers } from '@/lib/api';
import type { Transfer, TransfersQuery } from '@/lib/types';
import { PageHeader } from '@/components/PageHeader';
import { GlassCard } from '@/components/GlassCard';
import { FilterBar, TextField, SelectField } from '@/components/FilterBar';
import { DataTable, Column } from '@/components/DataTable';
import { Pagination } from '@/components/Pagination';
import { EmptyState } from '@/components/EmptyState';
import { TableSkeleton } from '@/components/Skeleton';
import { fmtDate } from '@/lib/format';

const PAGE_SIZE = 12;

const sortOptions = [
  { value: 'news_date:desc', label: 'Latest news first' },
  { value: 'news_date:asc', label: 'Oldest news first' },
  { value: 'officer:asc', label: 'Officer A–Z' },
];

function TransfersExplorer() {
  const searchParams = useSearchParams();
  const initialQ = searchParams.get('q') ?? '';

  const [page, setPage] = useState(1);
  const [q, setQ] = useState(initialQ);
  const [state, setState] = useState('');
  const [district, setDistrict] = useState('');
  const [officer, setOfficer] = useState('');
  const [batch, setBatch] = useState('');
  const [cadre, setCadre] = useState('');
  const [source, setSource] = useState('');
  const [sortSel, setSortSel] = useState('news_date:desc');

  useEffect(() => {
    setQ(initialQ);
    setPage(1);
  }, [initialQ]);

  const [sort, order] = sortSel.split(':') as [
    TransfersQuery['sort'],
    TransfersQuery['order'],
  ];

  const query: TransfersQuery = {
    page,
    page_size: PAGE_SIZE,
    q: q || undefined,
    state: state || undefined,
    district: district || undefined,
    officer: officer || undefined,
    batch: batch || undefined,
    cadre: cadre || undefined,
    source: source || undefined,
    sort,
    order,
  };

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['transfers', query],
    queryFn: () => getTransfers(query),
    placeholderData: keepPreviousData,
  });

  const reset = () => {
    setQ('');
    setState('');
    setDistrict('');
    setOfficer('');
    setBatch('');
    setCadre('');
    setSource('');
    setSortSel('news_date:desc');
    setPage(1);
  };

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
      key: 'batch',
      header: 'Batch · Cadre',
      render: (r) => (
        <span className="text-slate-300">
          {r.ias_batch || '—'}{' '}
          <span className="text-slate-500">·</span> {r.cadre || '—'}
        </span>
      ),
    },
    {
      key: 'from',
      header: 'From',
      render: (r) => (
        <span className="text-slate-300">
          {r.previous_posting || r.previous_district || '—'}
        </span>
      ),
    },
    {
      key: 'to',
      header: 'To',
      render: (r) => (
        <span className="text-slate-300">
          {r.new_posting || r.new_district || '—'}
        </span>
      ),
    },
    { key: 'state', header: 'State', render: (r) => r.state || '—' },
    {
      key: 'news_date',
      header: 'News date',
      render: (r) => (
        <span className="text-slate-400">
          {fmtDate(r.news_date || r.transfer_date)}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Transfer Explorer"
        description="Filter, search and drill into every discovered transfer record."
      />

      <FilterBar>
        <TextField label="Search" value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="officer, posting…" />
        <TextField label="State" value={state} onChange={(v) => { setState(v); setPage(1); }} placeholder="e.g. Maharashtra" />
        <TextField label="District" value={district} onChange={(v) => { setDistrict(v); setPage(1); }} placeholder="e.g. Pune" />
        <TextField label="Officer" value={officer} onChange={(v) => { setOfficer(v); setPage(1); }} placeholder="officer name" />
        <TextField label="Batch" value={batch} onChange={(v) => { setBatch(v); setPage(1); }} placeholder="e.g. 2011" />
        <TextField label="Cadre" value={cadre} onChange={(v) => { setCadre(v); setPage(1); }} placeholder="cadre" />
        <TextField label="Source" value={source} onChange={(v) => { setSource(v); setPage(1); }} placeholder="source name" />
        <SelectField label="Sort by" value={sortSel} onChange={(v) => { setSortSel(v); setPage(1); }} options={sortOptions} />
      </FilterBar>

      <div className="flex items-center justify-between">
        <p className="flex items-center gap-2 text-xs text-slate-400">
          <SlidersHorizontal className="h-3.5 w-3.5" />
          {data ? `${data.total.toLocaleString('en-IN')} results` : 'Loading…'}
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
            rowKey={(r) => r.id}
            empty={
              <EmptyState
                title="No matching transfers"
                message="Try widening your filters, or wait for the agents to discover more."
                icon={<Search className="h-6 w-6" />}
              />
            }
          />
        )}
        {data && data.total > 0 && (
          <div className="px-5 pb-5">
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={data.total}
              onPageChange={setPage}
            />
          </div>
        )}
      </GlassCard>
    </div>
  );
}

export default function TransfersPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} />}>
      <TransfersExplorer />
    </Suspense>
  );
}
