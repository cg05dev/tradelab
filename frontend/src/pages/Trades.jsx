import { useState, useRef, useCallback } from 'react'
import PlanTrade from './PlanTrade'
import OpenTrades from './OpenTrades'
import TradeHistory from './TradeHistory'
import Portfolio from './Portfolio'

export default function Trades() {
  const [subTab, setSubTab] = useState('plan')
  const [refreshKey, setRefreshKey] = useState(0)
  const openTradesRef = useRef(null)

  const handleTradeAdded = useCallback(() => {
    // Refresh open trades when a trade is added
    if (openTradesRef.current) {
      openTradesRef.current.loadTrades()
    } else {
      // If component not mounted, increment key to force refresh when it mounts
      setRefreshKey(prev => prev + 1)
    }
  }, [])

  const handleTabChange = (tab) => {
    setSubTab(tab)
    // Refresh open trades when switching to that tab
    if (tab === 'open') {
      // Small delay to ensure component is mounted
      setTimeout(() => {
        if (openTradesRef.current) {
          openTradesRef.current.loadTrades()
        }
      }, 100)
    }
  }

  const tabs = [
    { id: 'plan', label: 'Trade' },
    { id: 'open', label: 'Open Trades' },
    { id: 'history', label: 'Trade History' },
    { id: 'portfolio', label: 'Portfolio' },
  ]

  return (
    <div className="space-y-4">
      {/* Sub-tabs */}
      <div className="flex gap-1 border-b border-neutral-700">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleTabChange(tab.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
              subTab === tab.id
                ? 'border-white text-white'
                : 'border-transparent text-neutral-500 hover:text-neutral-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div>
        <div className={subTab === 'plan' ? 'block' : 'hidden'}>
          <PlanTrade onTradeAdded={handleTradeAdded} />
        </div>
        <div className={subTab === 'open' ? 'block' : 'hidden'}>
          <OpenTrades key={refreshKey} ref={openTradesRef} />
        </div>
        <div className={subTab === 'history' ? 'block' : 'hidden'}>
          <TradeHistory />
        </div>
        <div className={subTab === 'portfolio' ? 'block' : 'hidden'}>
          <Portfolio />
        </div>
      </div>
    </div>
  )
}
