'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getRulingHistory } from '@/lib/referee-api';
import { domain, type ModeKey } from '@/lib/referee-config';
import type { RulingHistory } from '@/types/referee';

const modeBadgeMap: Record<string, string> = {
  A: 'text-emerald-400 bg-emerald-950/50 border-emerald-500/40',
  B: 'text-blue-400 bg-blue-950/50 border-blue-500/40',
  C: 'text-amber-400 bg-amber-950/50 border-amber-500/40',
  escalated: 'text-red-400 bg-red-950/50 border-red-500/40',
};

function getConfVal(c: number | { calibrated_final?: number }): number {
  return typeof c === 'number' ? c : c?.calibrated_final ?? 0;
}
function getConfMode(c: number | { routing_mode?: string }, fallback?: string): string {
  return typeof c === 'object' && c?.routing_mode ? c.routing_mode : fallback || 'C';
}
function confidenceColor(val: number): string {
  if (val >= 0.9) return 'text-emerald-400';
  if (val >= 0.8) return 'text-blue-400';
  if (val >= 0.6) return 'text-amber-400';
  return 'text-red-400';
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

export default function HistoryPage() {
  const [rulings, setRulings] = useState<RulingHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getRulingHistory(100)
      .then(setRulings)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex items-center gap-3 text-zinc-400">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
          Loading history...
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
          {domain.terms.ruling} History
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Browse all past {domain.terms.ruling.toLowerCase()}s
        </p>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-red-500/50 bg-red-950/30 p-4 text-sm text-red-300">
          {error}
        </div>
      )}

      {rulings.length === 0 && !error ? (
        <div className="flex items-center justify-center rounded-xl border border-dashed border-zinc-700 bg-zinc-900/20 p-16 text-sm text-zinc-500">
          No {domain.terms.ruling.toLowerCase()}s found. Submit one to get started.
        </div>
      ) : (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-zinc-800 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
                  <th className="px-4 py-3">Time</th>
                  <th className="px-4 py-3">{domain.terms.case} Preview</th>
                  <th className="px-4 py-3">{domain.terms.rule}s</th>
                  <th className="px-4 py-3 text-center">{domain.terms.confidence}</th>
                  <th className="px-4 py-3 text-center">Mode</th>
                  <th className="px-4 py-3 text-right">Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50">
                {rulings.map((r) => (
                  <tr
                    key={r.ruling_id}
                    className="group transition-colors hover:bg-zinc-800/30"
                  >
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-400">
                      <Link
                        href={`/referee/history/${r.ruling_id}`}
                        className="block hover:text-blue-400"
                      >
                        {formatDate(r.created_at || '')}
                      </Link>
                    </td>
                    <td className="max-w-xs px-4 py-3">
                      <Link
                        href={`/referee/history/${r.ruling_id}`}
                        className="block text-sm text-zinc-200 group-hover:text-blue-400"
                      >
                        <span className="line-clamp-1">{r.dispute_preview}</span>
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/referee/history/${r.ruling_id}`}
                        className="flex flex-wrap gap-1"
                      >
                        {(r.applicable_rules || []).slice(0, 3).map((rule) => (
                          <span
                            key={rule}
                            className="rounded bg-violet-900/40 px-1.5 py-0.5 text-[10px] text-violet-300"
                          >
                            {rule}
                          </span>
                        ))}
                        {(r.applicable_rules || []).length > 3 && (
                          <span className="text-[10px] text-zinc-500">
                            +{(r.applicable_rules || []).length - 3}
                          </span>
                        )}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Link href={`/referee/history/${r.ruling_id}`} className="block">
                        <span
                          className={`font-mono text-sm font-medium ${confidenceColor(getConfVal(r.confidence))}`}
                        >
                          {(getConfVal(r.confidence) * 100).toFixed(0)}%
                        </span>
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Link href={`/referee/history/${r.ruling_id}`} className="block">
                        <span
                          className={`inline-block rounded border px-2 py-0.5 text-[10px] font-medium ${
                            modeBadgeMap[getConfMode(r.confidence, r.routing_mode)] || 'text-zinc-400 border-zinc-600'
                          }`}
                        >
                          {domain.modes[getConfMode(r.confidence, r.routing_mode) as ModeKey]?.label ||
                            getConfMode(r.confidence, r.routing_mode)}
                        </span>
                      </Link>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      <Link
                        href={`/referee/history/${r.ruling_id}`}
                        className="block text-xs text-zinc-400"
                      >
                        ${(r.total_cost_usd || 0).toFixed(4)}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
