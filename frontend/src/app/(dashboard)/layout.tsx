'use client'

/**
 * Dashboard Layout — 主控台側邊欄導航
 */

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV_ITEMS = [
  { href: '/chat', label: '訓練對話', icon: '💬' },
  { href: '/knowledge', label: '知識庫', icon: '📚' },
  { href: '/prompts', label: '提示詞工作室', icon: '✏️' },
  { href: '/eval', label: '評估引擎', icon: '📊' },
  { href: '/tools', label: '工具管理', icon: '🔧' },
  { href: '/workflows', label: '工作流', icon: '⚡' },
  { href: '/settings', label: '設定', icon: '⚙️' },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()

  return (
    <div className="flex h-screen">
      {/* 側邊欄 */}
      <aside className="w-56 flex-shrink-0 border-r border-zinc-800 bg-zinc-950 flex flex-col">
        <div className="px-4 py-5 border-b border-zinc-800">
          <h1 className="text-lg font-bold text-zinc-100">🤖 AI Trainer</h1>
          <p className="text-xs text-zinc-500 mt-0.5">訓練你的 AI Agent</p>
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

        {/* 底部：專案切換 */}
        <div className="border-t border-zinc-800 px-4 py-3">
          <p className="text-xs text-zinc-500">當前專案</p>
          <p className="text-sm text-zinc-300 mt-0.5">撲克 AI 教練</p>
        </div>
      </aside>

      {/* 主內容區 */}
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  )
}
