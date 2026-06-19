import { format, formatDistanceToNow, parseISO, isValid } from 'date-fns';

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
