import { useState, useEffect, useRef, type RefObject } from 'react'
import Layout from './components/Layout'
import PlanTrade from './pages/PlanTrade'
import OpenTrades from './pages/OpenTrades'
import PortfolioHeader from './components/PortfolioHeader'
import WelcomeScreen from './components/WelcomeScreen'
import { getPortfolio } from './api/portfolio'

function App() {
  const [showWelcome, setShowWelcome] = useState(false)
  const [checkingPortfolio, setCheckingPortfolio] = useState(true)
  const openTradesRef = useRef<{ loadTrades: () => void } | null>(null)

  useEffect(() => {
    checkPortfolio()
  }, [])

  const checkPortfolio = async (): Promise<void> => {
    try {
      const res = await getPortfolio()
      const portfolioSize = res.data?.portfolio_size || 0
      setShowWelcome(portfolioSize === 0 || !portfolioSize)
    } catch (error) {
      console.error('Error checking portfolio:', error)
      setShowWelcome(true)
    } finally {
      setCheckingPortfolio(false)
    }
  }

  const handleWelcomeComplete = (): void => {
    setShowWelcome(false)
  }

  const handleTradeAdded = (): void => {
    // Refresh open trades when a new trade is added
    if (openTradesRef.current) {
      openTradesRef.current.loadTrades()
    }
  }

  if (checkingPortfolio) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-green-500"></div>
      </div>
    )
  }

  if (showWelcome) {
    return <WelcomeScreen onComplete={handleWelcomeComplete} />
  }

  return (
    <Layout>
      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Top: Portfolio Header */}
        <PortfolioHeader />

        {/* Bottom: Single Column Layout */}
        <div className="space-y-6">
          {/* Trade Planning */}
          <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
            <PlanTrade onTradeAdded={handleTradeAdded} />
          </div>

          {/* Open Trades - Full Width */}
          <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
            <h2 className="text-sm font-medium text-neutral-400 mb-4">Open Trades</h2>
            <OpenTrades ref={openTradesRef} />
          </div>
        </div>
      </div>
    </Layout>
  )
}

export default App
