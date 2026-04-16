'use client';

import { useEffect, useState } from 'react';
import { getConfig, updateConfig, listModels } from '@/lib/referee-api';
import { domain } from '@/lib/referee-config';
import { useI18n } from '@/lib/i18n';
import type { ModelInfo, SystemConfig } from '@/types/referee';

export default function SettingsPage() {
  const { t } = useI18n();
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Load config and models on mount
  useEffect(() => {
    Promise.all([getConfig(), listModels()])
      .then(([cfg, mods]) => {
        setConfig(cfg);
        setModels(mods);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Auto-dismiss toast
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setToast(null);
    try {
      const updated = await updateConfig(config);
      setConfig(updated);
      setToast({ type: 'success', message: t('referee.settings.saved') });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setToast({ type: 'error', message: `Failed to save: ${msg}` });
    } finally {
      setSaving(false);
    }
  };

  const update = <K extends keyof SystemConfig>(key: K, value: SystemConfig[K]) => {
    setConfig((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const availableModels = models.filter((m) => m.available);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex items-center gap-3 text-zinc-400">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
          {t('referee.settings.loading')}
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

  if (!config) return null;

  return (
    <div className="p-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-100">{t('referee.settings.title')}</h1>
          <p className="mt-1 text-sm text-zinc-500">Configure {domain.name} behavior</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500"
        >
          {saving ? (
            <span className="flex items-center gap-2">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-zinc-400 border-t-white" />
              {t('referee.settings.saving')}
            </span>
          ) : (
            t('referee.settings.save')
          )}
        </button>
      </div>

      {/* Toast */}
      {toast && (
        <div
          className={`mb-6 rounded-xl border p-4 text-sm ${
            toast.type === 'success'
              ? 'border-emerald-500/50 bg-emerald-950/30 text-emerald-300'
              : 'border-red-500/50 bg-red-950/30 text-red-300'
          }`}
        >
          {toast.message}
        </div>
      )}

      <div className="space-y-6">
        {/* Models Section */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="mb-4 text-sm font-semibold text-zinc-300">{t('referee.settings.modelConfig')}</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">
                {t('referee.settings.primaryModel')}
              </label>
              <select
                value={config.primary_model}
                onChange={(e) => update('primary_model', e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm outline-none transition-colors focus:border-blue-500"
              >
                {availableModels.map((m) => (
                  <option key={m.model_id} value={m.model_id}>
                    {m.display_name}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-[10px] text-zinc-600">Main model for ruling decisions</p>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">
                {t('referee.settings.backupModel')}
              </label>
              <select
                value={config.backup_model}
                onChange={(e) => update('backup_model', e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm outline-none transition-colors focus:border-blue-500"
              >
                {availableModels.map((m) => (
                  <option key={m.model_id} value={m.model_id}>
                    {m.display_name}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-[10px] text-zinc-600">
                Cross-verification and fallback
              </p>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">
                {t('referee.settings.triageModel')}
              </label>
              <select
                value={config.triage_model}
                onChange={(e) => update('triage_model', e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm outline-none transition-colors focus:border-blue-500"
              >
                {availableModels.map((m) => (
                  <option key={m.model_id} value={m.model_id}>
                    {m.display_name}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-[10px] text-zinc-600">
                Lightweight model for classification
              </p>
            </div>
          </div>
        </div>

        {/* Thresholds Section */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="mb-4 text-sm font-semibold text-zinc-300">
            {t('referee.settings.thresholds')}
          </h2>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <label className="text-xs font-medium text-zinc-400">
                  {t('referee.settings.autoDecide')}
                </label>
                <span className="font-mono text-sm font-bold text-emerald-400">
                  {config.auto_decide_threshold.toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                min="0.70"
                max="0.95"
                step="0.01"
                value={config.auto_decide_threshold}
                onChange={(e) => update('auto_decide_threshold', parseFloat(e.target.value))}
                className="w-full"
              />
              <div className="mt-1 flex justify-between text-[10px] text-zinc-600">
                <span>0.70</span>
                <span>0.95</span>
              </div>
              <p className="mt-1 text-[10px] text-zinc-600">
                Above this threshold: Mode A (auto-decide)
              </p>
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between">
                <label className="text-xs font-medium text-zinc-400">
                  {t('referee.settings.humanConfirm')}
                </label>
                <span className="font-mono text-sm font-bold text-amber-400">
                  {config.human_confirm_threshold.toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                min="0.40"
                max="0.80"
                step="0.01"
                value={config.human_confirm_threshold}
                onChange={(e) => update('human_confirm_threshold', parseFloat(e.target.value))}
                className="w-full"
              />
              <div className="mt-1 flex justify-between text-[10px] text-zinc-600">
                <span>0.40</span>
                <span>0.80</span>
              </div>
              <p className="mt-1 text-[10px] text-zinc-600">
                Below this threshold: Mode C (human confirm)
              </p>
            </div>
          </div>
          {/* Visual threshold bar */}
          <div className="mt-6">
            <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-zinc-500">
              Routing Visualization
            </p>
            <div className="relative h-8 rounded-lg overflow-hidden">
              {/* Background sections */}
              <div
                className="absolute inset-y-0 left-0 bg-red-600/30"
                style={{ width: `${config.human_confirm_threshold * 100}%` }}
              />
              <div
                className="absolute inset-y-0 bg-amber-600/30"
                style={{
                  left: `${config.human_confirm_threshold * 100}%`,
                  width: `${(config.auto_decide_threshold - config.human_confirm_threshold) * 100}%`,
                }}
              />
              <div
                className="absolute inset-y-0 right-0 bg-emerald-600/30"
                style={{ width: `${(1 - config.auto_decide_threshold) * 100}%` }}
              />
              {/* Labels */}
              <div className="absolute inset-0 flex items-center">
                <div
                  className="flex items-center justify-center text-[10px] font-medium text-red-300"
                  style={{ width: `${config.human_confirm_threshold * 100}%` }}
                >
                  {config.human_confirm_threshold * 100 > 15 ? 'Mode C' : ''}
                </div>
                <div
                  className="flex items-center justify-center text-[10px] font-medium text-amber-300"
                  style={{
                    width: `${(config.auto_decide_threshold - config.human_confirm_threshold) * 100}%`,
                  }}
                >
                  {(config.auto_decide_threshold - config.human_confirm_threshold) * 100 > 15
                    ? 'Mode B'
                    : ''}
                </div>
                <div
                  className="flex items-center justify-center text-[10px] font-medium text-emerald-300"
                  style={{ width: `${(1 - config.auto_decide_threshold) * 100}%` }}
                >
                  {(1 - config.auto_decide_threshold) * 100 > 10 ? 'Mode A' : ''}
                </div>
              </div>
            </div>
            <div className="mt-1 flex justify-between text-[10px] text-zinc-600">
              <span>0.00</span>
              <span>1.00</span>
            </div>
          </div>
        </div>

        {/* Voting Section */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="mb-4 text-sm font-semibold text-zinc-300">
            {t('referee.settings.multiModelVoting')}
          </h2>
          <div className="space-y-5">
            {/* Toggles */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="flex items-center justify-between rounded-lg border border-zinc-800 p-4">
                <div>
                  <p className="text-sm font-medium text-zinc-200">{t('referee.settings.dualModel')}</p>
                  <p className="text-[10px] text-zinc-500">
                    Cross-verify with a second model
                  </p>
                </div>
                <button
                  onClick={() => update('enable_dual_model', !config.enable_dual_model)}
                  className={`relative h-6 w-11 rounded-full transition-colors ${
                    config.enable_dual_model ? 'bg-blue-600' : 'bg-zinc-700'
                  }`}
                >
                  <span
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                      config.enable_dual_model ? 'translate-x-5' : 'translate-x-0.5'
                    }`}
                  />
                </button>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-zinc-800 p-4">
                <div>
                  <p className="text-sm font-medium text-zinc-200">{t('referee.settings.tripleModel')}</p>
                  <p className="text-[10px] text-zinc-500">
                    Three-way voting for maximum accuracy
                  </p>
                </div>
                <button
                  onClick={() => update('enable_triple_model', !config.enable_triple_model)}
                  className={`relative h-6 w-11 rounded-full transition-colors ${
                    config.enable_triple_model ? 'bg-blue-600' : 'bg-zinc-700'
                  }`}
                >
                  <span
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                      config.enable_triple_model ? 'translate-x-5' : 'translate-x-0.5'
                    }`}
                  />
                </button>
              </div>
            </div>

            {/* Consistency Samples */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-zinc-400">
                  {t('referee.settings.samples')}
                </label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={config.consistency_samples}
                  onChange={(e) =>
                    update('consistency_samples', Math.max(1, Math.min(10, parseInt(e.target.value) || 1)))
                  }
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm outline-none transition-colors focus:border-blue-500"
                />
                <p className="mt-1 text-[10px] text-zinc-600">
                  Number of samples for consistency scoring (1-10)
                </p>
              </div>
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <label className="text-xs font-medium text-zinc-400">{t('referee.settings.temperature')}</label>
                  <span className="font-mono text-sm font-bold text-violet-400">
                    {config.temperature.toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  min="0.00"
                  max="1.00"
                  step="0.05"
                  value={config.temperature}
                  onChange={(e) => update('temperature', parseFloat(e.target.value))}
                  className="w-full"
                />
                <div className="mt-1 flex justify-between text-[10px] text-zinc-600">
                  <span>0.00 (deterministic)</span>
                  <span>1.00 (creative)</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom Save Button */}
        <div className="flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded-lg bg-blue-600 px-8 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500"
          >
            {saving ? t('referee.settings.saving') : t('referee.settings.save')}
          </button>
        </div>
      </div>
    </div>
  );
}
