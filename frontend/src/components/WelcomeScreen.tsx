import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { TrendingUp } from 'lucide-react'
import { updatePortfolio } from '../api/portfolio'
import { getErrorMessage } from '../api/error'

export default function WelcomeScreen({ onComplete }: { onComplete: () => void }) {
  const queryClient = useQueryClient()
  const [portfolioSize, setPortfolioSize] = useState('')
  const [error, setError] = useState('')

  const submitMutation = useMutation({
    mutationFn: async () => {
      const size = parseFloat(portfolioSize)
      if (!portfolioSize || Number.isNaN(size) || size <= 0) {
        throw new Error('Please enter a valid portfolio size greater than 0')
      }
      return updatePortfolio(size)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['portfolio'] })
      onComplete()
    },
    onError: (err) => setError(getErrorMessage(err, 'Error setting portfolio size. Please try again.')),
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

          <h1 className="text-xl font-semibold text-white mb-1.5">Welcome to TradeLab</h1>
          <p className="text-gray-400 text-xs mb-6">Set up your portfolio to get started</p>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              setError('')
              submitMutation.mutate()
            }}
            className="space-y-4"
          >
            <div>
              <label htmlFor="portfolio" className="block text-xs text-gray-500 mb-1.5 text-left">
                Portfolio Size (USD)
              </label>
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
                placeholder="0.00"
                className="w-full px-3.5 py-2.5 bg-black/30 border border-gray-700/60 rounded-lg text-white text-sm placeholder-gray-600 focus:outline-none focus:border-green-500/50 focus:bg-black/40 transition-colors"
                autoFocus
              />
              {(error || submitMutation.error) && (
                <p className="text-red-400 text-xs mt-1.5 text-left">{error || getErrorMessage(submitMutation.error)}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={submitMutation.isPending}
              className="w-full px-4 py-2.5 bg-green-500/10 hover:bg-green-500/20 border border-green-500/30 text-green-400 rounded-lg transition-colors font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitMutation.isPending ? 'Setting up...' : 'Get Started'}
            </button>
          </form>

          <p className="text-xs text-gray-500 mt-5">You can change this later in the Dashboard</p>
        </div>
      </div>
    </div>
  )
}
