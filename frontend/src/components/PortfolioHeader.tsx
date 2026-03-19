import { useMutation, useQuery } from '@tanstack/react-query'
import { getPortfolio, updatePortfolio } from '../api/portfolio'
import { getAnalyticsOverview } from '../api/analytics'
import { getErrorMessage } from '../api/error'
import type { AnalyticsOverview, PortfolioResponse } from '../types'

export default function PortfolioHeader() {
  const portfolioQuery = useQuery<PortfolioResponse>({
    queryKey: ['portfolio'],
    queryFn: async () => (await getPortfolio()).data ?? { portfolio_size: 0 },
  })

  const analyticsQuery = useQuery<AnalyticsOverview>({
    queryKey: ['analytics-overview'],
    queryFn: async () => (await getAnalyticsOverview()).data ?? { total_pnl: 0, win_rate: 0, profit_factor: 0 },
  })

  const updateMutation = useMutation({
    mutationFn: updatePortfolio,
    onSuccess: () => {
      void portfolioQuery.refetch()
      void analyticsQuery.refetch()
    },
  })

  const handleUpdatePortfolio = async (): Promise<void> => {
    const current = String(portfolioQuery.data?.portfolio_size ?? 0)
    const newSize = prompt('Enter new portfolio size:', current)
    if (!newSize || Number.isNaN(parseFloat(newSize))) return
    updateMutation.mutate(parseFloat(newSize))
  }

  if (portfolioQuery.isLoading || analyticsQuery.isLoading) {
    return (
      <div className="w-full py-6 flex items-center justify-center">
        <div className="animate-spin rounded-full h-4 w-4 border-t border-b border-neutral-500"></div>
      </div>
    )
  }

  if (portfolioQuery.isError || analyticsQuery.isError) {
    return (
      <div className="w-full py-6 text-center text-sm text-red-400">
        {getErrorMessage(portfolioQuery.error ?? analyticsQuery.error, 'Unable to load portfolio data')}
      </div>
    )
  }

  const portfolioSize = portfolioQuery.data?.portfolio_size || 0
  const totalPnL = analyticsQuery.data?.total_pnl || 0
  const winRate = analyticsQuery.data?.win_rate || 0
  const profitFactor = analyticsQuery.data?.profit_factor || 0

  return (
    <div className="w-full py-6">
      <div className="flex items-center gap-4">
        <button
          onClick={handleUpdatePortfolio}
          className="text-xl font-light text-white border border-transparent rounded-md px-2 py-1 -mx-2 -my-1 hover:text-neutral-200 hover:border-neutral-700 hover:bg-white/[0.03] hover:underline underline-offset-4 transition-colors cursor-pointer focus:outline-none focus-visible:border-green-500/50 focus-visible:bg-green-500/5"
        >
          ${portfolioSize.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </button>

        <div className="flex items-center gap-1 text-xs text-neutral-400">
          <span className="text-neutral-600">|</span>
          <div className="flex items-center gap-1 px-1.5">
            <span className="text-neutral-500">WR</span>
            <span className="text-neutral-300">{winRate.toFixed(0)}%</span>
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
            <span className="text-neutral-300">{profitFactor.toFixed(1)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
