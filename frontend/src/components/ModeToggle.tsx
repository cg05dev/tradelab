import { useMode, type UITradingMode } from '../contexts/ModeContext'

export default function ModeToggle() {
  const { mode, toggleMode, isLoading } = useMode()

  return (
    <button
      type="button"
      onClick={toggleMode}
      disabled={isLoading}
      className="inline-flex items-stretch overflow-hidden rounded-full border border-neutral-700/30 bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm disabled:opacity-50"
      aria-label="Toggle trading mode"
    >
      <span
        className={`px-3 py-1 text-xs font-semibold transition-colors border-r border-neutral-700/30 ${
          mode === 'paper'
            ? 'text-indigo-400'
            : 'text-neutral-500'
        }`}
      >
        Paper
      </span>
      <span
        className={`px-3 py-1 text-xs font-semibold transition-colors ${
          mode === 'live'
            ? 'text-green-400'
            : 'text-neutral-500'
        }`}
      >
        Live
      </span>
    </button>
  )
}
