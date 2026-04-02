'use client'

/**
 * Widget Renderer — AI 互動元件渲染器
 *
 * 負責把 AI 回傳的 WidgetDefinition 渲染成可互動的 UI 元件
 * 使用者操作後，透過 onResponse 回傳結果
 */

import { useState } from 'react'
import type { WidgetDefinition, WidgetType } from '@/types'

interface WidgetRendererProps {
  widget: WidgetDefinition
  onResponse: (result: Record<string, any>) => void
  disabled?: boolean
}

export function WidgetRenderer({ widget, onResponse, disabled }: WidgetRendererProps) {
  const Component = WIDGET_MAP[widget.widget_type]

  if (!Component) {
    return <div className="text-red-400 text-sm">未知元件類型: {widget.widget_type}</div>
  }

  return (
    <div className="my-3 rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
      <p className="mb-3 text-sm font-medium text-zinc-200">{widget.question}</p>
      <Component widget={widget} onResponse={onResponse} disabled={disabled} />
      {widget.allow_skip && (
        <button
          onClick={() => onResponse({ skipped: true })}
          disabled={disabled}
          className="mt-2 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          跳過
        </button>
      )}
    </div>
  )
}

// ============================================
// 各元件實作
// ============================================

type WidgetProps = {
  widget: WidgetDefinition
  onResponse: (result: Record<string, any>) => void
  disabled?: boolean
}

/** 單選 */
function SingleSelect({ widget, onResponse, disabled }: WidgetProps) {
  const [selected, setSelected] = useState<string | null>(null)

  return (
    <div className="flex flex-col gap-2">
      {widget.options.map((opt) => (
        <button
          key={opt.id}
          onClick={() => {
            setSelected(opt.id)
            onResponse({ selected: opt.id })
          }}
          disabled={disabled}
          className={`text-left rounded-md border px-3 py-2 text-sm transition-all ${
            selected === opt.id
              ? 'border-blue-500 bg-blue-500/20 text-blue-300'
              : 'border-zinc-600 bg-zinc-700/50 text-zinc-300 hover:border-zinc-500'
          } ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
        >
          <span className="font-medium">{opt.label}</span>
          {opt.description && (
            <span className="ml-2 text-xs text-zinc-400">{opt.description}</span>
          )}
        </button>
      ))}
    </div>
  )
}

/** 多選 */
function MultiSelect({ widget, onResponse, disabled }: WidgetProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const toggle = (id: string) => {
    const next = new Set(selected)
    next.has(id) ? next.delete(id) : next.add(id)
    setSelected(next)
  }

  return (
    <div className="flex flex-col gap-2">
      {widget.options.map((opt) => (
        <button
          key={opt.id}
          onClick={() => toggle(opt.id)}
          disabled={disabled}
          className={`text-left rounded-md border px-3 py-2 text-sm transition-all ${
            selected.has(opt.id)
              ? 'border-blue-500 bg-blue-500/20 text-blue-300'
              : 'border-zinc-600 bg-zinc-700/50 text-zinc-300 hover:border-zinc-500'
          }`}
        >
          <span className="mr-2">{selected.has(opt.id) ? '☑' : '☐'}</span>
          {opt.label}
          {opt.description && (
            <span className="ml-2 text-xs text-zinc-400">{opt.description}</span>
          )}
        </button>
      ))}
      <button
        onClick={() => onResponse({ selected: Array.from(selected) })}
        disabled={disabled || selected.size === 0}
        className="mt-1 rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500 disabled:opacity-50"
      >
        確認選擇
      </button>
    </div>
  )
}

/** 確認 / 取消 */
function Confirm({ widget, onResponse, disabled }: WidgetProps) {
  return (
    <div className="flex gap-3">
      <button
        onClick={() => onResponse({ confirmed: true })}
        disabled={disabled}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500 disabled:opacity-50"
      >
        確認
      </button>
      <button
        onClick={() => onResponse({ confirmed: false })}
        disabled={disabled}
        className="rounded-md border border-zinc-600 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
      >
        取消
      </button>
    </div>
  )
}

/** 數值滑桿 */
function Slider({ widget, onResponse, disabled }: WidgetProps) {
  const min = widget.config?.min ?? 0
  const max = widget.config?.max ?? 100
  const step = widget.config?.step ?? 1
  const [value, setValue] = useState(widget.config?.default ?? Math.round((min + max) / 2))

  return (
    <div className="flex flex-col gap-2">
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => setValue(Number(e.target.value))}
        disabled={disabled}
        className="w-full accent-blue-500"
      />
      <div className="flex items-center justify-between">
        <span className="text-sm text-zinc-400">{value}</span>
        <button
          onClick={() => onResponse({ value })}
          disabled={disabled}
          className="rounded-md bg-blue-600 px-4 py-1.5 text-sm text-white hover:bg-blue-500"
        >
          確認
        </button>
      </div>
    </div>
  )
}

/** 排序（簡化版 — 點擊調整順序） */
function Rank({ widget, onResponse, disabled }: WidgetProps) {
  const [items, setItems] = useState(widget.options.map((o) => o.id))

  const moveUp = (idx: number) => {
    if (idx === 0) return
    const next = [...items]
    ;[next[idx - 1], next[idx]] = [next[idx], next[idx - 1]]
    setItems(next)
  }

  const labelMap = Object.fromEntries(widget.options.map((o) => [o.id, o.label]))

  return (
    <div className="flex flex-col gap-1">
      {items.map((id, idx) => (
        <div
          key={id}
          className="flex items-center gap-2 rounded-md border border-zinc-600 bg-zinc-700/50 px-3 py-2 text-sm text-zinc-300"
        >
          <span className="text-zinc-500 w-5">{idx + 1}.</span>
          <span className="flex-1">{labelMap[id]}</span>
          <button
            onClick={() => moveUp(idx)}
            disabled={disabled || idx === 0}
            className="text-xs text-zinc-400 hover:text-white disabled:opacity-30"
          >
            ▲
          </button>
        </div>
      ))}
      <button
        onClick={() => onResponse({ ranked: items })}
        disabled={disabled}
        className="mt-1 rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500"
      >
        確認排序
      </button>
    </div>
  )
}

/** 迷你表單 */
function FormWidget({ widget, onResponse, disabled }: WidgetProps) {
  const fields = widget.config?.fields ?? []
  const [values, setValues] = useState<Record<string, any>>({})

  return (
    <div className="flex flex-col gap-3">
      {fields.map((field: any) => (
        <div key={field.name}>
          <label className="mb-1 block text-xs text-zinc-400">{field.label}</label>
          <input
            type={field.type === 'number' ? 'number' : 'text'}
            value={values[field.name] ?? ''}
            onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
            disabled={disabled}
            className="w-full rounded-md border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-blue-500"
            placeholder={field.placeholder}
          />
        </div>
      ))}
      <button
        onClick={() => onResponse({ fields: values })}
        disabled={disabled}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500"
      >
        送出
      </button>
    </div>
  )
}

/** 日期選擇 */
function DatePicker({ widget, onResponse, disabled }: WidgetProps) {
  const [value, setValue] = useState('')

  return (
    <div className="flex items-center gap-3">
      <input
        type="datetime-local"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled}
        className="rounded-md border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-blue-500"
      />
      <button
        onClick={() => onResponse({ datetime: value })}
        disabled={disabled || !value}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500 disabled:opacity-50"
      >
        確認
      </button>
    </div>
  )
}

/** 卡片輪播（簡化版 — 水平滾動） */
function CardCarousel({ widget, onResponse, disabled }: WidgetProps) {
  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {widget.options.map((opt) => (
        <button
          key={opt.id}
          onClick={() => onResponse({ selected_card: opt.id })}
          disabled={disabled}
          className="flex-shrink-0 w-48 rounded-lg border border-zinc-600 bg-zinc-700/50 p-3 text-left transition-all hover:border-blue-500 hover:bg-blue-500/10"
        >
          <p className="font-medium text-sm text-zinc-200">{opt.label}</p>
          {opt.description && (
            <p className="mt-1 text-xs text-zinc-400">{opt.description}</p>
          )}
        </button>
      ))}
    </div>
  )
}

// ============================================
// 元件映射表
// ============================================

const WIDGET_MAP: Record<WidgetType, React.ComponentType<WidgetProps>> = {
  single_select: SingleSelect,
  multi_select: MultiSelect,
  confirm: Confirm,
  slider: Slider,
  rank: Rank,
  form: FormWidget,
  date_picker: DatePicker,
  card_carousel: CardCarousel,
}
