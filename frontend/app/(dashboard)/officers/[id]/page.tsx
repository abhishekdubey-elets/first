'use client';

import { useMemo } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import type { AxiosError } from 'axios';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowLeftRight,
  BookOpen,
  Building2,
  CalendarClock,
  ExternalLink,
  Eye,
  EyeOff,
  FileText,
  ImageIcon,
  MapPin,
  Newspaper,
  Sparkles,
  Users,
  UserRound,
} from 'lucide-react';
import { getOfficerProfile, queueOfficerResearch, setOfficerImageHidden } from '@/lib/api';
import type {
  OfficerLink,
  OfficerMovement,
  OfficerProfile,
  OfficerResearch,
  PressMention,
} from '@/lib/types';
import { useAuth } from '@/lib/useAuth';
import { GlassCard } from '@/components/GlassCard';
import { StatCard } from '@/components/StatCard';
import { StatusBadge } from '@/components/StatusBadge';
import { EmptyState } from '@/components/EmptyState';
import { Skeleton } from '@/components/Skeleton';
import { OfficerAvatar } from '@/components/OfficerAvatar';
import { fmtDate, fmtRelative, fmtTenure } from '@/lib/format';
import { cn } from '@/lib/utils';

const movementStyles: Record<string, string> = {
  Transfer: 'bg-violet-500/15 text-violet-300 border-violet-500/25',
  Appointment: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/25',
  Promotion: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
  'Re-appointment': 'bg-sky-500/15 text-sky-300 border-sky-500/25',
  Retirement: 'bg-slate-500/15 text-slate-300 border-slate-500/25',
  Resignation: 'bg-rose-500/15 text-rose-300 border-rose-500/25',
};

function MovementBadge({ movement }: { movement: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium',
        movementStyles[movement] ?? 'bg-slate-500/15 text-slate-300 border-slate-500/25',
      )}
    >
      {movement}
    </span>
  );
}

// A readable placeholder title while loading: "anita-sharma--uttar-pradesh" -> "Anita Sharma".
function nameFromRef(ref: string): string {
  return ref
    .replace(/--.*$/, '')
    .replace(/-/g, ' ')
    .replace(/\b\p{L}/gu, (c) => c.toUpperCase());
}

function where(m: OfficerMovement): string {
  return [m.to_district, m.state].filter(Boolean).join(', ') || '—';
}

// ---------- The whole journey: postings and press, grouped by year ----------
type Moment =
  | { kind: 'posting'; date: string; key: string; m: OfficerMovement }
  | { kind: 'press'; date: string; key: string; p: PressMention };

const KIND_ORDER = { posting: 0, press: 1 } as const;

function journey(p: OfficerProfile): { year: string; moments: Moment[] }[] {
  const moments: Moment[] = [
    ...p.timeline.map((m) => ({
      kind: 'posting' as const, date: m.date, key: `t${m.transfer_id}`, m,
    })),
    ...(p.research?.press ?? [])
      .filter((x) => x.published)
      .map((x) => ({ kind: 'press' as const, date: x.published as string, key: `p${x.url}`, p: x })),
  ];
  moments.sort((a, b) =>
    a.date === b.date ? KIND_ORDER[a.kind] - KIND_ORDER[b.kind] : a.date < b.date ? 1 : -1,
  );
  const years = new Map<string, Moment[]>();
  for (const mo of moments) {
    const y = mo.date.slice(0, 4);
    years.set(y, [...(years.get(y) ?? []), mo]);
  }
  return Array.from(years, ([year, list]) => ({ year, moments: list }));
}

const dot = { posting: 'bg-brand-violet', press: 'bg-amber-400' } as const;

function PostingMoment({ m }: { m: OfficerMovement }) {
  return (
    <>
      <p className="text-sm font-medium text-white">
        {m.role}
        {(m.from_posting || m.from_district) && (
          <span className="font-normal text-slate-400">
            {' '}— from {m.from_posting || m.from_district}
          </span>
        )}
        {m.state && <span className="font-normal text-slate-400"> · {m.state}</span>}
      </p>
      <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
        <MovementBadge movement={m.movement} />
        {m.tenure_days !== null && (
          <span>
            {m.is_current ? 'in post' : 'held'} {fmtTenure(m.tenure_days)}
          </span>
        )}
        {m.order_number && <span>· Order {m.order_number}</span>}
        {m.source_url ? (
          <a
            href={m.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 hover:text-brand-cyan"
          >
            · via {m.source_name || 'source'}
            {m.source_count > 1 && ` +${m.source_count - 1}`}
            <ExternalLink className="h-3 w-3" />
          </a>
        ) : (
          m.source_name && <span>· via {m.source_name}</span>
        )}
        <StatusBadge status={m.status} />
      </p>
    </>
  );
}

function PressMoment({ p }: { p: PressMention }) {
  return (
    <>
      <a
        href={p.url}
        target="_blank"
        rel="noopener noreferrer"
        className="group inline-flex items-start gap-1.5 text-sm font-medium text-white hover:text-amber-300"
      >
        {p.title}
        <ExternalLink className="mt-1 h-3 w-3 shrink-0 text-slate-500 group-hover:text-amber-300" />
      </a>
      {p.excerpt && (
        <p className="mt-1 line-clamp-2 border-l-2 border-amber-400/30 pl-2 text-xs italic text-slate-400">
          {p.excerpt}
        </p>
      )}
    </>
  );
}

function Journey({ p }: { p: OfficerProfile }) {
  const groups = useMemo(() => journey(p), [p]);
  const hasPress = (p.research?.press.length ?? 0) > 0;
  return (
    <GlassCard className="lg:col-span-2">
      <h3 className="text-sm font-semibold text-white">The whole journey</h3>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-400">
        <span className="inline-flex items-center gap-1.5">
          <span className={cn('h-2 w-2 rounded-full', dot.posting)} /> Posting
        </span>
        <span className={cn('inline-flex items-center gap-1.5', !hasPress && 'opacity-50')}>
          <span className={cn('h-2 w-2 rounded-full', dot.press)} /> Press
        </span>
      </div>
      <div className="mt-5 space-y-6">
        {groups.map(({ year, moments }) => (
          <section key={year}>
            <div className="flex items-center gap-3">
              <span className="rounded-full bg-white/10 px-3 py-1 text-sm font-semibold text-white">
                {year}
              </span>
              <span className="text-xs text-slate-400">
                {moments.length} {moments.length === 1 ? 'moment' : 'moments'}
              </span>
            </div>
            <ol className="mt-4 space-y-4 border-l border-white/10 pl-5">
              {moments.map((mo, i) => (
                <motion.li
                  key={mo.key}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.03 }}
                  className="relative"
                >
                  <span
                    className={cn(
                      'absolute -left-[25px] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-slate-950',
                      dot[mo.kind],
                    )}
                  />
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="rounded-md bg-white/5 px-2 py-0.5 font-medium text-slate-300">
                      {mo.date}
                    </span>
                    <span
                      className={cn(
                        'font-semibold uppercase tracking-wide',
                        mo.kind === 'posting' ? 'text-brand-violet' : 'text-amber-300',
                      )}
                    >
                      {mo.kind === 'posting' ? 'Posting' : 'Press'}
                    </span>
                    {mo.kind === 'posting' && mo.m.is_current && (
                      <span className="uppercase tracking-wide text-brand-cyan">Current</span>
                    )}
                    {mo.kind === 'press' && mo.p.source && (
                      <span className="text-slate-500">{mo.p.source}</span>
                    )}
                  </div>
                  <div className="mt-1.5">
                    {mo.kind === 'posting' ? <PostingMoment m={mo.m} /> : <PressMoment p={mo.p} />}
                  </div>
                </motion.li>
              ))}
            </ol>
          </section>
        ))}
      </div>
    </GlassCard>
  );
}

// ---------- Research panel (status, photos, admin actions) ----------
function researchStatus(r: OfficerResearch | null): string {
  if (!r) return 'Not researched yet. The research agent works through officers during the daily crawl.';
  if (r.status === 'queued') return `Queued ${fmtRelative(r.requested_at)}. Runs with the next crawl.`;
  if (r.status === 'failed') {
    return `Last attempt ${fmtRelative(r.researched_at)} did not finish${r.error ? ` (${r.error})` : ''}. It is retried after a day.`;
  }
  const photos = r.images.filter((i) => !i.hidden).length;
  return `Researched ${fmtRelative(r.researched_at)}: ${r.press.length} press ${r.press.length === 1 ? 'mention' : 'mentions'}, ${photos} ${photos === 1 ? 'photo' : 'photos'}${r.wikipedia ? ', Wikipedia article' : ''}.`;
}

function ResearchPanel({
  p,
  isAdmin,
  profileRef,
}: {
  p: OfficerProfile;
  isAdmin: boolean;
  profileRef: string;
}) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ['officer-profile', profileRef] });
  const queue = useMutation({ mutationFn: () => queueOfficerResearch(p.id), onSuccess: refresh });
  const toggle = useMutation({
    mutationFn: (v: { url: string; hidden: boolean }) => setOfficerImageHidden(p.id, v.url, v.hidden),
    onSuccess: refresh,
  });
  const r = p.research;
  const images = r?.images ?? [];

  return (
    <GlassCard>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
            <Sparkles className="h-4 w-4 text-amber-300" /> Press & photos
          </h3>
          <p className="mt-1 max-w-2xl text-xs text-slate-400">{researchStatus(r)}</p>
        </div>
        {isAdmin && (
          <button
            type="button"
            onClick={() => queue.mutate()}
            disabled={queue.isPending || r?.status === 'queued'}
            className="btn-ghost px-3 py-1.5 text-xs"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {r?.status === 'queued' ? 'Queued' : queue.isPending ? 'Queuing…' : 'Research this officer'}
          </button>
        )}
      </div>

      {images.length > 0 ? (
        <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {images.map((img) => (
            <li
              key={img.image_url}
              className={cn('rounded-xl border border-white/10 bg-white/[0.03] p-2', img.hidden && 'opacity-40')}
            >
              <div className="aspect-[3/4] overflow-hidden rounded-lg bg-white/5">
                {/* eslint-disable-next-line @next/next/no-img-element -- remote hosts vary per officer */}
                <img
                  src={img.image_url}
                  alt={img.caption ?? p.name}
                  referrerPolicy="no-referrer"
                  className="h-full w-full object-cover object-top"
                />
              </div>
              <p className="mt-1.5 line-clamp-2 text-[11px] text-slate-400" title={img.caption ?? ''}>
                {img.caption}
              </p>
              <div className="mt-1 flex items-center justify-between gap-1 text-[11px]">
                {img.page_url ? (
                  <a
                    href={img.page_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="truncate text-slate-500 hover:text-brand-cyan"
                  >
                    {img.source || 'source'}
                  </a>
                ) : (
                  <span className="truncate text-slate-500">{img.source}</span>
                )}
                {img.origin === 'press' && (
                  <span className="shrink-0 text-amber-300/80" title="Matched by its caption, not checked by a person">
                    unverified
                  </span>
                )}
              </div>
              {isAdmin && (
                <button
                  type="button"
                  onClick={() => toggle.mutate({ url: img.image_url, hidden: !img.hidden })}
                  className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-white"
                >
                  {img.hidden ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
                  {img.hidden ? 'Show' : 'Hide photo'}
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        r?.status === 'done' && (
          <p className="mt-3 flex items-center gap-2 text-xs text-slate-500">
            <ImageIcon className="h-3.5 w-3.5" /> No photo whose caption names this officer was found.
          </p>
        )
      )}
    </GlassCard>
  );
}

// ---------- Lists ----------
const relationLabel: Record<string, string> = {
  same_order: 'Same order',
  same_article: 'Same report',
  batchmate: 'Batchmate',
  same_name: 'Same name',
};

function OfficerList({ items, empty }: { items: OfficerLink[]; empty: string }) {
  if (items.length === 0) {
    return <p className="mt-3 text-sm text-slate-400">{empty}</p>;
  }
  return (
    <ul className="mt-3 space-y-2">
      {items.map((o) => (
        <li key={`${o.id}-${o.relation}`}>
          <Link
            href={`/officers/${encodeURIComponent(o.id)}`}
            className="group flex items-center justify-between gap-3 rounded-lg border border-white/5 bg-white/[0.03] px-3 py-2 text-sm transition hover:bg-white/[0.06]"
          >
            <span className="min-w-0">
              <span className="block truncate text-slate-200 group-hover:text-brand-cyan">
                {o.name}
                {o.batch && <span className="text-slate-500"> · {o.batch}</span>}
              </span>
              <span className="block truncate text-xs text-slate-400">
                {o.current_role}
                {o.state ? ` · ${o.state}` : ''}
              </span>
            </span>
            <span className="shrink-0 text-[11px] uppercase tracking-wide text-slate-500">
              {relationLabel[o.relation] ?? o.relation}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function LinkList({
  items,
  empty,
  accent,
}: {
  items: { key: string; label: string; sub?: string; url: string | null }[];
  empty: string;
  accent: 'cyan' | 'violet';
}) {
  if (items.length === 0) {
    return <p className="mt-3 text-sm text-slate-400">{empty}</p>;
  }
  const hover = accent === 'cyan' ? 'group-hover:text-brand-cyan' : 'group-hover:text-brand-violet';
  const row =
    'group flex items-center justify-between gap-2 rounded-lg border border-white/5 bg-white/[0.03] px-3 py-2 text-sm';
  return (
    <ul className="mt-3 space-y-2">
      {items.map((it) => {
        const body = (
          <>
            <span className="min-w-0">
              <span className={cn('block truncate text-slate-200', it.url && hover)}>{it.label}</span>
              {it.sub && <span className="block text-xs text-slate-500">{it.sub}</span>}
            </span>
            {it.url && <ExternalLink className={cn('h-3.5 w-3.5 shrink-0 text-slate-500', hover)} />}
          </>
        );
        return (
          <li key={it.key}>
            {it.url ? (
              <a
                href={it.url}
                target="_blank"
                rel="noopener noreferrer"
                className={cn(row, 'transition hover:bg-white/[0.06]')}
              >
                {body}
              </a>
            ) : (
              <div className={row}>{body}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

// ---------- Header ----------
function ProfileHeader({ p }: { p: OfficerProfile }) {
  const photo = p.research?.photo;
  const wiki = p.research?.wikipedia;
  return (
    <GlassCard>
      <div className="flex flex-col gap-5 sm:flex-row">
        <div className="flex flex-col items-start gap-1.5">
          <OfficerAvatar name={p.name} photoUrl={p.photo_url} size="lg" />
          {photo && (
            <p className="max-w-[6rem] text-[10px] leading-tight text-slate-500">
              Photo:{' '}
              {photo.page_url ? (
                <a href={photo.page_url} target="_blank" rel="noopener noreferrer" className="hover:text-brand-cyan">
                  {photo.source || 'source'}
                </a>
              ) : (
                photo.source
              )}
              {photo.origin === 'press' && <span className="text-amber-300/80"> · unverified</span>}
            </p>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight text-white">{p.name}</h1>
            <span className="rounded-full bg-brand-indigo/20 px-2.5 py-0.5 text-xs font-semibold text-brand-cyan">
              IAS officer
            </span>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-slate-300">{p.bio}</p>
          {p.aliases.length > 0 && (
            <p className="mt-1 text-xs text-slate-500">Also reported as {p.aliases.join(', ')}</p>
          )}
          {wiki && (
            <div className="mt-3 rounded-lg border border-white/5 bg-white/[0.03] p-3 text-xs text-slate-400">
              <p className="line-clamp-3">{wiki.extract}</p>
              <a
                href={wiki.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-flex items-center gap-1 text-slate-500 hover:text-brand-cyan"
              >
                <BookOpen className="h-3 w-3" /> From Wikipedia (CC BY-SA)
              </a>
            </div>
          )}
        </div>
      </div>
    </GlassCard>
  );
}

// ---------- Page ----------
export default function OfficerProfilePage() {
  const params = useParams<{ id: string }>();
  const ref = decodeURIComponent(params.id);
  const { data: me } = useAuth();
  const isAdmin = me?.role === 'admin';

  const { data: p, isLoading, error } = useQuery<OfficerProfile, AxiosError>({
    queryKey: ['officer-profile', ref],
    queryFn: () => getOfficerProfile(ref),
    retry: (count, err) => err.response?.status !== 404 && count < 2,
  });

  const notFound = error?.response?.status === 404;
  const current = p ? p.timeline.filter((m) => m.is_current) : [];

  return (
    <div className="space-y-6">
      <Link
        href="/officers"
        className="inline-flex items-center gap-1.5 text-sm text-slate-400 transition hover:text-slate-200"
      >
        <ArrowLeft className="h-4 w-4" /> All officers
      </Link>

      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-36" />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28" />
            ))}
          </div>
          <p className="text-sm text-slate-500">Loading {nameFromRef(ref)}…</p>
        </div>
      ) : !p ? (
        <GlassCard>
          <EmptyState
            title={notFound ? 'No records for this officer' : 'Could not load this profile'}
            message={
              notFound
                ? "We haven't discovered any transfers under this name yet."
                : 'The API did not answer. Try again in a moment.'
            }
            icon={<UserRound className="h-6 w-6" />}
          />
        </GlassCard>
      ) : (
        <>
          <ProfileHeader p={p} />

          {(p.alternates.length > 0 || p.identity_notes.length > 0) && (
            <GlassCard className="border border-amber-500/20">
              <div className="flex items-start gap-3 text-sm">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
                <div className="space-y-1.5 text-slate-300">
                  {p.identity_notes.map((n) => (
                    <p key={n}>{n}</p>
                  ))}
                  {p.alternates.length > 0 && (
                    <p>
                      Other officers with this name:{' '}
                      {p.alternates.map((a, i) => (
                        <span key={a.id}>
                          {i > 0 && ', '}
                          <Link
                            href={`/officers/${encodeURIComponent(a.id)}`}
                            className="text-brand-cyan hover:underline"
                          >
                            {a.name}
                            {a.state ? ` (${a.state})` : ''}
                          </Link>
                        </span>
                      ))}
                    </p>
                  )}
                </div>
              </div>
            </GlassCard>
          )}

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Movements tracked"
              value={p.stats.movements}
              sub={`${fmtDate(p.stats.first_seen)} – ${fmtDate(p.stats.last_seen)}`}
              icon={ArrowLeftRight}
              accent="violet"
            />
            <StatCard
              label="Average tenure"
              value={fmtTenure(p.stats.average_tenure_days)}
              sub={p.stats.average_tenure_days === null ? 'Needs two or more moves' : 'Between moves'}
              icon={CalendarClock}
              accent="indigo"
              delay={0.05}
            />
            <StatCard
              label="Districts"
              value={p.stats.districts.length}
              sub={p.stats.districts.slice(-3).join(', ') || 'None recorded'}
              icon={MapPin}
              accent="cyan"
              delay={0.1}
            />
            <StatCard
              label="Press mentions"
              value={p.research?.press.length ?? 0}
              sub={`${p.stats.sources} transfer sources · ${p.stats.verified_movements} of ${p.stats.movements} moves verified`}
              icon={Newspaper}
              accent="violet"
              delay={0.15}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <GlassCard className="lg:col-span-1">
              <h3 className="text-sm font-semibold text-white">
                Current posting{current.length > 1 ? 's' : ''}
              </h3>
              <div className="mt-4 space-y-4 text-sm">
                {current.map((m) => (
                  <div key={m.transfer_id} className="space-y-3">
                    <div className="flex items-start gap-2.5">
                      <Building2 className="mt-0.5 h-4 w-4 text-brand-violet" />
                      <div>
                        <p className="text-slate-200">{m.role}</p>
                        <p className="text-xs text-slate-400">{m.role_group}</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-2.5">
                      <MapPin className="mt-0.5 h-4 w-4 text-brand-cyan" />
                      <div>
                        <p className="text-slate-200">{where(m)}</p>
                        <p className="text-xs text-slate-400">Location</p>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <MovementBadge movement={m.movement} />
                      <StatusBadge status={m.status} />
                    </div>
                    <p className="text-xs text-slate-400">
                      Since {fmtDate(m.date)} · in post {fmtTenure(m.tenure_days)}
                    </p>
                  </div>
                ))}
              </div>
              <dl className="mt-5 grid grid-cols-2 gap-3 border-t border-white/10 pt-4 text-xs">
                <div>
                  <dt className="text-slate-500">Batch</dt>
                  <dd className="mt-0.5 text-slate-200">{p.batch || '—'}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Cadre</dt>
                  <dd className="mt-0.5 text-slate-200">{p.cadre || '—'}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-slate-500">States served</dt>
                  <dd className="mt-0.5 text-slate-200">{p.stats.states.join(', ') || '—'}</dd>
                </div>
                {p.stats.role_groups.length > 0 && (
                  <div className="col-span-2">
                    <dt className="text-slate-500">Roles held</dt>
                    <dd className="mt-1 flex flex-wrap gap-1.5">
                      {p.stats.role_groups.map((g) => (
                        <span
                          key={g.role_group}
                          className="rounded-md bg-white/5 px-2 py-0.5 text-slate-300"
                        >
                          {g.role_group}
                          {g.count > 1 && <span className="text-slate-500"> ×{g.count}</span>}
                        </span>
                      ))}
                    </dd>
                  </div>
                )}
              </dl>
            </GlassCard>

            <Journey p={p} />
          </div>

          <ResearchPanel p={p} isAdmin={isAdmin} profileRef={ref} />

          <div className="grid gap-4 lg:grid-cols-2">
            <GlassCard>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
                <Users className="h-4 w-4 text-brand-cyan" /> Moved together
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                Officers in the same government order or the same news report.
              </p>
              <OfficerList items={p.co_transferred} empty="No other officers in the same order." />
            </GlassCard>
            <GlassCard>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
                <UserRound className="h-4 w-4 text-brand-violet" /> Batchmates
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                {p.batch && p.cadre
                  ? `${p.batch} batch, ${p.cadre} cadre.`
                  : 'Needs a known batch and cadre.'}
              </p>
              <OfficerList items={p.batchmates} empty="No batchmates tracked yet." />
            </GlassCard>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <GlassCard>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
                <Newspaper className="h-4 w-4 text-brand-cyan" /> Transfer sources
              </h3>
              <LinkList
                accent="cyan"
                empty="No linked sources."
                items={p.sources.map((s) => ({ key: s.url, label: s.name, url: s.url }))}
              />
            </GlassCard>
            <GlassCard>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
                <FileText className="h-4 w-4 text-brand-violet" /> Government orders
              </h3>
              <LinkList
                accent="violet"
                empty="No linked orders."
                items={p.orders.map((o) => ({
                  key: `${o.number ?? ''}|${o.url ?? ''}`,
                  label: o.number || 'Government order',
                  sub: fmtDate(o.date),
                  url: o.url,
                }))}
              />
            </GlassCard>
          </div>
        </>
      )}
    </div>
  );
}
