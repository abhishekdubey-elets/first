import { cn } from '@/lib/utils';
import { fmtPercent } from '@/lib/format';

export function ConfidenceBadge({ score }: { score: number }) {
  const value = Number.isFinite(score) ? score : 0;
  const tone =
    value >= 0.8
      ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25'
      : value >= 0.5
        ? 'bg-amber-500/15 text-amber-300 border-amber-500/25'
        : 'bg-rose-500/15 text-rose-300 border-rose-500/25';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium',
        tone
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {fmtPercent(value)}
    </span>
  );
}
