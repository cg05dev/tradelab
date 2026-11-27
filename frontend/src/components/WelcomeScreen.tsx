import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { TrendingUp } from 'lucide-react'
import { updatePortfolio } from '../api/portfolio'
import { setMode } from '../api/mode'
import { getErrorMessage } from '../api/error'
import { MODE_STORAGE_KEY } from '../contexts/ModeContext'

// First run: connect a Hyperliquid account (the live portfolio then syncs from its balance), or
// start paper trading with a balance typed in here.
export default function WelcomeScreen({ onComplete }: { onComplete: () => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [portfolioSize, setPortfolioSize] = useState('')
  const [error, setError] = useState('')

  const startPaper = useMutation({
    mutationFn: async () => {
      const size = parseFloat(portfolioSize)
      if (!portfolioSize || Number.isNaN(size) || size <= 0) {
        throw new Error('Please enter a starting balance greater than 0')
      }
      await setMode('paper')
      window.localStorage.setItem(MODE_STORAGE_KEY, 'paper')
      return updatePortfolio(size, 'paper')
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['portfolio'] })
      onComplete()
    },
    onError: (err) => setError(getErrorMessage(err, 'Error setting the starting balance. Please try again.')),
  })

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-black topography-bg-paper">
      <div className="max-w-md w-full">
        <div className="border border-gray-700/60 rounded-xl p-8 bg-black/50 backdrop-blur-sm text-center" style={{ boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2)' }}>
          <div className="flex justify-center mb-5">
            <div className="w-14 h-14 bg-green-500/10 rounded-full flex items-center justify-center border border-green-500/20">
              <TrendingUp className="w-7 h-7 text-green-400" />
            </div>
          </div>

          <h1 className="text-xl font-semibold text-white mb-1.5 font-display">Welcome to TradeLab</h1>
          <p className="text-gray-400 text-xs mb-6">Plan risk-first trades, then journal and review them.</p>

          <button
            type="button"
            onClick={() => navigate({ to: '/settings' })}
            className="w-full px-4 py-2.5 bg-green-500/10 hover:bg-green-500/20 border border-green-500/30 text-green-400 rounded-lg transition-colors font-medium text-sm"
          >
            Connect your Hyperliquid account
          </button>
          <p className="text-xs text-gray-500 mt-2">Your live portfolio syncs from the account&apos;s balance.</p>

          <div className="my-6 flex items-center gap-3 text-xs text-gray-600">
            <span className="h-px flex-1 bg-gray-800" />or<span className="h-px flex-1 bg-gray-800" />
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              setError('')
              startPaper.mutate()
            }}
            className="space-y-3"
          >
            <label htmlFor="portfolio" className="block text-xs text-gray-500 text-left">
              Start paper trading with a balance of (USD)
            </label>
            <div className="flex gap-2">
              <input
                id="portfolio"
                type="number"
                step="0.01"
                min="0.01"
                value={portfolioSize}
                onChange={(e) => {
                  setPortfolioSize(e.target.value)
                  setError('')
                }}
                onWheel={(e) => (e.currentTarget as HTMLInputElement).blur()}
                placeholder="10,000"
                className="min-w-0 flex-1 px-3.5 py-2.5 bg-black/30 border border-gray-700/60 rounded-lg text-white text-sm placeholder-gray-600 focus:outline-none focus:border-indigo-400/50 focus:bg-black/40 transition-colors"
              />
              <button
                type="submit"
                disabled={startPaper.isPending}
                className="px-4 py-2.5 bg-indigo-400/[0.06] hover:bg-indigo-400/10 border border-indigo-400/30 text-indigo-300 rounded-lg transition-colors font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {startPaper.isPending ? 'Starting…' : 'Start'}
              </button>
            </div>
            {error && <p className="text-red-400 text-xs text-left">{error}</p>}
          </form>
        </div>
      </div>
    </div>
  )
}
