import type { ReactNode } from 'react'

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="h-screen bg-black topography-bg flex flex-col overflow-hidden">
      <header className="flex-shrink-0 border-b border-neutral-800 bg-black/80 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <h1 className="text-lg font-medium text-white tracking-tight">TradeLab</h1>
          </div>
        </div>
      </header>
      <main className="flex-1 overflow-y-auto w-full">{children}</main>
    </div>
  )
}
