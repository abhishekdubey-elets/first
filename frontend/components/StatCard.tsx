'use client';

import { motion } from 'framer-motion';
import { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  sub?: string;
  delay?: number;
  accent?: 'indigo' | 'violet' | 'cyan';
}

const accentMap = {
  indigo: 'from-brand-indigo/30 to-brand-indigo/0 text-brand-indigo',
  violet: 'from-brand-violet/30 to-brand-violet/0 text-brand-violet',
  cyan: 'from-brand-cyan/30 to-brand-cyan/0 text-brand-cyan',
};

export function StatCard({
  label,
  value,
  icon: Icon,
  sub,
  delay = 0,
  accent = 'violet',
}: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: 'easeOut' }}
      whileHover={{ y: -3 }}
      className="glass glass-hover rounded-2xl p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
            {label}
          </p>
          <p className="mt-2 text-3xl font-semibold text-white">{value}</p>
          {sub && <p className="mt-1 text-xs text-slate-400">{sub}</p>}
        </div>
        <div
          className={cn(
            'flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br',
            accentMap[accent]
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </motion.div>
  );
}
