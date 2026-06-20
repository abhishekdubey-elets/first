'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  ArrowLeftRight,
  BarChart3,
  Newspaper,
  RefreshCw,
  Settings as SettingsIcon,
  Radar,
  X,
} from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

const nav = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/transfers', label: 'Transfer Explorer', icon: ArrowLeftRight },
  { href: '/analytics', label: 'Analytics', icon: BarChart3 },
  { href: '/news', label: 'News Feed', icon: Newspaper },
  { href: '/sync', label: 'Sheets Sync', icon: RefreshCw },
  { href: '/settings', label: 'Settings', icon: SettingsIcon },
];

export function Sidebar({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const pathname = usePathname();

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname.startsWith(href);

  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-white/10 bg-slate-950/70 backdrop-blur-xl transition-transform duration-300 lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="flex items-center justify-between px-5 py-5">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent-gradient shadow-glow">
              <Radar className="h-5 w-5 text-white" />
            </div>
            <div className="leading-tight">
              <p className="text-sm font-semibold text-white">IAS Transfer</p>
              <p className="text-[11px] text-slate-400">Intelligence</p>
            </div>
          </Link>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-white/10 lg:hidden"
            aria-label="Close sidebar"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 px-3 py-2">
          {nav.map((item) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onClose}
                className={cn(
                  'group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors',
                  active
                    ? 'text-white'
                    : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'
                )}
              >
                {active && (
                  <motion.span
                    layoutId="sidebar-active"
                    className="absolute inset-0 rounded-xl border border-white/10"
                    style={{
                      background:
                        'linear-gradient(135deg, rgba(99,102,241,0.25), rgba(139,92,246,0.18), rgba(34,211,238,0.15))',
                    }}
                    transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                  />
                )}
                <item.icon className="relative h-[18px] w-[18px] shrink-0" />
                <span className="relative">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="px-5 py-4">
          <div className="glass rounded-xl p-3 text-xs text-slate-400">
            <p className="font-medium text-slate-200">Agents online</p>
            <p className="mt-0.5">Discovery & verification active</p>
          </div>
        </div>
      </aside>
    </>
  );
}
