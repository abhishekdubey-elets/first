import { cn } from '@/lib/utils';

const styles: Record<string, string> = {
  // transfer statuses
  pending: 'bg-amber-500/15 text-amber-300 border-amber-500/25',
  verified: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
  conflicted: 'bg-rose-500/15 text-rose-300 border-rose-500/25',
  exported: 'bg-sky-500/15 text-sky-300 border-sky-500/25',
  export_failed: 'bg-rose-500/15 text-rose-300 border-rose-500/25',
  // article statuses
  discovered: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/25',
  extracted: 'bg-violet-500/15 text-violet-300 border-violet-500/25',
  parsed: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
  irrelevant: 'bg-slate-500/15 text-slate-300 border-slate-500/25',
  failed: 'bg-rose-500/15 text-rose-300 border-rose-500/25',
  // log levels
  INFO: 'bg-sky-500/15 text-sky-300 border-sky-500/25',
  WARNING: 'bg-amber-500/15 text-amber-300 border-amber-500/25',
  ERROR: 'bg-rose-500/15 text-rose-300 border-rose-500/25',
  SUCCESS: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
  // sync
  ok: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
  success: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
  error: 'bg-rose-500/15 text-rose-300 border-rose-500/25',
  connected: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
  disconnected: 'bg-rose-500/15 text-rose-300 border-rose-500/25',
};

export function StatusBadge({ status }: { status: string }) {
  const key = String(status ?? '').trim();
  const cls = styles[key] ?? 'bg-slate-500/15 text-slate-300 border-slate-500/25';
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize',
        cls
      )}
    >
      {key ? key.replace(/_/g, ' ') : 'unknown'}
    </span>
  );
}
