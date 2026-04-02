import Link from 'next/link'

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Hero */}
      <header className="border-b border-zinc-800">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <h1 className="text-xl font-bold text-zinc-100">AI Trainer</h1>
          <Link
            href="/chat"
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
          >
            Open Dashboard
          </Link>
        </div>
      </header>

      <main>
        {/* Hero Section */}
        <section className="max-w-6xl mx-auto px-6 py-24 text-center">
          <div className="inline-block rounded-full bg-blue-500/10 border border-blue-500/20 px-4 py-1 text-xs text-blue-400 mb-6">
            Conversational AI Agent Training Platform
          </div>
          <h2 className="text-5xl font-bold text-zinc-100 leading-tight">
            Train Your AI Agent<br />
            <span className="text-blue-400">Through Conversation</span>
          </h2>
          <p className="mt-6 text-lg text-zinc-400 max-w-2xl mx-auto">
            Non-technical users can train domain-specific AI agents that can chat, interact with widgets, call APIs, and execute multi-step workflows — all through natural conversation.
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
            <Link
              href="/chat"
              className="rounded-lg bg-blue-600 px-8 py-3 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
            >
              Start Training
            </Link>
            <Link
              href="/settings"
              className="rounded-lg border border-zinc-700 px-8 py-3 text-sm font-medium text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              View Settings
            </Link>
          </div>
        </section>

        {/* Features Grid */}
        <section className="max-w-6xl mx-auto px-6 py-16">
          <h3 className="text-2xl font-bold text-zinc-200 text-center mb-12">Everything You Need</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[
              {
                icon: '💬',
                title: 'Training Chat',
                desc: 'Conversational interface with streaming responses. Teach your AI through dialogue with instant feedback.',
                href: '/chat',
              },
              {
                icon: '📚',
                title: 'Knowledge Base',
                desc: 'Upload documents for RAG-powered responses. Automatic chunking and vector search.',
                href: '/knowledge',
              },
              {
                icon: '✏️',
                title: 'Prompt Studio',
                desc: 'Version-controlled system prompts with auto-optimization suggestions based on user feedback.',
                href: '/prompts',
              },
              {
                icon: '📊',
                title: 'Eval Engine',
                desc: 'Create test cases and run automated evaluations with LLM-powered scoring.',
                href: '/eval',
              },
              {
                icon: '🔧',
                title: 'Tool Registry',
                desc: 'Register external APIs, webhooks, and MCP servers for your agent to use.',
                href: '/tools',
              },
              {
                icon: '⚡',
                title: 'Workflows',
                desc: 'Build multi-step automated processes with branching logic and error handling.',
                href: '/workflows',
              },
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
          <h3 className="text-2xl font-bold text-zinc-200 text-center mb-8">The Training Loop</h3>
          <div className="flex flex-col gap-4">
            {[
              { step: '1', title: 'Guided Interview', desc: 'AI asks questions to establish your domain baseline' },
              { step: '2', title: 'Free Training', desc: 'Chat freely — paste data, write rules, give examples' },
              { step: '3', title: 'Feedback & Scoring', desc: 'Rate AI responses as correct, partial, or wrong with corrections' },
              { step: '4', title: 'Auto-Optimize', desc: 'System generates prompt improvement suggestions from feedback' },
              { step: '5', title: 'Evaluate & Test', desc: 'Run test cases to verify improvements with regression detection' },
              { step: '6', title: 'Iterate', desc: 'Continuous improvement — each cycle makes your AI smarter' },
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
          <h3 className="text-2xl font-bold text-zinc-200 mb-8">Built With</h3>
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
