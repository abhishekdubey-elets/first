import clsx, { ClassValue } from 'clsx';

export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}

export const CHART_COLORS = ['#6366f1', '#8b5cf6', '#22d3ee', '#a78bfa', '#38bdf8', '#818cf8'];
