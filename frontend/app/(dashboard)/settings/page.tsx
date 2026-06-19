'use client';

import { useEffect, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Save,
  Upload,
  Loader2,
  CheckCircle2,
  Cpu,
  Sheet,
  Bell,
  KeyRound,
  Clock,
} from 'lucide-react';
import {
  getSettings,
  updateExportSettings,
  uploadCredentials,
  getModels,
} from '@/lib/api';
import type { Settings, ModelsResponse } from '@/lib/types';
import { PageHeader } from '@/components/PageHeader';
import { GlassCard } from '@/components/GlassCard';
import { Skeleton } from '@/components/Skeleton';
import { cn } from '@/lib/utils';

export default function SettingsPage() {
  const queryClient = useQueryClient();

  const settingsQ = useQuery<Settings>({
    queryKey: ['settings'],
    queryFn: getSettings,
  });
  const modelsQ = useQuery<ModelsResponse>({
    queryKey: ['models'],
    queryFn: getModels,
  });

  const [spreadsheetId, setSpreadsheetId] = useState('');
  const [worksheet, setWorksheet] = useState('');
  const [autoExport, setAutoExport] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (settingsQ.data) {
      setSpreadsheetId(settingsQ.data.spreadsheet_id ?? '');
      setWorksheet(settingsQ.data.worksheet_name ?? '');
      setAutoExport(Boolean(settingsQ.data.auto_export));
    }
  }, [settingsQ.data]);

  const saveExport = useMutation({
    mutationFn: () =>
      updateExportSettings({
        spreadsheet_id: spreadsheetId,
        worksheet_name: worksheet,
        auto_export: autoExport,
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['settings'] }),
  });

  const upload = useMutation({
    mutationFn: (file: File) => uploadCredentials(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      if (fileRef.current) fileRef.current.value = '';
    },
  });

  const s = settingsQ.data;
  const m = modelsQ.data;

  const discoveryMinutes = s
    ? Math.round((s.discovery_interval_seconds ?? 0) / 60)
    : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Configure exports, models and integrations for the intelligence pipeline."
      />

      {/* Pipeline overview */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <GlassCard>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
            <Clock className="h-4 w-4 text-brand-cyan" /> Discovery interval
          </div>
          {settingsQ.isLoading ? (
            <Skeleton className="mt-3 h-7 w-24" />
          ) : (
            <p className="mt-2 text-2xl font-semibold text-white">
              {discoveryMinutes} min
              <span className="ml-1 text-sm font-normal text-slate-400">
                ({s?.discovery_interval_seconds ?? 0}s)
              </span>
            </p>
          )}
        </GlassCard>
        <GlassCard delay={0.05}>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
            <Cpu className="h-4 w-4 text-brand-violet" /> Active model
          </div>
          {settingsQ.isLoading ? (
            <Skeleton className="mt-3 h-7 w-32" />
          ) : (
            <>
              <p className="mt-2 text-lg font-semibold text-white">
                {s?.llm_model || '—'}
              </p>
              <p className="text-xs text-slate-400">{s?.llm_provider || '—'}</p>
            </>
          )}
        </GlassCard>
        <GlassCard delay={0.1}>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
            <KeyRound className="h-4 w-4 text-brand-indigo" /> Google credentials
          </div>
          {settingsQ.isLoading ? (
            <Skeleton className="mt-3 h-7 w-28" />
          ) : (
            <p
              className={cn(
                'mt-2 text-lg font-semibold',
                s?.credentials_uploaded ? 'text-emerald-300' : 'text-amber-300'
              )}
            >
              {s?.credentials_uploaded ? 'Uploaded' : 'Not uploaded'}
            </p>
          )}
        </GlassCard>
      </div>

      {/* Export settings */}
      <GlassCard>
        <div className="flex items-center gap-2">
          <Sheet className="h-4 w-4 text-brand-cyan" />
          <h3 className="text-sm font-semibold text-white">
            Google Sheets export
          </h3>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-slate-400">
              Spreadsheet ID
            </span>
            <input
              className="input-glass"
              value={spreadsheetId}
              onChange={(e) => setSpreadsheetId(e.target.value)}
              placeholder="1AbC…xyz"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-slate-400">
              Worksheet name
            </span>
            <input
              className="input-glass"
              value={worksheet}
              onChange={(e) => setWorksheet(e.target.value)}
              placeholder="Transfers"
            />
          </label>
        </div>

        <button
          type="button"
          onClick={() => setAutoExport((v) => !v)}
          className="mt-4 flex items-center gap-3"
        >
          <span
            className={cn(
              'relative h-6 w-11 rounded-full transition-colors',
              autoExport ? 'bg-accent-gradient' : 'bg-white/10'
            )}
          >
            <span
              className={cn(
                'absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform',
                autoExport ? 'translate-x-[22px]' : 'translate-x-0.5'
              )}
            />
          </span>
          <span className="text-sm text-slate-200">
            Auto-export verified transfers
          </span>
        </button>

        <div className="mt-5 flex items-center gap-3">
          <button
            onClick={() => saveExport.mutate()}
            disabled={saveExport.isPending}
            className="btn-gradient"
          >
            {saveExport.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Save export settings
          </button>
          {saveExport.isSuccess && (
            <span className="flex items-center gap-1.5 text-sm text-emerald-300">
              <CheckCircle2 className="h-4 w-4" /> Saved
            </span>
          )}
          {saveExport.isError && (
            <span className="text-sm text-rose-300">Failed to save.</span>
          )}
        </div>
      </GlassCard>

      {/* Credentials upload */}
      <GlassCard>
        <div className="flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-brand-violet" />
          <h3 className="text-sm font-semibold text-white">
            Google service-account credentials
          </h3>
        </div>
        <p className="mt-1.5 text-sm text-slate-400">
          Upload the service-account JSON used to write to Google Sheets.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept="application/json,.json"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate(file);
            }}
            className="block text-sm text-slate-300 file:mr-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-white/10 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-white/15"
          />
          {upload.isPending && (
            <span className="flex items-center gap-1.5 text-sm text-slate-300">
              <Loader2 className="h-4 w-4 animate-spin" /> Uploading…
            </span>
          )}
          {upload.isSuccess && (
            <span className="flex items-center gap-1.5 text-sm text-emerald-300">
              <CheckCircle2 className="h-4 w-4" /> Uploaded
            </span>
          )}
          {upload.isError && (
            <span className="text-sm text-rose-300">Upload failed.</span>
          )}
        </div>
      </GlassCard>

      {/* Model / provider picker */}
      <GlassCard>
        <div className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-brand-indigo" />
          <h3 className="text-sm font-semibold text-white">
            Model &amp; provider
          </h3>
        </div>
        {modelsQ.isLoading ? (
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
        ) : (m?.providers.length ?? 0) === 0 ? (
          <p className="mt-3 text-sm text-slate-400">
            No providers reported by the backend.
          </p>
        ) : (
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {m!.providers.map((p) => {
              const active = p.id === m!.active;
              return (
                <div
                  key={p.id}
                  className={cn(
                    'rounded-xl border p-4 transition',
                    active
                      ? 'border-brand-violet/50 bg-brand-violet/10'
                      : 'border-white/10 bg-white/[0.03]',
                    !p.available && 'opacity-50'
                  )}
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold text-white">
                      {p.label}
                    </p>
                    {active && (
                      <span className="rounded-full bg-accent-gradient px-2 py-0.5 text-[10px] font-medium text-white">
                        Active
                      </span>
                    )}
                  </div>
                  <p className="mt-1 font-mono text-xs text-slate-400">
                    {p.model}
                  </p>
                  <p
                    className={cn(
                      'mt-2 text-xs font-medium',
                      p.available ? 'text-emerald-300' : 'text-slate-500'
                    )}
                  >
                    {p.available ? '● Available' : '○ Unavailable'}
                  </p>
                </div>
              );
            })}
          </div>
        )}
        <p className="mt-3 text-xs text-slate-500">
          The active model is configured on the backend. Availability reflects
          provider credentials detected server-side.
        </p>
      </GlassCard>

      {/* Notifications (display-only) */}
      <GlassCard>
        <div className="flex items-center gap-2">
          <Bell className="h-4 w-4 text-brand-cyan" />
          <h3 className="text-sm font-semibold text-white">Notifications</h3>
        </div>
        <div className="mt-4 space-y-3">
          {[
            { label: 'Email on conflicted transfers', on: true },
            { label: 'Email on export failures', on: true },
            { label: 'Daily digest summary', on: false },
          ].map((n) => (
            <div
              key={n.label}
              className="flex items-center justify-between rounded-lg bg-white/[0.03] px-3 py-2.5"
            >
              <span className="text-sm text-slate-200">{n.label}</span>
              <span
                className={cn(
                  'relative h-5 w-9 rounded-full',
                  n.on ? 'bg-accent-gradient' : 'bg-white/10'
                )}
              >
                <span
                  className={cn(
                    'absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform',
                    n.on ? 'translate-x-[18px]' : 'translate-x-0.5'
                  )}
                />
              </span>
            </div>
          ))}
          <p className="text-xs text-slate-500">
            Notification preferences are display-only in this build.
          </p>
        </div>
      </GlassCard>
    </div>
  );
}
