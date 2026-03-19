import { useState, useEffect, useCallback, type ChangeEvent, type FormEvent } from 'react'
import { getPortfolio } from '../api/portfolio'
import { getAnalyticsOverview } from '../api/analytics'
import type { AnalyticsOverview, PortfolioResponse } from '../types'

export default function PortfolioHeader() {
  const [portfolio, setPortfolio] = useState<PortfolioResponse>({ portfolio_size: 0 })
  const [analytics, setAnalytics] = useState<AnalyticsOverview | null>(null)
  const [loading, setLoading] = useState(true)

  const loadData = useCallback(async (): Promise<void> => {
    try {
      setLoading(true)
      const [portfolioRes, analyticsRes] = await Promise.all([
        getPortfolio(),
        getAnalyticsOverview()
      ])
      setPortfolio(portfolioRes.data ?? { portfolio_size: 0 })
      setAnalytics(analyticsRes.data ?? null)
    } catch (error) {
      console.error('Error loading portfolio data:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 30000)
    return () => clearInterval(interval)
  }, [loadData])

  const handleUpdatePortfolio = async (): Promise<void> => {
    const newSize = prompt('Enter new portfolio size:', String(portfolio.portfolio_size))
    if (newSize && !isNaN(parseFloat(newSize))) {
      try {
        const { updatePortfolio } = await import('../api/portfolio')
        await updatePortfolio(parseFloat(newSize))
        await loadData()
      } catch (error) {
        console.error('Error updating portfolio:', error)
      }
    }
  }

  const portfolioSize = portfolio.portfolio_size || 0
  const totalPnL = analytics?.total_pnl || 0
  const winRate = analytics?.win_rate || 0
  const profitFactor = analytics?.profit_factor || 0

  if (loading) {
    return (
      <div className="w-full py-6 flex items-center justify-center">
        <div className="animate-spin rounded-full h-4 w-4 border-t border-b border-neutral-500"></div>
      </div>
    )
  }

  return (
    <div className="w-full py-6">
      <div className="flex items-center gap-4">
        {/* Portfolio Value */}
        <button 
          onClick={handleUpdatePortfolio}
          className="text-xl font-light text-white hover:text-neutral-300 transition-colors cursor-pointer"
        >
          ${portfolioSize.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </button>

        {/* Compact Stats Row */}
        <div className="flex items-center gap-1 text-xs text-neutral-400">
          <span className="text-neutral-600">|</span>
          
          <div className="flex items-center gap-1 px-1.5">
            <span className="text-neutral-500">WR</span>
            <span className={winRate >= 50 ? 'text-neutral-300' : 'text-neutral-300'}>
              {winRate.toFixed(0)}%
            </span>
          </div>

          <span className="text-neutral-600">|</span>

          <div className="flex items-center gap-1 px-1.5">
            <span className="text-neutral-500">P&L</span>
            <span className={totalPnL >= 0 ? 'text-green-400/70' : 'text-red-400/70'}>
              {totalPnL >= 0 ? '+' : ''}${totalPnL.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            </span>
          </div>

          <span className="text-neutral-600">|</span>

          <div className="flex items-center gap-1 px-1.5">
            <span className="text-neutral-500">PF</span>
            <span className={profitFactor >= 1 ? 'text-neutral-300' : 'text-neutral-300'}>
              {profitFactor.toFixed(1)}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
