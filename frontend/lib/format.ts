import {
  format,
  formatDistanceToNow,
  parseISO,
  isValid,
  isToday,
  isYesterday,
} from 'date-fns';

export function safeDate(value?: string | null): Date | null {
  if (!value) return null;
  const d = typeof value === 'string' ? parseISO(value) : value;
  return isValid(d) ? d : null;
}

export function fmtDate(value?: string | null, pattern = 'dd MMM yyyy'): string {
  const d = safeDate(value);
  return d ? format(d, pattern) : '—';
}

export function fmtDateTime(value?: string | null): string {
  const d = safeDate(value);
  return d ? format(d, 'dd MMM yyyy, HH:mm') : '—';
}

export function fmtRelative(value?: string | null): string {
  const d = safeDate(value);
  return d ? formatDistanceToNow(d, { addSuffix: true }) : '—';
}

export function fmtPercent(value: number, digits = 0): string {
  if (Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

export function fmtNumber(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '0';
  return value.toLocaleString('en-IN');
}

/** True when `value` is a valid date within the last `hours` hours (or in the future). */
export function isWithinHours(value?: string | null, hours = 24): boolean {
  const d = safeDate(value);
  if (!d) return false;
  const diff = Date.now() - d.getTime();
  return diff <= hours * 60 * 60 * 1000;
}

/** "Today" / "Yesterday" / "dd MMM yyyy" — used for grouping feeds by day. */
export function dayLabel(value?: string | null): string {
  const d = safeDate(value);
  if (!d) return 'Unknown date';
  if (isToday(d)) return 'Today';
  if (isYesterday(d)) return 'Yesterday';
  return format(d, 'dd MMM yyyy');
}

/** Human-friendly interval, e.g. 3600 -> "1 hour", 5400 -> "1.5 hours", 900 -> "15 min". */
export function fmtInterval(seconds?: number | null): string {
  if (!seconds || seconds <= 0) return '—';
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  const hours = seconds / 3600;
  const rounded = Math.round(hours * 10) / 10;
  return `${rounded} ${rounded === 1 ? 'hour' : 'hours'}`;
}
