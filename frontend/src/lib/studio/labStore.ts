/**
 * Experiment Studio (Lab) — shared client state.
 *
 * Scope:
 *  - Currently selected case (4 sources)
 *  - In-progress overrides bundle (prompt / model / tools / knowledge / workflow steps)
 *  - Demo input pool for batch rerun
 *  - Latest rerun results history (for diff + matrix views)
 *
 * Why Zustand: the drawer, canvas, and right-side panel all read and mutate
 * the same experiment state; prop-drilling through three layers hurts clarity.
 */
import { create } from 'zustand'
import type {
  CaseSummary,
  LabOverrides,
  LabRerunResult,
  LabSourceType,
} from './types'

export interface LabExperimentRecord {
  id: string
  at: number
  input: string
  result: LabRerunResult
}

interface LabState {
  // case selection
  selectedCase: CaseSummary | null
  labRunId: string | null

  // editable bundle
  overrides: LabOverrides
  demoInputs: string[]

  // rerun history for this lab run
  history: LabExperimentRecord[]

  // canvas interaction
  selectedNodeId: string | null

  // actions
  setSelectedCase: (c: CaseSummary | null) => void
  setLabRunId: (id: string | null) => void
  setOverrides: (patch: Partial<LabOverrides>) => void
  resetOverrides: () => void
  setDemoInputs: (inputs: string[]) => void
  addDemoInput: (input: string) => void
  removeDemoInput: (idx: number) => void
  appendHistory: (rec: Omit<LabExperimentRecord, 'id' | 'at'>) => void
  clearHistory: () => void
  setSelectedNodeId: (id: string | null) => void
}

const emptyOverrides: LabOverrides = {}

export const useLabStore = create<LabState>((set) => ({
  selectedCase: null,
  labRunId: null,
  overrides: { ...emptyOverrides },
  demoInputs: [],
  history: [],
  selectedNodeId: null,

  setSelectedCase: (selectedCase) =>
    set({
      selectedCase,
      labRunId: null,
      overrides: { ...emptyOverrides },
      history: [],
      selectedNodeId: null,
    }),
  setLabRunId: (labRunId) => set({ labRunId }),
  setOverrides: (patch) =>
    set((s) => ({ overrides: { ...s.overrides, ...patch } })),
  resetOverrides: () => set({ overrides: { ...emptyOverrides } }),
  setDemoInputs: (demoInputs) => set({ demoInputs }),
  addDemoInput: (input) =>
    set((s) => ({ demoInputs: [...s.demoInputs, input] })),
  removeDemoInput: (idx) =>
    set((s) => ({
      demoInputs: s.demoInputs.filter((_, i) => i !== idx),
    })),
  appendHistory: (rec) =>
    set((s) => ({
      history: [
        ...s.history,
        { ...rec, id: `h_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`, at: Date.now() },
      ],
    })),
  clearHistory: () => set({ history: [] }),
  setSelectedNodeId: (selectedNodeId) => set({ selectedNodeId }),
}))

export function sourceTypeLabel(t: LabSourceType | null | undefined): string {
  switch (t) {
    case 'pipeline':
      return 'Pipeline'
    case 'workflow':
      return 'Workflow'
    case 'session':
      return 'Chat'
    case 'comparison':
      return 'Compare'
    default:
      return '-'
  }
}

export function sourceTypeColor(t: LabSourceType | null | undefined): string {
  switch (t) {
    case 'pipeline':
      return 'text-emerald-400'
    case 'workflow':
      return 'text-blue-400'
    case 'session':
      return 'text-amber-400'
    case 'comparison':
      return 'text-purple-400'
    default:
      return 'text-zinc-400'
  }
}
