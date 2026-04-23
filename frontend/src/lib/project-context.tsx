'use client'

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { getDemoContext } from '@/lib/ai-engine'
import type { DemoContext, ProjectSummary, DomainConfig } from '@/types'

const AI_ENGINE_URL = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

// ── Types ──────────────────────────────────────

export interface ProjectConfig {
  project_id: string
  project_type: 'trainer' | 'referee' | 'poker_coach'
  name: string
  description?: string
  default_model?: string
  tenant_id?: string
  domain_config: DomainConfig
}

interface ProjectContextValue {
  projects: ProjectSummary[]
  currentProject: ProjectConfig | null
  demoContext: DemoContext | null
  switchProject: (id: string) => void
  loading: boolean
}

const ProjectContext = createContext<ProjectContextValue>({
  projects: [],
  currentProject: null,
  demoContext: null,
  switchProject: () => {},
  loading: true,
})

export function useProject() {
  return useContext(ProjectContext)
}

// ── Storage key ────────────────────────────────

const STORAGE_KEY = 'ait-current-project'

// ── Provider ───────────────────────────────────

export function ProjectProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const router = useRouter()
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [currentProject, setCurrentProject] = useState<ProjectConfig | null>(null)
  const [demoContext, setDemoContext] = useState<DemoContext | null>(null)
  const [loading, setLoading] = useState(true)

  // Fetch project list + current project config
  useEffect(() => {
    if (!user) return

    let cancelled = false

    async function load() {
      try {
        // Speculatively start both fetches in parallel. We don't know the
        // target project id until demo-context resolves, but the saved
        // localStorage id is usually correct — fire that config fetch
        // immediately and re-fetch only if demo-context disagrees.
        const email = user!.email || ''
        const savedId = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null

        const ctxPromise = getDemoContext(email)
        const speculativeConfigPromise = savedId
          ? fetch(`${AI_ENGINE_URL}/api/v1/projects/${savedId}`).then((r) => (r.ok ? r.json() : null)).catch(() => null)
          : Promise.resolve(null)

        const [ctx, speculativeConfig] = await Promise.all([ctxPromise, speculativeConfigPromise])
        if (cancelled) return

        const projectList: ProjectSummary[] = ctx.projects || []
        setProjects(projectList)
        setDemoContext(ctx)

        const targetId = (savedId && projectList.some((p) => p.id === savedId))
          ? savedId
          : ctx.project_id

        // Use speculative config if it matches the resolved target id;
        // otherwise fetch the correct one.
        let config = speculativeConfig && speculativeConfig.id === targetId ? speculativeConfig : null
        if (!config && targetId) {
          config = await fetch(`${AI_ENGINE_URL}/api/v1/projects/${targetId}`).then((r) => r.json())
        }
        if (cancelled) return

        if (config) {
          setCurrentProject({
            project_id: config.id,
            project_type: config.project_type || 'trainer',
            name: config.name,
            description: config.description,
            default_model: config.default_model,
            tenant_id: config.tenant_id,
            domain_config: config.domain_config || {},
          })
          if (typeof window !== 'undefined') {
            localStorage.setItem(STORAGE_KEY, config.id)
          }
        }
      } catch (err) {
        console.error('[ProjectContext] Failed to load projects:', err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [user])

  const switchProject = useCallback(async (id: string) => {
    try {
      const config = await fetch(`${AI_ENGINE_URL}/api/v1/projects/${id}`).then(r => r.json())
      const pc: ProjectConfig = {
        project_id: config.id,
        project_type: config.project_type || 'trainer',
        name: config.name,
        description: config.description,
        default_model: config.default_model,
        tenant_id: config.tenant_id,
        domain_config: config.domain_config || {},
      }
      setCurrentProject(pc)
      if (typeof window !== 'undefined') {
        localStorage.setItem(STORAGE_KEY, config.id)
      }
      // Navigate to first nav item of the new project
      const firstNav = pc.domain_config.nav?.[0]?.href || '/overview'
      router.push(firstNav)
    } catch (err) {
      console.error('[ProjectContext] Failed to switch project:', err)
    }
  }, [router])

  return (
    <ProjectContext.Provider value={{ projects, currentProject, demoContext, switchProject, loading }}>
      {children}
    </ProjectContext.Provider>
  )
}
