/**
 * Embed Layout — minimal wrapper for iframe-embeddable pages.
 * No AuthProvider, no I18nProvider, no dashboard chrome.
 */
export default function EmbedLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-screen w-screen overflow-hidden">
      {children}
    </div>
  )
}
