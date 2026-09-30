import { useRef } from 'react'
import PlanTrade from './PlanTrade'
import OpenTrades from './OpenTrades'

export default function TradePage() {
  const openTradesRef = useRef<{ loadTrades: () => void }>(null)

  const handleTradeAdded = () => {
    openTradesRef.current?.loadTrades()
  }

  return (
    <div className="space-y-7">
      <PlanTrade onTradeAdded={handleTradeAdded} />
      <div className="rounded-xl border border-neutral-700/30 bg-gradient-to-b from-neutral-900/20 to-black/20 p-6 shadow-2xl shadow-black/20 backdrop-blur-sm md:p-7">
        <div className="mb-4">
          <h2 className="font-display text-base font-semibold text-white">Open trades</h2>
          <p className="mt-1 text-xs text-neutral-500">Live position performance and risk levels.</p>
        </div>
        <OpenTrades ref={openTradesRef} />
      </div>
    </div>
  )
}
