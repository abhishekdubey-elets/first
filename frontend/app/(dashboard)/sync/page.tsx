'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  RefreshCw,
  Sheet,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
} from 'lucide-react';
import { getSyncStatus, getSyncLogs, retrySync } from '@/lib/api';
import type { SyncLog, SyncStatus } from '@/lib/types';
import { PageHeader } from '@/components/PageHeader';
import { GlassCard } from '@/components/GlassCard';
import { StatCard } from '@/components/StatCard';
import { DataTable, Column } from '@/components/DataTable';
import { StatusBadge } from '@/components/StatusBadge';
import { EmptyState } from '@/components/EmptyState';
import { CardSkeleton, TableSkeleton } from '@/components/Skeleton';
import { fmtDateTime, fmtRelative, fmtNumber } from '@/lib/format';

export default function SyncPage() {
  const queryClient = useQueryClient();

  const statusQ = useQuery<SyncStatus>({
    queryKey: ['sync-status'],
    queryFn: getSyncStatus,
  });
  const logsQ = useQuery<SyncLog[]>({
    queryKey: ['sync-logs'],
    queryFn: getSyncLogs,
  });

  const retry = useMutation({
    mutationFn: retrySync,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sync-status'] });
      queryClient.invalidateQueries({ queryKey: ['sync-logs'] });
    },
  });

  const s = statusQ.data;
  const connected = s?.sheet?.connected;

  const columns: Column<SyncLog>[] = [
    {
      key: 'status',
      header: 'Status',
      render: (r) => <StatusBadge status={r.status} />,
    },
    {
      key: 'written',
      header: 'Rows written',
      render: (r) => (
        <span className="text-emerald-300">{fmtNumber(r.rows_written)}</span>
      ),
    },
    {
      key: 'failed',
      header: 'Rows failed',
      render: (r) => (
        <span className={r.rows_failed > 0 ? 'text-rose-300' : 'text-slate-400'}>
          {fmtNumber(r.rows_failed)}
        </span>
      ),
    },
    {
      key: 'message',
      header: 'Message',
      render: (r) => (
        <span className="text-slate-300">{r.message || '—'}</span>
      ),
    },
    {
      key: 'time',
      header: 'When',
      render: (r) => (
        <span className="text-slate-400" title={fmtDateTime(r.created_at)}>
          {fmtRelative(r.created_at)}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Google Sheets Sync"
        description="Export status and history for the connected spreadsheet."
        action={
          <button
            onClick={() => retry.mutate()}
            disabled={retry.isPending}
            className="btn-gradient"
          >
            {retry.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Retry failed
          </button>
        }
      />

      {retry.isSuccess && (
        <div className="flex items-center gap-2 rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-4 py-2.5 text-sm text-emerald-300">
          <CheckCircle2 className="h-4 w-4" />
          Requeued {fmtNumber(retry.data?.requeued ?? 0)} failed uploads.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {statusQ.isLoading || !s ? (
          Array.from({ length: 4 }).map((_, i) => <CardSkeleton key={i} />)
        ) : (
          <>
            <GlassCard>
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                Connection
              </p>
              <div className="mt-3 flex items-center gap-2">
                {connected ? (
                  <>
                    <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                    <span className="text-lg font-semibold text-white">
                      Connected
                    </span>
                  </>
                ) : (
                  <>
                    <XCircle className="h-5 w-5 text-rose-400" />
                    <span className="text-lg font-semibold text-white">
                      Disconnected
                    </span>
                  </>
                )}
              </div>
              {s.sheet?.error && (
                <p className="mt-2 flex items-start gap-1.5 text-xs text-rose-300">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  {s.sheet.error}
                </p>
              )}
            </GlassCard>

            <StatCard
              label="Total rows in sheet"
              value={fmtNumber(s.sheet?.total_rows)}
              icon={Sheet}
              accent="cyan"
              delay={0.05}
            />
            <StatCard
              label="Exported rows"
              value={fmtNumber(s.exported_rows)}
              icon={CheckCircle2}
              accent="indigo"
              delay={0.1}
            />
            <StatCard
              label="Failed uploads"
              value={fmtNumber(s.failed_uploads)}
              icon={XCircle}
              accent="violet"
              delay={0.15}
            />
          </>
        )}
      </div>

      {s && (
        <GlassCard>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <span className="text-slate-400">
              Last sync:{' '}
              <span className="text-slate-200">
                {s.last_sync ? fmtDateTime(s.last_sync) : 'Never'}
              </span>
            </span>
            <span className="text-slate-400">
              Last status:{' '}
              {s.last_status ? (
                <StatusBadge status={s.last_status} />
              ) : (
                <span className="text-slate-200">—</span>
              )}
            </span>
          </div>
        </GlassCard>
      )}

      <GlassCard className="p-0">
        <div className="px-5 py-4">
          <h3 className="text-sm font-semibold text-white">Sync logs</h3>
        </div>
        {logsQ.isLoading ? (
          <div className="px-5 pb-5">
            <TableSkeleton rows={6} />
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={logsQ.data ?? []}
            rowKey={(r) => r.id}
            empty={<EmptyState title="No sync runs yet" message="Exports will appear here once they run." />}
          />
        )}
      </GlassCard>
    </div>
  );
}
