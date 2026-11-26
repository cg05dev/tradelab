import { useMutation, useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { getPortfolio, updatePortfolio } from '../api/portfolio'
import { getAnalyticsOverview } from '../api/analytics'
import { getOpenTrades } from '../api/trades'
import { getHyperliquidPrice } from '../api/hyperliquid'
import { getErrorMessage } from '../api/error'
import { useMode } from '../contexts/ModeContext'
import { useEffect, useState } from 'react'
import type { AnalyticsOverview, PortfolioResponse, Trade } from '../types'

export default function PortfolioHeader() {
  const { mode } = useMode()
  const [currentPrices, setCurrentPrices] = useState<Record<string, number>>({})

  const portfolioQuery = useQuery<PortfolioResponse>({
    queryKey: ['portfolio', mode],
    queryFn: async () => (await getPortfolio(mode)).data ?? { portfolio_size: 0 },
    refetchInterval: mode === 'live' ? 10_000 : false, // the live balance tracks the Hyperliquid account
  })

  const analyticsQuery = useQuery<AnalyticsOverview>({
    queryKey: ['analytics-overview', mode],
    queryFn: async () => (await getAnalyticsOverview(mode)).data ?? { total_pnl: 0, win_rate: 0, profit_factor: 0 },
    refetchInterval: 3000, // Refresh analytics every 3 seconds
  })

  const openTradesQuery = useQuery<{ trades: Trade[] }>({
    queryKey: ['open-trades-portfolio', mode],
    queryFn: async () => (await getOpenTrades(mode)).data ?? { trades: [] },
    refetchInterval: 5000, // Refresh trades every 5 seconds
  })

  // Fetch current prices for open trades
  useEffect(() => {
    const trades = openTradesQuery.data?.trades || []
    if (trades.length === 0) return

    const fetchPrices = async () => {
      const prices: Record<string, number> = {}
      const uniqueAssets = [...new Set(trades.map((t: Trade) => t.Asset).filter((asset): asset is string => Boolean(asset)))] as string[]
      
      await Promise.all(
        uniqueAssets.map(async (asset: string) => {
          try {
            const coin = asset.split('-')[0] ?? ''
            const res = await getHyperliquidPrice(coin)
            if (res.data?.price) {
              prices[asset] = res.data.price
            }
          } catch (error) {
            console.error(`Error fetching price for ${asset}:`, error)
          }
        })
      )
      
      setCurrentPrices(prices)
    }

    fetchPrices()
    
    // Poll prices every 670ms
    const interval = setInterval(fetchPrices, 670)
    return () => clearInterval(interval)
  }, [openTradesQuery.data?.trades])

  // Calculate total unrealized PnL from open trades
  const totalUnrealizedPnL = (() => {
    const trades = openTradesQuery.data?.trades || []
    let total = 0
    
    for (const trade of trades) {
      const asset = trade.Asset ?? ''
      const currentPrice = asset ? currentPrices[asset] : undefined
      if (!currentPrice || !trade.Entry) continue
      
      const entry = typeof trade.Entry === 'number' ? trade.Entry : parseFloat(String(trade.Entry ?? 0))
      const positionSize = typeof trade.Position_Size === 'number' ? trade.Position_Size : parseFloat(String(trade.Position_Size ?? 0)) || 0
      
      if (trade.Direction?.toLowerCase() === 'long') {
        total += (currentPrice - entry) * (positionSize / entry)
      } else {
        total += (entry - currentPrice) * (positionSize / entry)
      }
    }
    
    return total
  })()

  const updateMutation = useMutation({
    mutationFn: ({ portfolioSize, mode }: { portfolioSize: number; mode?: string }) => updatePortfolio(portfolioSize, mode),
    onSuccess: () => {
      void portfolioQuery.refetch()
      void analyticsQuery.refetch()
    },
  })

  // Paper's balance is typed in; live's is always the Hyperliquid account value
  const synced = portfolioQuery.data?.source === 'hyperliquid'
  const editable = mode === 'paper'

  const handleUpdatePortfolio = async (): Promise<void> => {
    if (!editable) return
    const current = String(portfolioQuery.data?.portfolio_size ?? 0)
    const newSize = prompt('Enter new portfolio size:', current)
    if (!newSize || Number.isNaN(parseFloat(newSize))) return
    updateMutation.mutate({ portfolioSize: parseFloat(newSize), mode })
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

  const portfolioSize = portfolioQuery.data?.portfolio_size ?? 0
  const balanceKnown = portfolioQuery.data?.portfolio_size != null
  const totalPnL = analyticsQuery.data?.total_pnl || 0
  const winRate = analyticsQuery.data?.win_rate || 0
  const profitFactor = analyticsQuery.data?.profit_factor || 0
  
  // A synced Hyperliquid account value already includes unrealized P&L; a manual size doesn't
  const portfolioWithUnrealized = synced ? portfolioSize : portfolioSize + totalUnrealizedPnL

  return (
    <div className="w-full rounded-xl border border-white/[0.06] bg-black/10 px-5 py-4 backdrop-blur-sm">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        {portfolioQuery.data?.source === 'none' ? (
          <Link
            to="/settings"
            className="rounded-lg border border-green-400/30 bg-green-400/10 px-3 py-2 text-sm font-medium text-green-400 hover:bg-green-400/15"
          >
            Connect your Hyperliquid account →
          </Link>
        ) : !balanceKnown ? (
          <span className="font-display text-2xl font-medium text-neutral-500" title={portfolioQuery.data?.sync_error}>
            Unavailable
          </span>
        ) : (
          <button
            onClick={handleUpdatePortfolio}
            disabled={!editable}
            className="rounded-md border border-transparent px-2 py-1 -mx-2 -my-1 font-display text-2xl font-medium tabular-nums text-white enabled:hover:border-neutral-700 enabled:hover:bg-white/[0.03] enabled:hover:text-neutral-200 focus:outline-none focus-visible:border-green-500/50 focus-visible:bg-green-500/5"
            title={editable ? 'Edit paper balance' : 'Your Hyperliquid account value'}
          >
            ${portfolioWithUnrealized.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </button>
        )}

        {synced && !balanceKnown && (
          <span className="text-xs text-amber-300">{portfolioQuery.data?.sync_error}</span>
        )}

        {synced && balanceKnown && (
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${portfolioQuery.data?.stale ? 'bg-amber-400/10 text-amber-300' : 'bg-green-400/10 text-green-400/80'}`}
            title={portfolioQuery.data?.stale ? "Couldn't reach Hyperliquid; showing the last value fetched" : 'Live account value from Hyperliquid'}
          >
            {portfolioQuery.data?.stale ? 'Stale' : 'Synced'}
          </span>
        )}

        {totalUnrealizedPnL !== 0 && (
          <span className={`text-xs ${totalUnrealizedPnL >= 0 ? 'text-green-400/60' : 'text-red-400/60'}`}>
            ({synced ? 'incl. ' : ''}{totalUnrealizedPnL >= 0 ? '+' : ''}${totalUnrealizedPnL.toFixed(2)} unrealized)
          </span>
        )}

        <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-400">
          <div className="rounded-md border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5" title="Percentage of closed trades that were profitable">
            <span className="mr-1.5 text-neutral-500">Win rate</span>
            <span className="tabular-nums text-neutral-200">{winRate.toFixed(0)}%</span>
          </div>
          <div className="rounded-md border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5" title="Realized profit and loss">
            <span className="mr-1.5 text-neutral-500">Realized P&amp;L</span>
            <span className={`tabular-nums ${totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {totalPnL >= 0 ? '+' : ''}${totalPnL.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            </span>
          </div>
          <div className="rounded-md border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5" title="Gross profits divided by gross losses">
            <span className="mr-1.5 text-neutral-500">Profit factor</span>
            <span className="tabular-nums text-neutral-200">{profitFactor > 0 ? profitFactor.toFixed(1) : '—'}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
