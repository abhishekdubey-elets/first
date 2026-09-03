'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Menu,
  Search,
  RefreshCw,
  LogOut,
  Loader2,
  CheckCircle2,
} from 'lucide-react';
import { runAgents, getAgentStatus, clearToken } from '@/lib/api';
import { fmtRelative } from '@/lib/format';
import { useAuth } from '@/lib/useAuth';

// Keys to refresh once a crawl cycle has had time to land results.
const CYCLE_KEYS = [['agent-status'], ['transfers'], ['stats'], ['news']];
const REPOLL_DELAYS_MS = [5000, 15000, 30000, 60000, 120000];

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: user } = useAuth();
  const [search, setSearch] = useState('');
  const [justRan, setJustRan] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const errorTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data: agentStatus } = useQuery({
    queryKey: ['agent-status'],
    queryFn: getAgentStatus,
    // Poll faster while a cycle is in progress so the label flips promptly.
    refetchInterval: (query) => (query.state.data?.running ? 15_000 : 60_000),
  });

  const isRunning = Boolean(agentStatus?.running);
  const isAdmin = user?.role === 'admin';

  useEffect(
    () => () => {
      if (errorTimer.current) clearTimeout(errorTimer.current);
    },
    [],
  );

  const showError = (msg: string) => {
    setRunError(msg);
    if (errorTimer.current) clearTimeout(errorTimer.current);
    errorTimer.current = setTimeout(() => setRunError(null), 4000);
  };

  const runMutation = useMutation({
    mutationFn: runAgents,
    onSuccess: (res) => {
      setRunError(null);
      setJustRan(true);
      setTimeout(() => setJustRan(false), 2500);
      if (res?.already_running) showError('A crawl is already in progress.');
      CYCLE_KEYS.forEach((queryKey) =>
        queryClient.invalidateQueries({ queryKey }),
      );
      // The cycle runs in the background; re-poll a few times so the status
      // label, feed, stats and tables update once it completes.
      REPOLL_DELAYS_MS.forEach((ms) =>
        setTimeout(() => {
          CYCLE_KEYS.forEach((queryKey) =>
            queryClient.invalidateQueries({ queryKey }),
          );
        }, ms),
      );
    },
    onError: (err: unknown) => {
      const e = err as {
        response?: { status?: number; data?: { detail?: unknown } };
      };
      const d = e?.response?.data?.detail;
      if (typeof d === 'string' && d.trim()) showError(d);
      else if (e?.response?.status === 403) showError('Admin role required.');
      else if (!e?.response) showError('Cannot reach the server.');
      else showError('Could not start the crawl.');
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

  const busy = runMutation.isPending || isRunning;

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
          {(agentStatus?.last_run || isRunning) && (
            <span
              className="hidden text-right text-[11px] leading-tight text-slate-400 md:block"
              title={
                agentStatus?.summary
                  ? `${agentStatus.summary.new ?? 0} new · ${agentStatus.summary.transfers ?? 0} transfers · ${agentStatus.summary.articles ?? 0} articles`
                  : undefined
              }
            >
              {isRunning ? (
                <>
                  <span className="block text-slate-500">Crawling</span>
                  <span className="text-brand-cyan">
                    started {fmtRelative(agentStatus?.started_at)}
                  </span>
                </>
              ) : (
                <>
                  <span className="block text-slate-500">Last run</span>
                  <span className="text-slate-300">
                    {fmtRelative(agentStatus?.last_run)}
                  </span>
                </>
              )}
            </span>
          )}

          {isAdmin && (
            <div className="flex items-center gap-2">
              {runError && (
                <span
                  className="hidden max-w-[220px] truncate text-xs text-rose-300 sm:inline"
                  title={runError}
                >
                  {runError}
                </span>
              )}
              <button
                onClick={() => runMutation.mutate()}
                disabled={busy}
                className="btn-gradient px-3 py-2 sm:px-4"
                title={
                  isRunning
                    ? 'A crawl cycle is currently running'
                    : 'Crawl the latest IAS transfer news now'
                }
              >
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : justRan ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                <span className="hidden sm:inline">
                  {busy ? 'Crawling…' : justRan ? 'Started' : 'Crawl now'}
                </span>
              </button>
            </div>
          )}

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
      {runError && (
        <p className="px-4 pb-2 text-xs text-rose-300 sm:hidden">{runError}</p>
      )}
    </header>
  );
}
