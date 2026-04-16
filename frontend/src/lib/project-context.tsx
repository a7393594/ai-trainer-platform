'use client'

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import type { ProjectSummary, DomainConfig } from '@/types'

const AI_ENGINE_URL = process.env.NEXT_PUBLIC_AI_ENGINE_URL || 'http://localhost:8000'

// ── Types ──────────────────────────────────────

export interface ProjectConfig {
  project_id: string
  project_type: 'trainer' | 'referee'
  name: string
  description?: string
  domain_config: DomainConfig
}

interface ProjectContextValue {
  projects: ProjectSummary[]
  currentProject: ProjectConfig | null
  switchProject: (id: string) => void
  loading: boolean
}

const ProjectContext = createContext<ProjectContextValue>({
  projects: [],
  currentProject: null,
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
  const [loading, setLoading] = useState(true)

  // Fetch project list + current project config
  useEffect(() => {
    if (!user) return

    async function load() {
      try {
        // 1. Get demo context (includes projects list)
        const email = user!.email || ''
        const params = email ? `?email=${encodeURIComponent(email)}` : ''
        const ctx = await fetch(`${AI_ENGINE_URL}/api/v1/demo/context${params}`).then(r => r.json())

        const projectList: ProjectSummary[] = ctx.projects || []
        setProjects(projectList)

        // 2. Determine which project to load
        const savedId = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null
        const targetId = (savedId && projectList.some(p => p.id === savedId))
          ? savedId
          : ctx.project_id  // default from API

        // 3. Fetch full config for target project
        if (targetId) {
          const config = await fetch(`${AI_ENGINE_URL}/api/v1/projects/${targetId}`).then(r => r.json())
          setCurrentProject({
            project_id: config.id,
            project_type: config.project_type || 'trainer',
            name: config.name,
            description: config.description,
            domain_config: config.domain_config || {},
          })
          if (typeof window !== 'undefined') {
            localStorage.setItem(STORAGE_KEY, config.id)
          }
        }
      } catch (err) {
        console.error('[ProjectContext] Failed to load projects:', err)
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [user])

  const switchProject = useCallback(async (id: string) => {
    try {
      const config = await fetch(`${AI_ENGINE_URL}/api/v1/projects/${id}`).then(r => r.json())
      const pc: ProjectConfig = {
        project_id: config.id,
        project_type: config.project_type || 'trainer',
        name: config.name,
        description: config.description,
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
    <ProjectContext.Provider value={{ projects, currentProject, switchProject, loading }}>
      {children}
    </ProjectContext.Provider>
  )
}
