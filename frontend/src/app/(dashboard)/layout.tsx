'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'

const NAV_ITEMS = [
  { href: '/chat', label: 'Training Chat', icon: '💬' },
  { href: '/knowledge', label: 'Knowledge', icon: '📚' },
  { href: '/prompts', label: 'Prompt Studio', icon: '✏️' },
  { href: '/eval', label: 'Eval Engine', icon: '📊' },
  { href: '/tools', label: 'Tools', icon: '🔧' },
  { href: '/workflows', label: 'Workflows', icon: '⚡' },
  { href: '/settings', label: 'Settings', icon: '⚙️' },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, loading, signOut } = useAuth()

  // Auth guard
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
        <div className="px-4 py-5 border-b border-zinc-800">
          <h1 className="text-lg font-bold text-zinc-100">AI Trainer</h1>
          <p className="text-xs text-zinc-500 mt-0.5">
            {user.email?.split('@')[0]}
          </p>
        </div>

        <nav className="flex-1 px-2 py-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname.startsWith(item.href)
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

        <div className="border-t border-zinc-800 px-4 py-3">
          <button
            onClick={signOut}
            className="w-full rounded-lg px-3 py-1.5 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors text-left"
          >
            Sign Out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  )
}
