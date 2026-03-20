import type { ReactNode } from 'react'
import { useMode } from '../contexts/ModeContext'

export default function Layout({ children }: { children: ReactNode }) {
  const { mode } = useMode()
  
  return (
    <div className={`h-screen bg-black flex flex-col overflow-hidden transition-all duration-1000 ${mode === 'paper' ? 'topography-bg-paper' : 'topography-bg-live'}`}>
      <main className="flex-1 overflow-y-auto w-full">{children}</main>
    </div>
  )
}
