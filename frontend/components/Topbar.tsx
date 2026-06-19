'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Menu,
  Search,
  Sparkles,
  LogOut,
  Loader2,
  CheckCircle2,
} from 'lucide-react';
import { runAgents, clearToken } from '@/lib/api';
import { useAuth } from '@/lib/useAuth';

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: user } = useAuth();
  const [search, setSearch] = useState('');
  const [justRan, setJustRan] = useState(false);

  const runMutation = useMutation({
    mutationFn: runAgents,
    onSuccess: () => {
      setJustRan(true);
      setTimeout(() => setJustRan(false), 2500);
      queryClient.invalidateQueries({ queryKey: ['logs'] });
    },
  });

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const q = search.trim();
    if (q) router.push(`/transfers?q=${encodeURIComponent(q)}`);
  };

  const logout = () => {
    clearToken();
    queryClient.clear();
    router.replace('/login');
  };

  const initials = (user?.full_name || user?.email || 'U')
    .split(' ')
    .map((s) => s[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-slate-950/60 backdrop-blur-xl">
      <div className="flex items-center gap-3 px-4 py-3 sm:px-6">
        <button
          onClick={onMenu}
          className="rounded-lg p-2 text-slate-300 hover:bg-white/10 lg:hidden"
          aria-label="Open menu"
        >
          <Menu className="h-5 w-5" />
        </button>

        <form onSubmit={onSearch} className="relative hidden flex-1 max-w-md sm:block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search officers, districts, postings…"
            className="input-glass pl-9"
          />
        </form>

        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          <button
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
            className="btn-gradient px-3 py-2 sm:px-4"
          >
            {runMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : justRan ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            <span className="hidden sm:inline">
              {justRan ? 'Queued' : 'Run agents now'}
            </span>
          </button>

          <div className="flex items-center gap-2.5 rounded-xl border border-white/10 bg-white/5 px-2.5 py-1.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-gradient text-xs font-semibold text-white">
              {initials}
            </div>
            <div className="hidden leading-tight md:block">
              <p className="max-w-[140px] truncate text-sm font-medium text-white">
                {user?.full_name || user?.email || 'Account'}
              </p>
              <p className="text-[11px] capitalize text-slate-400">
                {user?.role || 'member'}
              </p>
            </div>
            <button
              onClick={logout}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-white/10 hover:text-rose-300"
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
