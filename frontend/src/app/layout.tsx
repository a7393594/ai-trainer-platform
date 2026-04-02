import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'AI Trainer Platform',
  description: '對話式 AI Agent 訓練工作台',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-TW" className="dark">
      <body className="bg-zinc-900 text-zinc-100 antialiased">{children}</body>
    </html>
  )
}
