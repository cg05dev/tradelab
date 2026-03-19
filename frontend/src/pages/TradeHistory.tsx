import { useQuery } from '@tanstack/react-query'
import { getClosedTrades } from '../api/trades'
import { getErrorMessage } from '../api/error'
import type { Trade } from '../types'

export default function TradeHistory() {
  const tradesQuery = useQuery<Trade[]>({
    queryKey: ['closed-trades'],
    queryFn: async () => (await getClosedTrades()).data?.trades || [],
  })

  if (tradesQuery.isLoading) {
    return (
      <div className="w-full py-4">
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full w-6 h-6 border-t-2 border-b-2 border-neutral-500"></div>
        </div>
      </div>
    )
  }

  if (tradesQuery.isError) {
    return (
      <div className="w-full py-4">
        <div className="text-center py-8 text-red-400 text-sm">{getErrorMessage(tradesQuery.error, 'Error loading trade history')}</div>
      </div>
    )
  }

  const trades = tradesQuery.data || []

  if (trades.length === 0) {
    return (
      <div className="w-full py-4">
        <div className="text-center py-8 text-neutral-500 text-sm">
          <p>No trade history yet</p>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-neutral-500">{trades.length} trades</span>
      </div>
      <div className="space-y-2 max-h-[200px] overflow-y-auto">
        {trades.slice(0, 10).map((trade: Trade, index: number) => (
          <div key={String(trade.id ?? index)} className="border border-neutral-700/30 rounded p-2 bg-black/30">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-medium text-white">{trade.Asset}</span>
                <span className={`text-xs px-1 py-0.5 rounded ${trade.Direction === 'long' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                  {(trade.Direction || 'unknown').toUpperCase()}
                </span>
              </div>
              <span className={`text-xs font-medium ${(trade['P&L'] || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {(trade['P&L'] || 0) >= 0 ? '+' : ''}${(trade['P&L'] || 0).toFixed(0)}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs text-neutral-400">
              <span>Entry: ${trade.Entry?.toFixed(0)}</span>
              <span>Exit: ${trade.Exit_Price?.toFixed(0)}</span>
            </div>
            <div className="text-xs text-neutral-500 mt-0.5">{trade.Date ? new Date(trade.Date).toLocaleDateString() : '-'}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
