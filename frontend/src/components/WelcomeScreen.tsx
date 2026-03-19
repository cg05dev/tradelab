import { useState, type FormEvent } from 'react'
import { updatePortfolio } from '../api/portfolio'
import { TrendingUp } from 'lucide-react'
import type { ApiError } from '../types'

export default function WelcomeScreen({ onComplete }: { onComplete: () => void }) {
  const [portfolioSize, setPortfolioSize] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault()
    setError('')
    
    const size = parseFloat(portfolioSize)
    if (!portfolioSize || isNaN(size) || size <= 0) {
      setError('Please enter a valid portfolio size greater than 0')
      return
    }

    try {
      setLoading(true)
      await updatePortfolio(size)
      onComplete()
    } catch (err) {
      const error = err as ApiError
      setError(error.response?.data?.detail || 'Error setting portfolio size. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-black topography-bg">
      <div className="max-w-md w-full">
        <div className="border border-gray-700/60 rounded-xl p-8 bg-black/50 backdrop-blur-sm text-center" style={{ boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2)' }}>
          {/* Icon */}
          <div className="flex justify-center mb-5">
            <div className="w-14 h-14 bg-green-500/10 rounded-full flex items-center justify-center border border-green-500/20">
              <TrendingUp className="w-7 h-7 text-green-400" />
            </div>
          </div>

          {/* Title */}
          <h1 className="text-xl font-semibold text-white mb-1.5">Welcome to TradeLab</h1>
          <p className="text-gray-400 text-xs mb-6">
            Set up your portfolio to get started
          </p>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
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
              {error && (
                <p className="text-red-400 text-xs mt-1.5 text-left">{error}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full px-4 py-2.5 bg-green-500/10 hover:bg-green-500/20 border border-green-500/30 text-green-400 rounded-lg transition-colors font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Setting up...' : 'Get Started'}
            </button>
          </form>

          <p className="text-xs text-gray-500 mt-5">
            You can change this later in the Dashboard
          </p>
        </div>
      </div>
    </div>
  )
}

