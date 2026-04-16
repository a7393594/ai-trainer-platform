'use client';

import { useState } from 'react';
import { submitRuling } from '@/lib/referee-api';
import { domain, type ModeKey } from '@/lib/referee-config';
import type { RulingResult } from '@/types/referee';

const modeBadgeMap: Record<string, string> = {
  A: 'text-emerald-400 bg-emerald-950/50 border-emerald-500/40',
  B: 'text-blue-400 bg-blue-950/50 border-blue-500/40',
  C: 'text-amber-400 bg-amber-950/50 border-amber-500/40',
  escalated: 'text-red-400 bg-red-950/50 border-red-500/40',
};

export default function SubmitPage() {
  const [dispute, setDispute] = useState('');
  const [contextValues, setContextValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const f of domain.contextFields) {
      init[f.key] = f.type === 'select' && f.options ? f.options[0] : '';
    }
    return init;
  });
  const [modelMode, setModelMode] = useState<'single' | 'dual' | 'triple'>('single');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RulingResult | null>(null);
  const [error, setError] = useState('');

  const updateContext = (key: string, value: string) => {
    setContextValues((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async () => {
    if (!dispute.trim()) return;
    setLoading(true);
    setError('');
    setResult(null);

    try {
      const gameContext: Record<string, unknown> = {};
      for (const f of domain.contextFields) {
        const val = contextValues[f.key];
        if (val) {
          gameContext[f.key] = f.type === 'number' ? Number(val) : val;
        }
      }

      const data = await submitRuling(dispute.trim(), gameContext, {
        force_dual_model: modelMode === 'dual',
        force_triple_model: modelMode === 'triple',
      });
      setResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
          Submit {domain.terms.case}
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Describe the situation and get an AI {domain.terms.ruling.toLowerCase()}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-5">
        {/* Input Panel */}
        <div className="lg:col-span-2 space-y-6">
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
            <h2 className="mb-4 text-sm font-semibold text-zinc-300">
              {domain.terms.case} Details
            </h2>

            {/* Dispute textarea */}
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-zinc-400">
                  {domain.terms.case} Description
                </label>
                <textarea
                  value={dispute}
                  onChange={(e) => setDispute(e.target.value)}
                  placeholder="Describe what happened...\ne.g. Player pushed chips forward twice without verbal declaration"
                  rows={5}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm placeholder-zinc-600 outline-none transition-colors focus:border-blue-500"
                />
              </div>

              {/* Dynamic context fields */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                {domain.contextFields.map((field) => (
                  <div key={field.key}>
                    <label className="mb-1.5 block text-xs font-medium text-zinc-400">
                      {field.label}
                    </label>
                    {field.type === 'select' && field.options ? (
                      <select
                        value={contextValues[field.key]}
                        onChange={(e) => updateContext(field.key, e.target.value)}
                        className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm outline-none transition-colors focus:border-blue-500"
                      >
                        {field.options.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type={field.type === 'number' ? 'number' : 'text'}
                        value={contextValues[field.key]}
                        onChange={(e) => updateContext(field.key, e.target.value)}
                        placeholder={'placeholder' in field ? field.placeholder : ''}
                        className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm placeholder-zinc-600 outline-none transition-colors focus:border-blue-500"
                      />
                    )}
                  </div>
                ))}
              </div>

              {/* Model mode toggle */}
              <div>
                <label className="mb-2 block text-xs font-medium text-zinc-400">
                  Verification Mode
                </label>
                <div className="flex gap-2">
                  {(['single', 'dual', 'triple'] as const).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => setModelMode(mode)}
                      className={`rounded-lg border px-4 py-2 text-xs font-medium transition-colors ${
                        modelMode === mode
                          ? 'border-blue-500 bg-blue-600/20 text-blue-400'
                          : 'border-zinc-700 bg-zinc-800/50 text-zinc-400 hover:border-zinc-600'
                      }`}
                    >
                      {mode === 'single'
                        ? 'Single Model'
                        : mode === 'dual'
                          ? 'Dual Model'
                          : 'Triple Model'}
                    </button>
                  ))}
                </div>
                <p className="mt-1.5 text-[10px] text-zinc-600">
                  {modelMode === 'single'
                    ? 'One model decides. Fastest and cheapest.'
                    : modelMode === 'dual'
                      ? 'Two models cross-verify. Higher confidence.'
                      : 'Three models vote. Maximum reliability.'}
                </p>
              </div>

              {/* Submit */}
              <button
                onClick={handleSubmit}
                disabled={loading || !dispute.trim()}
                className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-zinc-400 border-t-white" />
                    Analyzing {domain.terms.case}...
                  </span>
                ) : (
                  `Submit ${domain.terms.ruling} Request`
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Result Panel */}
        <div className="lg:col-span-3">
          {error && (
            <div className="rounded-xl border border-red-500/50 bg-red-950/30 p-4 text-sm text-red-300">
              {error}
            </div>
          )}

          {loading && (
            <div className="flex items-center justify-center rounded-xl border border-zinc-800 bg-zinc-900/50 p-16">
              <div className="flex items-center gap-3 text-zinc-400">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
                AI Referee analyzing {domain.terms.case.toLowerCase()}...
              </div>
            </div>
          )}

          {!loading && !result && !error && (
            <div className="flex items-center justify-center rounded-xl border border-dashed border-zinc-700 bg-zinc-900/20 p-20 text-center text-sm text-zinc-500">
              Describe a {domain.terms.case.toLowerCase()} on the left to get an AI{' '}
              {domain.terms.ruling.toLowerCase()}
            </div>
          )}

          {result && (
            <div className="space-y-4">
              {/* Decision */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
                <div className="mb-3 flex items-start justify-between">
                  <h2 className="text-lg font-bold text-zinc-100">{domain.terms.ruling}</h2>
                  <span
                    className={`rounded-lg border px-3 py-1 text-xs font-medium ${
                      modeBadgeMap[result.confidence?.routing_mode] || ''
                    }`}
                  >
                    {domain.modes[result.confidence?.routing_mode as ModeKey]?.label ||
                      result.confidence?.routing_mode}
                  </span>
                </div>
                <p className="mb-3 text-sm leading-relaxed text-zinc-200">{result.decision}</p>
                <div className="flex flex-wrap gap-2">
                  {result.applicable_rules?.map((r) => (
                    <span
                      key={r}
                      className="rounded bg-violet-900/60 px-2 py-0.5 text-xs text-violet-200"
                    >
                      {r}
                    </span>
                  ))}
                </div>
              </div>

              {/* Confidence */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
                <h3 className="mb-3 text-sm font-semibold text-zinc-300">
                  {domain.terms.confidence}
                </h3>
                <div className="grid grid-cols-4 gap-3 text-center">
                  {(
                    [
                      ['Verbalized', result.confidence?.verbalized],
                      ['Consistency', result.confidence?.consistency_score],
                      ['Cross-Model', result.confidence?.cross_model_agreement],
                      ['Final', result.confidence?.calibrated_final],
                    ] as [string, number][]
                  ).map(([label, val], i) => (
                    <div key={label}>
                      <div className="text-[10px] uppercase tracking-wider text-zinc-500">
                        {label}
                      </div>
                      <div
                        className={`mt-1 font-mono text-xl font-bold ${
                          i === 3 ? 'text-blue-400' : 'text-zinc-200'
                        }`}
                      >
                        {val != null ? `${(val * 100).toFixed(0)}%` : 'N/A'}
                      </div>
                      {val != null && (
                        <div className="mx-auto mt-1.5 h-1.5 w-full max-w-[60px] rounded-full bg-zinc-800">
                          <div
                            className={`h-1.5 rounded-full ${
                              val >= 0.9
                                ? 'bg-emerald-500'
                                : val >= 0.8
                                  ? 'bg-blue-500'
                                  : val >= 0.6
                                    ? 'bg-amber-500'
                                    : 'bg-red-500'
                            }`}
                            style={{ width: `${val * 100}%` }}
                          />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Reasoning */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
                <h3 className="mb-2 text-sm font-semibold text-zinc-300">Reasoning</h3>
                <p className="whitespace-pre-wrap text-xs leading-relaxed text-zinc-400">
                  {result.reasoning}
                </p>
              </div>

              {/* Subsequent Steps */}
              {result.subsequent_steps?.length > 0 && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
                  <h3 className="mb-2 text-sm font-semibold text-zinc-300">Next Steps</h3>
                  <ol className="list-inside list-decimal space-y-1.5 text-xs text-zinc-400">
                    {result.subsequent_steps.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ol>
                </div>
              )}

              {/* Voting */}
              {result.voting && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
                  <h3 className="mb-3 text-sm font-semibold text-zinc-300">
                    Multi-Model Verification:{' '}
                    {result.voting.agreement ? (
                      <span className="text-emerald-400">Agreed</span>
                    ) : (
                      <span className="text-amber-400">Diverged</span>
                    )}
                  </h3>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {[
                      result.voting.primary,
                      result.voting.secondary,
                      result.voting.tertiary,
                    ]
                      .filter(Boolean)
                      .map((v, i) => (
                        <div key={i} className="rounded-lg border border-zinc-700 p-3">
                          <div className="mb-1.5 text-xs font-medium text-violet-300">
                            {v!.model}
                          </div>
                          <p className="line-clamp-3 text-xs text-zinc-300">{v!.decision}</p>
                          <p className="mt-2 text-[10px] text-zinc-500">
                            ${v!.cost_usd?.toFixed(4)}
                          </p>
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {/* Rules Retrieved */}
              {result.rules_retrieved?.length > 0 && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
                  <h3 className="mb-3 text-sm font-semibold text-zinc-300">
                    {domain.terms.rule}s Retrieved
                  </h3>
                  <div className="space-y-2">
                    {result.rules_retrieved.map((rule, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-3 rounded-lg border border-zinc-800 p-3"
                      >
                        <span className="rounded bg-violet-900/60 px-2 py-0.5 text-xs font-medium text-violet-200">
                          {rule.rule_code}
                        </span>
                        <span className="flex-1 text-xs text-zinc-300">{rule.title}</span>
                        <span className="text-[10px] text-zinc-500">
                          {(rule.score * 100).toFixed(0)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Meta bar */}
              <div className="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-900/50 px-4 py-3 text-xs text-zinc-500">
                <span>{result.model_used}</span>
                <span>{(result.latency_ms / 1000).toFixed(1)}s</span>
                <span>${result.total_cost_usd?.toFixed(4)}</span>
                <span className="font-mono">{result.ruling_id?.slice(0, 8)}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
