import { useQuery } from '@tanstack/react-query'
import { getConnection } from '../api/connection'
import { useMode } from '../contexts/ModeContext'

export default function ModeToggle() {
  const { mode, toggleMode, isLoading } = useMode()
  // Live mode trades on whichever network the account is connected to; say so when it's testnet
  const connectionQuery = useQuery({ queryKey: ['connection'], queryFn: async () => (await getConnection()).data })
  const testnet = connectionQuery.data?.network === 'testnet' && Boolean(connectionQuery.data?.account_address)

  return (
    <button
      type="button"
      onClick={toggleMode}
      disabled={isLoading}
      className="inline-flex items-stretch overflow-hidden rounded-full border border-neutral-700/50 bg-black/30 p-1 backdrop-blur-sm disabled:opacity-50"
      aria-label="Toggle trading mode"
      aria-pressed={mode === 'live'}
      title={testnet ? 'Live mode trades on Hyperliquid testnet (test funds). Change the network in Settings.' : undefined}
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
            ? testnet ? 'bg-amber-400/15 text-amber-300' : 'bg-green-400/10 text-green-400'
            : 'text-neutral-500'
        }`}
      >
        {testnet ? 'Live · Testnet' : 'Live'}
      </span>
    </button>
  )
}
