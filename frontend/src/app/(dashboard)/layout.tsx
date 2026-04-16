'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { useI18n } from '@/lib/i18n'

// ── 專案定義(可擴展更多 domain) ────────────────────
const PROJECTS = [
  {
    id: 'trainer',
    label: 'AI Trainer',
    icon: '🤖',
    description: 'AI Agent 訓練工作台',
    basePath: '',
  },
  {
    id: 'referee',
    label: 'Poker Referee',
    icon: '♠️',
    description: 'TDA 2024 裁判系統',
    basePath: '/referee',
  },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, loading, signOut } = useAuth()
  const { locale, setLocale, t } = useI18n()

  // 根據 URL 判斷目前專案
  const isReferee = pathname.startsWith('/referee')
  const currentProject = isReferee ? PROJECTS[1] : PROJECTS[0]

  // AI Trainer 導覽
  const TRAINER_NAV = [
    { href: '/overview', label: t('nav.overview'), icon: '📊' },
    { href: '/chat', label: t('nav.train'), icon: '💬' },
    { href: '/comparison', label: t('nav.comparison'), icon: '⚖️' },
    { href: '/prompts', label: t('nav.prompts'), icon: '✏️' },
    { href: '/behavior', label: t('nav.behavior'), icon: '🧠' },
    { href: '/enhance', label: t('nav.enhance'), icon: '🧰' },
    { href: '/studio', label: t('nav.studio'), icon: '🧬' },
    { href: '/integrations', label: t('nav.deploy'), icon: '🔌' },
    { href: '/settings', label: t('nav.settings'), icon: '⚙️' },
  ]

  // Poker Referee 導覽
  const REFEREE_NAV = [
    { href: '/referee', label: 'Dashboard', icon: '📊' },
    { href: '/referee/submit', label: 'Submit Ruling', icon: '📝' },
    { href: '/referee/history', label: 'History', icon: '📋' },
    { href: '/referee/knowledge', label: 'Rule Library', icon: '📚' },
    { href: '/referee/settings', label: 'Settings', icon: '⚙️' },
  ]

  const NAV_ITEMS = isReferee ? REFEREE_NAV : TRAINER_NAV

  if (loading) {
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

  return (
    <div className="flex h-screen">
      <aside className="w-56 flex-shrink-0 border-r border-zinc-800 bg-zinc-950 flex flex-col">
        {/* ── 專案切換器 ── */}
        <div className="px-3 py-3 border-b border-zinc-800">
          <select
            value={currentProject.id}
            onChange={(e) => {
              const proj = PROJECTS.find((p) => p.id === e.target.value)
              if (proj) router.push(proj.basePath || '/')
            }}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-blue-500"
          >
            {PROJECTS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.icon} {p.label}
              </option>
            ))}
          </select>
          <p className="mt-1 px-1 text-[10px] text-zinc-600">{currentProject.description}</p>
        </div>

        {/* ── 使用者 ── */}
        <div className="px-4 py-2 border-b border-zinc-800">
          <p className="text-xs text-zinc-500">{user.email?.split('@')[0]}</p>
        </div>

        {/* ── 導覽 ── */}
        <nav className="flex-1 px-2 py-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = isReferee
              ? item.href === '/referee'
                ? pathname === '/referee'
                : pathname.startsWith(item.href) && item.href !== '/referee'
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
                <span>{item.label}</span>
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
