import { useMode } from '../contexts/ModeContext'

export default function ModeToggle() {
  const { mode, toggleMode, isLoading } = useMode()

  return (
    <button
      type="button"
      onClick={toggleMode}
      disabled={isLoading}
      className="inline-flex items-stretch overflow-hidden rounded-full border border-neutral-700/50 bg-black/30 p-1 backdrop-blur-sm disabled:opacity-50"
      aria-label="Toggle trading mode"
      aria-pressed={mode === 'live'}
    >
      <span
        className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
          mode === 'paper'
            ? 'bg-indigo-400/10 text-indigo-300'
            : 'text-neutral-500'
        }`}
      >
        Paper
      </span>
      <span
        className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
          mode === 'live'
            ? 'bg-green-400/10 text-green-400'
            : 'text-neutral-500'
        }`}
      >
        Live
      </span>
    </button>
  )
}
