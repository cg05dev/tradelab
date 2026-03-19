import { useRef } from 'react'
import PlanTrade from './PlanTrade'
import OpenTrades from './OpenTrades'

export default function TradePage() {
  const openTradesRef = useRef<{ loadTrades: () => void }>(null)

  const handleTradeAdded = () => {
    openTradesRef.current?.loadTrades()
  }

  return (
    <div className="space-y-6">
      <PlanTrade onTradeAdded={handleTradeAdded} />
      <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
        <h2 className="text-sm font-medium text-neutral-400 mb-4">Open Trades</h2>
        <OpenTrades ref={openTradesRef} />
      </div>
    </div>
  )
}
