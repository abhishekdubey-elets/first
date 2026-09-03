'use client';

import { useMemo } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  ArrowLeft,
  MapPin,
  Building2,
  FileText,
  ExternalLink,
  Newspaper,
  UserRound,
} from 'lucide-react';
import { getOfficerTransfers } from '@/lib/api';
import type { Transfer } from '@/lib/types';
import { PageHeader } from '@/components/PageHeader';
import { GlassCard } from '@/components/GlassCard';
import { StatusBadge } from '@/components/StatusBadge';
import { EmptyState } from '@/components/EmptyState';
import { Skeleton } from '@/components/Skeleton';
import { fmtDate, safeDate } from '@/lib/format';

// Best-effort timestamp for ordering: parseable transfer date, else the
// article's publication date, else when we discovered the record.
function sortKey(t: Transfer): number {
  return (
    (
      safeDate(t.transfer_date) ??
      safeDate(t.news_date) ??
      safeDate(t.created_at)
    )?.getTime() ?? 0
  );
}

export default function OfficerProfilePage() {
  const params = useParams<{ name: string }>();
  const name = decodeURIComponent(params.name);

  const { data, isLoading } = useQuery({
    queryKey: ['officer', name],
    queryFn: () => getOfficerTransfers(name),
  });

  // The backend matches officer names by substring, so narrow to exact
  // (case-insensitive, trimmed) matches; most recent first for the timeline
  // & "current posting". `transfer_date` is free-form text, so never feed it
  // straight into `new Date()`.
  const sorted = useMemo(() => {
    const target = name.trim().toLowerCase();
    const list = (data ?? []).filter(
      (t) => (t.officer_name ?? '').trim().toLowerCase() === target,
    );
    list.sort((a, b) => sortKey(b) - sortKey(a));
    return list;
  }, [data, name]);

  const current = sorted[0];

  const sources = useMemo(() => {
    const seen = new Map<string, { name: string; url: string }>();
    for (const t of sorted) {
      if (t.source_url && !seen.has(t.source_url)) {
        seen.set(t.source_url, {
          name: t.source_name || t.source_url,
          url: t.source_url,
        });
      }
    }
    return Array.from(seen.values());
  }, [sorted]);

  const govOrders = useMemo(() => {
    const seen = new Map<string, { label: string; url: string }>();
    for (const t of sorted) {
      if (t.gov_order_link && !seen.has(t.gov_order_link)) {
        seen.set(t.gov_order_link, {
          label: t.notification_number || 'Government order',
          url: t.gov_order_link,
        });
      }
    }
    return Array.from(seen.values());
  }, [sorted]);

  return (
    <div className="space-y-6">
      <Link
        href="/transfers"
        className="inline-flex items-center gap-1.5 text-sm text-slate-400 transition hover:text-slate-200"
      >
        <ArrowLeft className="h-4 w-4" /> Back to explorer
      </Link>

      <PageHeader
        title={name}
        description={
          current
            ? `${current.ias_batch ? `Batch ${current.ias_batch}` : ''}${
                current.ias_batch && current.cadre ? ' · ' : ''
              }${current.cadre || ''}`
            : 'Officer transfer profile'
        }
      />

      {isLoading ? (
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-40 lg:col-span-1" />
          <Skeleton className="h-40 lg:col-span-2" />
        </div>
      ) : sorted.length === 0 ? (
        <GlassCard>
          <EmptyState
            title="No records for this officer"
            message="We haven't discovered any transfers under this name yet."
            icon={<UserRound className="h-6 w-6" />}
          />
        </GlassCard>
      ) : (
        <>
          {/* Current posting + meta */}
          <div className="grid gap-4 lg:grid-cols-3">
            <GlassCard className="lg:col-span-1">
              <h3 className="text-sm font-semibold text-white">Current posting</h3>
              <div className="mt-4 space-y-3 text-sm">
                <div className="flex items-start gap-2.5">
                  <Building2 className="mt-0.5 h-4 w-4 text-brand-violet" />
                  <div>
                    <p className="text-slate-200">
                      {current.new_posting || current.current_designation || '—'}
                    </p>
                    <p className="text-xs text-slate-400">Designation / posting</p>
                  </div>
                </div>
                <div className="flex items-start gap-2.5">
                  <MapPin className="mt-0.5 h-4 w-4 text-brand-cyan" />
                  <div>
                    <p className="text-slate-200">
                      {current.new_district || '—'}
                      {current.state ? `, ${current.state}` : ''}
                    </p>
                    <p className="text-xs text-slate-400">Location</p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <StatusBadge status={current.status} />
                </div>
                <p className="pt-1 text-xs text-slate-400">
                  Effective {fmtDate(current.effective_date || current.transfer_date)}
                </p>
              </div>
            </GlassCard>

            <GlassCard className="lg:col-span-2">
              <h3 className="text-sm font-semibold text-white">
                Postings timeline
              </h3>
              <ol className="mt-5 space-y-5">
                {sorted.map((t: Transfer, i) => (
                  <motion.li
                    key={t.id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.04 }}
                    className="relative pl-6"
                  >
                    <span className="absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full bg-accent-gradient ring-4 ring-brand-violet/15" />
                    {i < sorted.length - 1 && (
                      <span className="absolute left-[4.5px] top-4 h-[calc(100%+0.75rem)] w-px bg-white/10" />
                    )}
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium text-white">
                        {t.previous_posting || t.previous_district || 'Unknown'}{' '}
                        <span className="text-slate-500">→</span>{' '}
                        {t.new_posting || t.new_district || 'Unknown'}
                      </p>
                    </div>
                    <p className="mt-0.5 text-xs text-slate-400">
                      {fmtDate(t.transfer_date)}
                      {t.state ? ` · ${t.state}` : ''}
                      {t.reason ? ` · ${t.reason}` : ''}
                    </p>
                    {(t.source_name || t.notification_number) && (
                      <p className="mt-1 text-xs text-slate-500">
                        {t.notification_number && (
                          <span>Order {t.notification_number} </span>
                        )}
                        {t.source_name && <span>· via {t.source_name}</span>}
                      </p>
                    )}
                  </motion.li>
                ))}
              </ol>
            </GlassCard>
          </div>

          {/* Sources & orders */}
          <div className="grid gap-4 lg:grid-cols-2">
            <GlassCard>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
                <Newspaper className="h-4 w-4 text-brand-cyan" /> Source articles
              </h3>
              {sources.length === 0 ? (
                <p className="mt-3 text-sm text-slate-400">No linked sources.</p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {sources.map((s) => (
                    <li key={s.url}>
                      <a
                        href={s.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="group flex items-center justify-between gap-2 rounded-lg border border-white/5 bg-white/[0.03] px-3 py-2 text-sm transition hover:bg-white/[0.06]"
                      >
                        <span className="truncate text-slate-200 group-hover:text-brand-cyan">
                          {s.name}
                        </span>
                        <ExternalLink className="h-3.5 w-3.5 shrink-0 text-slate-500 group-hover:text-brand-cyan" />
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </GlassCard>

            <GlassCard>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
                <FileText className="h-4 w-4 text-brand-violet" /> Government orders
              </h3>
              {govOrders.length === 0 ? (
                <p className="mt-3 text-sm text-slate-400">No linked orders.</p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {govOrders.map((o) => (
                    <li key={o.url}>
                      <a
                        href={o.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="group flex items-center justify-between gap-2 rounded-lg border border-white/5 bg-white/[0.03] px-3 py-2 text-sm transition hover:bg-white/[0.06]"
                      >
                        <span className="truncate text-slate-200 group-hover:text-brand-violet">
                          {o.label}
                        </span>
                        <ExternalLink className="h-3.5 w-3.5 shrink-0 text-slate-500 group-hover:text-brand-violet" />
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </GlassCard>
          </div>
        </>
      )}
    </div>
  );
}
