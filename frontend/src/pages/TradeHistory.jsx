import { useState, useEffect } from 'react'
import { getClosedTrades } from '../api/trades'

export default function TradeHistory() {
  const [trades, setTrades] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadTradeHistory()
  }, [])

  const loadTradeHistory = async () => {
    try {
      setLoading(true)
      const res = await getClosedTrades()
      setTrades(res.data?.trades || [])
    } catch (error) {
      console.error('Error loading trade history:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto py-12 px-6">
        <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-8 shadow-2xl shadow-black/20">
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-neutral-500"></div>
          </div>
        </div>
      </div>
    )
  }

  if (trades.length === 0) {
    return (
      <div className="max-w-3xl mx-auto py-12 px-6">
        <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-8 shadow-2xl shadow-black/20">
          <div className="text-center py-8 text-neutral-500">
            <p>No trade history yet</p>
            <p className="text-sm mt-1">Completed trades will appear here</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto py-12 px-6">
      <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-8 shadow-2xl shadow-black/20">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-neutral-400">Trade History</h2>
            <span className="text-xs text-neutral-500">{trades.length} trades</span>
          </div>
          
          <div className="space-y-2">
            {trades.map((trade) => (
              <div key={trade.id} className="border border-neutral-700/30 rounded p-3 bg-black/30">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-white">{trade.asset}</span>
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      trade.direction === 'long' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'
                    }`}>
                      {trade.direction.toUpperCase()}
                    </span>
                  </div>
                  <span className={`text-sm font-medium ${
                    (trade.actual_profit_loss || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {(trade.actual_profit_loss || 0) >= 0 ? '+' : ''}
                    ${(trade.actual_profit_loss || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </div>
                
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div>
                    <p className="text-neutral-500">Entry</p>
                    <p className="text-white">${trade.entry_price?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
                  </div>
                  <div>
                    <p className="text-neutral-500">Exit</p>
                    <p className="text-white">${trade.exit_price?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
                  </div>
                  <div>
                    <p className="text-neutral-500">Closed</p>
                    <p className="text-neutral-400">{new Date(trade.exit_date).toLocaleDateString()}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
