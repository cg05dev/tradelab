import type { ReactNode } from 'react'

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="h-screen bg-black topography-bg flex flex-col overflow-hidden">
      <main className="flex-1 overflow-y-auto w-full">{children}</main>
    </div>
  )
}
