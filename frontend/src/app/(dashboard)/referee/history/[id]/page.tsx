'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { getRulingDetail } from '@/lib/referee-api';
import { domain, type ModeKey } from '@/lib/referee-config';
import type { RulingResult } from '@/types/referee';

const modeBadgeMap: Record<string, string> = {
  A: 'text-emerald-400 bg-emerald-950/50 border-emerald-500/40',
  B: 'text-blue-400 bg-blue-950/50 border-blue-500/40',
  C: 'text-amber-400 bg-amber-950/50 border-amber-500/40',
  escalated: 'text-red-400 bg-red-950/50 border-red-500/40',
};

function confidenceColor(val: number): string {
  if (val >= 0.9) return 'text-emerald-400';
  if (val >= 0.8) return 'text-blue-400';
  if (val >= 0.6) return 'text-amber-400';
  return 'text-red-400';
}

function barColor(val: number): string {
  if (val >= 0.9) return 'bg-emerald-500';
  if (val >= 0.8) return 'bg-blue-500';
  if (val >= 0.6) return 'bg-amber-500';
  return 'bg-red-500';
}

export default function RulingDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [ruling, setRuling] = useState<RulingResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reasoningExpanded, setReasoningExpanded] = useState(false);
  const [expandedRules, setExpandedRules] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!id) return;
    getRulingDetail(id)
      .then(setRuling)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const toggleRule = (index: number) => {
    setExpandedRules((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex items-center gap-3 text-zinc-400">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
          Loading {domain.terms.ruling.toLowerCase()}...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="rounded-xl border border-red-500/50 bg-red-950/30 p-6 text-sm text-red-300">
          {error}
        </div>
      </div>
    );
  }

  if (!ruling) return null;

  const mode = ruling.confidence?.routing_mode as ModeKey;
  const reasoningText = ruling.reasoning || '';
  const isLongReasoning = reasoningText.length > 500;

  return (
    <div className="p-8">
      {/* Breadcrumb */}
      <div className="mb-6 flex items-center gap-2 text-xs text-zinc-500">
        <Link href="/history" className="hover:text-blue-400">
          History
        </Link>
        <span>/</span>
        <span className="text-zinc-300 font-mono">{id.slice(0, 8)}</span>
      </div>

      <div className="space-y-6">
        {/* Decision Card */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
          <div className="mb-4 flex items-start justify-between">
            <h1 className="text-xl font-bold text-zinc-100">{domain.terms.ruling}</h1>
            <span
              className={`rounded-lg border px-3 py-1 text-xs font-medium ${
                modeBadgeMap[mode] || 'text-zinc-400 border-zinc-600'
              }`}
            >
              {domain.modes[mode]?.label || mode}
            </span>
          </div>
          <p className="mb-4 text-sm leading-relaxed text-zinc-200">{ruling.decision}</p>
          <div className="flex flex-wrap gap-2">
            {ruling.applicable_rules?.map((r) => (
              <span
                key={r}
                className="rounded bg-violet-900/60 px-2.5 py-1 text-xs font-medium text-violet-200"
              >
                {r}
              </span>
            ))}
          </div>
          {/* Meta */}
          <div className="mt-4 flex items-center gap-4 border-t border-zinc-800 pt-4 text-xs text-zinc-500">
            <span>{ruling.model_used}</span>
            <span>{(ruling.latency_ms / 1000).toFixed(1)}s latency</span>
            <span>${ruling.total_cost_usd?.toFixed(4)}</span>
            {ruling.created_at && (
              <span>
                {new Date(ruling.created_at).toLocaleString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
            )}
          </div>
        </div>

        {/* Confidence Panel */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="mb-4 text-sm font-semibold text-zinc-300">
            {domain.terms.confidence} Analysis
          </h2>
          <div className="grid grid-cols-2 gap-6 lg:grid-cols-4">
            {(
              [
                ['Verbalized', ruling.confidence?.verbalized],
                ['Consistency', ruling.confidence?.consistency_score],
                ['Cross-Model', ruling.confidence?.cross_model_agreement],
                ['Calibrated Final', ruling.confidence?.calibrated_final],
              ] as [string, number][]
            ).map(([label, val]) => (
              <div key={label} className="text-center">
                <p className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</p>
                <p
                  className={`mt-1 font-mono text-2xl font-bold ${
                    val != null ? confidenceColor(val) : 'text-zinc-500'
                  }`}
                >
                  {val != null ? `${(val * 100).toFixed(0)}%` : 'N/A'}
                </p>
                {val != null && (
                  <div className="mx-auto mt-2 h-2 w-full max-w-[80px] rounded-full bg-zinc-800">
                    <div
                      className={`h-2 rounded-full ${barColor(val)}`}
                      style={{ width: `${val * 100}%` }}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Reasoning (collapsible) */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-300">Reasoning</h2>
            {isLongReasoning && (
              <button
                onClick={() => setReasoningExpanded(!reasoningExpanded)}
                className="text-xs text-blue-400 hover:text-blue-300"
              >
                {reasoningExpanded ? 'Collapse' : 'Expand'}
              </button>
            )}
          </div>
          <p
            className={`whitespace-pre-wrap text-xs leading-relaxed text-zinc-400 ${
              !reasoningExpanded && isLongReasoning ? 'line-clamp-6' : ''
            }`}
          >
            {reasoningText}
          </p>
        </div>

        {/* Subsequent Steps */}
        {ruling.subsequent_steps?.length > 0 && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
            <h2 className="mb-3 text-sm font-semibold text-zinc-300">Subsequent Steps</h2>
            <ol className="space-y-2">
              {ruling.subsequent_steps.map((step, i) => (
                <li key={i} className="flex items-start gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600/20 text-xs font-medium text-blue-400">
                    {i + 1}
                  </span>
                  <span className="text-sm text-zinc-300 pt-0.5">{step}</span>
                </li>
              ))}
            </ol>
          </div>
        )}

        {/* Voting */}
        {ruling.voting && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
            <h2 className="mb-3 text-sm font-semibold text-zinc-300">
              Multi-Model Verification:{' '}
              {ruling.voting.agreement ? (
                <span className="text-emerald-400">Models Agreed</span>
              ) : (
                <span className="text-amber-400">Models Diverged</span>
              )}
            </h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[ruling.voting.primary, ruling.voting.secondary, ruling.voting.tertiary]
                .filter(Boolean)
                .map((v, i) => (
                  <div key={i} className="rounded-lg border border-zinc-700 p-4">
                    <div className="mb-2 text-xs font-medium text-violet-300">{v!.model}</div>
                    <p className="text-xs leading-relaxed text-zinc-300">{v!.decision}</p>
                    <p className="mt-2 text-[10px] text-zinc-500">${v!.cost_usd?.toFixed(4)}</p>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Rules Retrieved (expandable cards) */}
        {ruling.rules_retrieved?.length > 0 && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
            <h2 className="mb-4 text-sm font-semibold text-zinc-300">
              {domain.terms.rule}s Retrieved
            </h2>
            <div className="space-y-3">
              {ruling.rules_retrieved.map((rule, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-zinc-800 overflow-hidden"
                >
                  <button
                    onClick={() => toggleRule(i)}
                    className="flex w-full items-center gap-3 p-4 text-left transition-colors hover:bg-zinc-800/30"
                  >
                    <span className="rounded bg-violet-900/60 px-2 py-0.5 text-xs font-medium text-violet-200">
                      {rule.rule_code}
                    </span>
                    <span className="flex-1 text-sm text-zinc-200">{rule.title}</span>
                    <span className="text-xs text-zinc-500">
                      {(rule.score * 100).toFixed(0)}% match
                    </span>
                    <svg
                      className={`h-4 w-4 text-zinc-500 transition-transform ${
                        expandedRules.has(i) ? 'rotate-180' : ''
                      }`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 9l-7 7-7-7"
                      />
                    </svg>
                  </button>
                  {expandedRules.has(i) && rule.full_text && (
                    <div className="border-t border-zinc-800 bg-zinc-950/50 p-4">
                      <p className="whitespace-pre-wrap text-xs leading-relaxed text-zinc-400">
                        {rule.full_text}
                      </p>
                      {rule.topic && (
                        <span className="mt-2 inline-block rounded bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400">
                          {rule.topic}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Audit Log */}
        {ruling.audit_log && Object.keys(ruling.audit_log).length > 0 && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
            <h2 className="mb-3 text-sm font-semibold text-zinc-300">Audit Log</h2>
            <pre className="overflow-x-auto rounded-lg bg-zinc-950 p-4 text-xs text-zinc-400 font-mono">
              {JSON.stringify(ruling.audit_log, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
