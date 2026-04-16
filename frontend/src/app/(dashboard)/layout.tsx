'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { useI18n } from '@/lib/i18n'
import { ProjectProvider, useProject } from '@/lib/project-context'

// ── Inner layout that reads ProjectContext ────────────

function DashboardInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, loading: authLoading, signOut } = useAuth()
  const { locale, setLocale, t } = useI18n()
  const { projects, currentProject, switchProject, loading: projectLoading } = useProject()

  if (authLoading || projectLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-900">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-zinc-600 border-t-blue-500" />
      </div>
    )
  }

  if (!user) {
    router.push('/login')
    return null
  }

  // Nav items from domain_config (fallback to empty)
  const navItems = currentProject?.domain_config?.nav || []

  // i18n label resolution: if label starts with "nav.", try t(), else use as-is
  const resolveLabel = (label: string) => {
    if (label.startsWith('nav.')) {
      const translated = t(label)
      return translated !== label ? translated : label.replace('nav.', '')
    }
    return label
  }

  return (
    <div className="flex h-screen">
      <aside className="w-56 flex-shrink-0 border-r border-zinc-800 bg-zinc-950 flex flex-col">
        {/* ── 專案切換器 ── */}
        <div className="px-3 py-3 border-b border-zinc-800">
          <select
            value={currentProject?.project_id || ''}
            onChange={(e) => switchProject(e.target.value)}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-blue-500"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.project_type === 'referee' ? '♠️' : '🤖'} {p.name}
              </option>
            ))}
          </select>
          <p className="mt-1 px-1 text-[10px] text-zinc-600">
            {currentProject?.description || ''}
          </p>
        </div>

        {/* ── 使用者 ── */}
        <div className="px-4 py-2 border-b border-zinc-800">
          <p className="text-xs text-zinc-500">{user.email?.split('@')[0]}</p>
        </div>

        {/* ── 導覽（從 domain_config.nav 動態生成）── */}
        <nav className="flex-1 px-2 py-3 space-y-1">
          {navItems.map((item) => {
            const isActive = item.href === '/overview'
              ? pathname === '/overview' || pathname === '/'
              : pathname.startsWith(item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? 'bg-blue-600/20 text-blue-400'
                    : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
                }`}
              >
                <span>{item.icon}</span>
                <span>{resolveLabel(item.label)}</span>
              </Link>
            )
          })}
        </nav>

        {/* Language Switcher */}
        <div className="border-t border-zinc-800 px-4 py-2">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setLocale('zh-TW')}
              className={`flex-1 rounded px-2 py-1 text-xs transition-colors ${
                locale === 'zh-TW' ? 'bg-blue-600/20 text-blue-400' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              中文
            </button>
            <button
              onClick={() => setLocale('en')}
              className={`flex-1 rounded px-2 py-1 text-xs transition-colors ${
                locale === 'en' ? 'bg-blue-600/20 text-blue-400' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              EN
            </button>
          </div>
        </div>

        <div className="border-t border-zinc-800 px-4 py-3">
          <button
            onClick={signOut}
            className="w-full rounded-lg px-3 py-1.5 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors text-left"
          >
            {t('nav.signOut')}
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  )
}

// ── Exported layout wraps with ProjectProvider ────────

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProjectProvider>
      <DashboardInner>{children}</DashboardInner>
    </ProjectProvider>
  )
}
