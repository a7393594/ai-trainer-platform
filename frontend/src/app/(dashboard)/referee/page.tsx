'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getAnalyticsSummary } from '@/lib/referee-api';
import { domain, type ModeKey } from '@/lib/referee-config';
import { useI18n } from '@/lib/i18n';
import type { AnalyticsSummary } from '@/types/referee';

const modeColorMap: Record<string, string> = {
  A: 'bg-emerald-500',
  B: 'bg-blue-500',
  C: 'bg-amber-500',
  escalated: 'bg-red-500',
};

const modeBadgeMap: Record<string, string> = {
  A: 'text-emerald-400 bg-emerald-950/50 border-emerald-500/40',
  B: 'text-blue-400 bg-blue-950/50 border-blue-500/40',
  C: 'text-amber-400 bg-amber-950/50 border-amber-500/40',
  escalated: 'text-red-400 bg-red-950/50 border-red-500/40',
};

const confidenceBucketColors: Record<string, string> = {
  '0.9+': 'bg-emerald-500',
  '0.8-0.9': 'bg-blue-500',
  '0.6-0.8': 'bg-amber-500',
  '<0.6': 'bg-red-500',
  high: 'bg-emerald-500',
  medium: 'bg-blue-500',
  low: 'bg-amber-500',
  very_low: 'bg-red-500',
};

export default function DashboardPage() {
  const { t } = useI18n();
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getAnalyticsSummary()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex items-center gap-3 text-zinc-400">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
          {t('referee.dashboard.loading')}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="rounded-xl border border-red-500/50 bg-red-950/30 p-6 text-sm text-red-300">
          Failed to load analytics: {error}
        </div>
      </div>
    );
  }

  if (!data) return null;

  const totalModes = Object.values(data.mode_distribution).reduce((a, b) => a + b, 0) || 1;
  const maxBucket = Math.max(...Object.values(data.confidence_buckets), 1);
  const maxModelUsage = Math.max(...Object.values(data.model_usage), 1);

  return (
    <div className="p-8">
      {/* Page Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-100">{t('referee.dashboard.title')}</h1>
        <p className="mt-1 text-sm text-zinc-500">{domain.description}</p>
      </div>

      {/* KPI Cards */}
      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KPICard
          label={t('referee.dashboard.totalRulings')}
          value={data.total_rulings.toLocaleString()}
          accent="text-blue-400"
        />
        <KPICard
          label={t('referee.dashboard.avgConfidence')}
          value={`${(data.avg_confidence * 100).toFixed(1)}%`}
          accent="text-emerald-400"
        />
        <KPICard
          label={t('referee.dashboard.totalCost')}
          value={`$${data.total_cost_usd.toFixed(2)}`}
          accent="text-amber-400"
        />
        <KPICard
          label={t('referee.dashboard.avgLatency')}
          value={`${(data.avg_latency_ms / 1000).toFixed(2)}s`}
          accent="text-violet-400"
        />
      </div>

      <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Mode Distribution */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="mb-4 text-sm font-semibold text-zinc-300">{t('referee.dashboard.modeDistribution')}</h2>
          {/* Stacked bar */}
          <div className="mb-4 flex h-8 overflow-hidden rounded-lg">
            {Object.entries(data.mode_distribution).map(([mode, count]) => {
              const pct = (count / totalModes) * 100;
              if (pct === 0) return null;
              return (
                <div
                  key={mode}
                  className={`${modeColorMap[mode] || 'bg-zinc-600'} flex items-center justify-center text-xs font-medium text-white transition-all`}
                  style={{ width: `${pct}%`, minWidth: pct > 5 ? undefined : '20px' }}
                  title={`${mode}: ${count} (${pct.toFixed(1)}%)`}
                >
                  {pct > 12 ? `${pct.toFixed(0)}%` : ''}
                </div>
              );
            })}
          </div>
          {/* Legend */}
          <div className="flex flex-wrap gap-4">
            {Object.entries(data.mode_distribution).map(([mode, count]) => {
              const modeConfig = domain.modes[mode as ModeKey];
              return (
                <div key={mode} className="flex items-center gap-2 text-xs text-zinc-400">
                  <span
                    className={`inline-block h-3 w-3 rounded ${modeColorMap[mode] || 'bg-zinc-600'}`}
                  />
                  <span className="text-zinc-300">{modeConfig?.label || mode}</span>
                  <span className="text-zinc-500">({count})</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Confidence Buckets */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="mb-4 text-sm font-semibold text-zinc-300">
            {t('referee.dashboard.confidenceBuckets')}
          </h2>
          <div className="space-y-3">
            {Object.entries(data.confidence_buckets).map(([key, count]) => {
              const pct = (count / maxBucket) * 100;
              return (
                <div key={key} className="flex items-center gap-3">
                  <span className="w-24 text-right text-xs text-zinc-400">
                    {key}
                  </span>
                  <div className="flex-1">
                    <div className="h-6 rounded bg-zinc-800">
                      <div
                        className={`${confidenceBucketColors[key] || 'bg-zinc-500'} flex h-6 items-center rounded pl-2 text-xs font-medium text-white transition-all`}
                        style={{ width: `${Math.max(pct, 4)}%` }}
                      >
                        {count}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Model Usage */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="mb-4 text-sm font-semibold text-zinc-300">{t('referee.dashboard.modelUsage')}</h2>
          <div className="space-y-3">
            {Object.entries(data.model_usage).map(([model, count]) => {
              const pct = (count / maxModelUsage) * 100;
              return (
                <div key={model} className="flex items-center gap-3">
                  <span className="w-36 truncate text-right text-xs text-zinc-400" title={model}>
                    {model}
                  </span>
                  <div className="flex-1">
                    <div className="h-6 rounded bg-zinc-800">
                      <div
                        className="flex h-6 items-center rounded bg-violet-600 pl-2 text-xs font-medium text-white transition-all"
                        style={{ width: `${Math.max(pct, 4)}%` }}
                      >
                        {count}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Recent Rulings */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="mb-4 text-sm font-semibold text-zinc-300">
            {t('referee.dashboard.recentRulings')}
          </h2>
          {data.recent_rulings.length === 0 ? (
            <p className="text-sm text-zinc-500">{t('referee.dashboard.noRulings')}</p>
          ) : (
            <div className="space-y-2">
              {data.recent_rulings.slice(0, 5).map((r) => (
                <Link
                  key={r.id || r.ruling_id}
                  href={`/referee/history/${r.id || r.ruling_id}`}
                  className="block rounded-lg border border-zinc-800 p-3 transition-colors hover:border-zinc-700 hover:bg-zinc-800/40"
                >
                  <div className="mb-1.5 flex items-center justify-between">
                    <span
                      className={`rounded border px-2 py-0.5 text-[10px] font-medium ${
                        modeBadgeMap[r.routing_mode || ''] || 'text-zinc-400 border-zinc-600'
                      }`}
                    >
                      {domain.modes[(r.routing_mode || '') as ModeKey]?.label || r.routing_mode || '?'}
                    </span>
                    <span className="text-[10px] text-zinc-500">
                      {typeof r.confidence === 'number'
                        ? `${(r.confidence * 100).toFixed(0)}%`
                        : `${(((r.confidence as unknown as Record<string, number>)?.calibrated_final ?? 0) * 100).toFixed(0)}%`}
                    </span>
                  </div>
                  <p className="line-clamp-1 text-xs text-zinc-300">{r.dispute_preview || r.final_decision}</p>
                  <div className="mt-1 flex items-center gap-2">
                    {r.effective_rule && (
                      <span className="rounded bg-violet-900/40 px-1.5 py-0.5 text-[10px] text-violet-300">
                        {r.effective_rule}
                      </span>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function KPICard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
      <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">{label}</p>
      <p className={`mt-2 text-2xl font-bold ${accent}`}>{value}</p>
    </div>
  );
}
