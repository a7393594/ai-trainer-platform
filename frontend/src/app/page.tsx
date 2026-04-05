'use client'

import Link from 'next/link'
import { useI18n } from '@/lib/i18n'

export default function LandingPage() {
  const { t, locale, setLocale } = useI18n()
  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Hero */}
      <header className="border-b border-zinc-800">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-bold text-zinc-100">AI Trainer</h1>
            <div className="flex gap-1">
              <button onClick={() => setLocale('zh-TW')} className={`text-xs px-2 py-1 rounded ${locale === 'zh-TW' ? 'text-blue-400' : 'text-zinc-500'}`}>中文</button>
              <button onClick={() => setLocale('en')} className={`text-xs px-2 py-1 rounded ${locale === 'en' ? 'text-blue-400' : 'text-zinc-500'}`}>EN</button>
            </div>
          </div>
          <Link
            href="/chat"
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
          >
            {t('landing.openDashboard')}
          </Link>
        </div>
      </header>

      <main>
        {/* Hero Section */}
        <section className="max-w-6xl mx-auto px-6 py-24 text-center">
          <div className="inline-block rounded-full bg-blue-500/10 border border-blue-500/20 px-4 py-1 text-xs text-blue-400 mb-6">
            {t('landing.badge')}
          </div>
          <h2 className="text-5xl font-bold text-zinc-100 leading-tight">
            {t('landing.heroTitle1')}<br />
            <span className="text-blue-400">{t('landing.heroTitle2')}</span>
          </h2>
          <p className="mt-6 text-lg text-zinc-400 max-w-2xl mx-auto">
            {t('landing.heroDesc')}
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
            <Link
              href="/chat"
              className="rounded-lg bg-blue-600 px-8 py-3 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
            >
              {t('landing.start')}
            </Link>
            <Link
              href="/settings"
              className="rounded-lg border border-zinc-700 px-8 py-3 text-sm font-medium text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              {t('landing.viewSettings')}
            </Link>
          </div>
        </section>

        {/* Features Grid */}
        <section className="max-w-6xl mx-auto px-6 py-16">
          <h3 className="text-2xl font-bold text-zinc-200 text-center mb-12">{t('landing.everything')}</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[
              { icon: '💬', title: t('landing.feat.chat'), desc: t('landing.feat.chatDesc'), href: '/chat' },
              { icon: '📚', title: t('landing.feat.knowledge'), desc: t('landing.feat.knowledgeDesc'), href: '/knowledge' },
              { icon: '✏️', title: t('landing.feat.prompts'), desc: t('landing.feat.promptsDesc'), href: '/prompts' },
              { icon: '📊', title: t('landing.feat.eval'), desc: t('landing.feat.evalDesc'), href: '/eval' },
              { icon: '🔧', title: t('landing.feat.tools'), desc: t('landing.feat.toolsDesc'), href: '/tools' },
              { icon: '⚡', title: t('landing.feat.workflows'), desc: t('landing.feat.workflowsDesc'), href: '/workflows' },
            ].map((feature) => (
              <Link
                key={feature.href}
                href={feature.href}
                className="group rounded-xl border border-zinc-800 bg-zinc-900 p-6 hover:border-zinc-700 hover:bg-zinc-800/50 transition-all"
              >
                <span className="text-3xl">{feature.icon}</span>
                <h4 className="mt-4 text-lg font-medium text-zinc-200 group-hover:text-blue-400 transition-colors">
                  {feature.title}
                </h4>
                <p className="mt-2 text-sm text-zinc-400 leading-relaxed">{feature.desc}</p>
              </Link>
            ))}
          </div>
        </section>

        {/* Training Loop */}
        <section className="max-w-4xl mx-auto px-6 py-16">
          <h3 className="text-2xl font-bold text-zinc-200 text-center mb-8">{t('landing.loop')}</h3>
          <div className="flex flex-col gap-4">
            {[
              { step: '1', title: t('landing.step1'), desc: t('landing.step1Desc') },
              { step: '2', title: t('landing.step2'), desc: t('landing.step2Desc') },
              { step: '3', title: t('landing.step3'), desc: t('landing.step3Desc') },
              { step: '4', title: t('landing.step4'), desc: t('landing.step4Desc') },
              { step: '5', title: t('landing.step5'), desc: t('landing.step5Desc') },
              { step: '6', title: t('landing.step6'), desc: t('landing.step6Desc') },
            ].map((item) => (
              <div key={item.step} className="flex items-start gap-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
                <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white">
                  {item.step}
                </div>
                <div>
                  <h4 className="text-sm font-medium text-zinc-200">{item.title}</h4>
                  <p className="text-xs text-zinc-400 mt-1">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Tech Stack */}
        <section className="max-w-4xl mx-auto px-6 py-16 text-center">
          <h3 className="text-2xl font-bold text-zinc-200 mb-8">{t('landing.builtWith')}</h3>
          <div className="flex flex-wrap justify-center gap-3">
            {['Next.js 14', 'FastAPI', 'Supabase', 'pgvector', 'LiteLLM', 'Claude', 'Tailwind CSS', 'TypeScript', 'Python'].map((tech) => (
              <span key={tech} className="rounded-full border border-zinc-700 bg-zinc-800 px-4 py-1.5 text-xs text-zinc-300">
                {tech}
              </span>
            ))}
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-zinc-800 py-8 text-center">
        <p className="text-xs text-zinc-500">AI Trainer Platform v0.1.0 — Built with Claude Code</p>
      </footer>
    </div>
  )
}
