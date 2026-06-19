'use client';

import { ReactNode } from 'react';
import { GlassCard } from '@/components/GlassCard';

export function ChartCard({
  title,
  subtitle,
  children,
  action,
  delay = 0,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  action?: ReactNode;
  delay?: number;
}) {
  return (
    <GlassCard delay={delay}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          {subtitle && (
            <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>
          )}
        </div>
        {action}
      </div>
      {children}
    </GlassCard>
  );
}
