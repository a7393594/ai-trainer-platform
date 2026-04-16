'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { searchRules, listRuleSources, listRules } from '@/lib/referee-api';
import { domain } from '@/lib/referee-config';
import { useI18n } from '@/lib/i18n';
import type { RuleItem, RuleSource } from '@/types/referee';

export default function KnowledgePage() {
  const { t } = useI18n();
  const [sources, setSources] = useState<RuleSource[]>([]);
  const [activeSource, setActiveSource] = useState<string | undefined>(undefined);
  const [rules, setRules] = useState<RuleItem[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [searchLoading, setSearchLoading] = useState(false);
  const [error, setError] = useState('');
  const [expandedRules, setExpandedRules] = useState<Set<string>>(new Set());
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load sources on mount
  useEffect(() => {
    listRuleSources()
      .then(setSources)
      .catch((e) => setError(e.message));
  }, []);

  // Load rules when source changes (and no search query)
  useEffect(() => {
    if (searchQuery.trim()) return;
    setLoading(true);
    listRules(activeSource)
      .then(setRules)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [activeSource, searchQuery]);

  // Debounced search
  const handleSearchChange = useCallback((value: string) => {
    setSearchQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!value.trim()) return;

    debounceRef.current = setTimeout(() => {
      setSearchLoading(true);
      searchRules(value.trim(), 20)
        .then(setRules)
        .catch((e) => setError(e.message))
        .finally(() => setSearchLoading(false));
    }, 400);
  }, []);

  const toggleRule = (code: string) => {
    setExpandedRules((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  // Stats
  const totalRules = rules.length;
  const judgmentCount = rules.filter((r) => r.requires_judgment).length;
  const judgmentPct = totalRules > 0 ? ((judgmentCount / totalRules) * 100).toFixed(0) : '0';
  const topics = new Set(rules.map((r) => r.topic).filter(Boolean));

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
          {t('referee.knowledge.title')}
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          {t('referee.knowledge.desc')}
        </p>
      </div>

      {/* Search */}
      <div className="mb-6">
        <div className="relative">
          <svg
            className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder={t('referee.knowledge.searchPlaceholder')}
            className="w-full rounded-xl border border-zinc-700 bg-zinc-900/50 py-3 pl-10 pr-4 text-sm placeholder-zinc-500 outline-none transition-colors focus:border-blue-500"
          />
          {searchLoading && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
            </div>
          )}
        </div>
      </div>

      {/* Source Tabs */}
      {sources.length > 0 && (
        <div className="mb-6 flex flex-wrap gap-2">
          <button
            onClick={() => {
              setActiveSource(undefined);
              setSearchQuery('');
            }}
            className={`rounded-lg border px-4 py-2 text-xs font-medium transition-colors ${
              !activeSource && !searchQuery.trim()
                ? 'border-blue-500 bg-blue-600/20 text-blue-400'
                : 'border-zinc-700 bg-zinc-800/50 text-zinc-400 hover:border-zinc-600'
            }`}
          >
            {t('referee.knowledge.allSources')}
          </button>
          {sources.map((src) => (
            <button
              key={src.source_id}
              onClick={() => {
                setActiveSource(src.source_id);
                setSearchQuery('');
              }}
              className={`rounded-lg border px-4 py-2 text-xs font-medium transition-colors ${
                activeSource === src.source_id
                  ? 'border-blue-500 bg-blue-600/20 text-blue-400'
                  : 'border-zinc-700 bg-zinc-800/50 text-zinc-400 hover:border-zinc-600'
              }`}
            >
              {src.name}
              <span className="ml-1.5 text-zinc-500">({src.rule_count})</span>
            </button>
          ))}
        </div>
      )}

      {/* Stats Bar */}
      <div className="mb-6 flex items-center gap-6 rounded-xl border border-zinc-800 bg-zinc-900/50 px-6 py-3">
        <div className="text-xs text-zinc-400">
          <span className="mr-1 font-mono text-sm font-bold text-zinc-200">{totalRules}</span>
          {t('referee.knowledge.totalRules')}
        </div>
        <div className="text-xs text-zinc-400">
          <span className="mr-1 font-mono text-sm font-bold text-amber-400">{judgmentPct}%</span>
          {t('referee.knowledge.requiresJudgment')}
        </div>
        <div className="text-xs text-zinc-400">
          <span className="mr-1 font-mono text-sm font-bold text-violet-400">{topics.size}</span>
          {t('referee.knowledge.topics')}
        </div>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-red-500/50 bg-red-950/30 p-4 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Rules List */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <div className="flex items-center gap-3 text-zinc-400">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
            {t('referee.knowledge.loading')}
          </div>
        </div>
      ) : rules.length === 0 ? (
        <div className="flex items-center justify-center rounded-xl border border-dashed border-zinc-700 bg-zinc-900/20 p-16 text-sm text-zinc-500">
          {t('referee.knowledge.noRules')}
          {searchQuery.trim() ? ` for "${searchQuery}"` : ''}.
        </div>
      ) : (
        <div className="space-y-3">
          {rules.map((rule) => {
            const isExpanded = expandedRules.has(rule.rule_code);
            return (
              <div
                key={rule.rule_code}
                className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden"
              >
                <button
                  onClick={() => toggleRule(rule.rule_code)}
                  className="flex w-full items-center gap-4 p-5 text-left transition-colors hover:bg-zinc-800/30"
                >
                  <span className="rounded bg-violet-900/60 px-2.5 py-1 text-xs font-bold text-violet-200 shrink-0">
                    {rule.rule_code}
                  </span>
                  <div className="min-w-0 flex-1">
                    <h3 className="text-sm font-medium text-zinc-200">{rule.title}</h3>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2">
                      {rule.requires_judgment && (
                        <span className="rounded border border-amber-500/40 bg-amber-950/50 px-2 py-0.5 text-[10px] font-medium text-amber-400">
                          {t('referee.knowledge.requiresJudgment')}
                        </span>
                      )}
                      {rule.topic && (
                        <span className="rounded bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400">
                          {rule.topic}
                        </span>
                      )}
                      {rule.tags?.map((tag) => (
                        <span
                          key={tag}
                          className="rounded bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-500"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                  <svg
                    className={`h-4 w-4 shrink-0 text-zinc-500 transition-transform ${
                      isExpanded ? 'rotate-180' : ''
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
                {isExpanded && (
                  <div className="border-t border-zinc-800 bg-zinc-950/50 p-5">
                    <p className="whitespace-pre-wrap text-xs leading-relaxed text-zinc-400">
                      {rule.full_text}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
