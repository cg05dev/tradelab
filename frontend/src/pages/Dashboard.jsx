import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { getPortfolio, updatePortfolio } from '../api/portfolio'
import { getAnalyticsOverview } from '../api/analytics'
import { getClosedTrades } from '../api/trades'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import PlanTrade from './PlanTrade'
import OpenTrades from './OpenTrades'
import TradeHistory from './TradeHistory'

const COLORS = ['#22c55e', '#ef4444', '#6b7280']

export default function Dashboard() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [portfolio, setPortfolio] = useState({ portfolio_size: 0 })
  const [analytics, setAnalytics] = useState(null)
  const [closedTrades, setClosedTrades] = useState([])
  const [showDetails, setShowDetails] = useState(false)
  const [newPortfolioSize, setNewPortfolioSize] = useState('')
  const [isUpdating, setIsUpdating] = useState(false)
  const openTradesRef = useRef(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [portfolioRes, analyticsRes, closedRes] = await Promise.all([
          getPortfolio(),
          getAnalyticsOverview(),
          getClosedTrades()
        ])
        setPortfolio(portfolioRes.data)
        setAnalytics(analyticsRes.data)
        setClosedTrades(closedRes.data?.trades || [])
      } catch (err) {
        console.error('Error fetching data:', err)
      }
    }
    fetchData()
  }, [refreshKey])

  const handleTradeAdded = useCallback(() => {
    if (openTradesRef.current) {
      openTradesRef.current.loadTrades()
    }
    setRefreshKey(prev => prev + 1)
  }, [])

  const handleUpdatePortfolio = async () => {
    const size = parseFloat(newPortfolioSize)
    if (!size || size <= 0) {
      alert('Please enter a valid portfolio size')
      return
    }
    
    setIsUpdating(true)
    try {
      await updatePortfolio(size)
      setPortfolio(prev => ({ ...prev, portfolio_size: size }))
      setNewPortfolioSize('')
      alert('Portfolio size updated successfully')
    } catch (err) {
      console.error('Error updating portfolio:', err)
      alert('Failed to update portfolio size')
    } finally {
      setIsUpdating(false)
    }
  }

  // Analytics data
  const totalPnL = analytics?.total_pnl || 0
  const totalTrades = analytics?.total_trades || 0
  const winRate = analytics?.win_rate || 0
  const openTradesCount = analytics?.open_trades || 0
  const winningTrades = analytics?.winning_trades || 0
  const losingTrades = analytics?.losing_trades || 0
  const profitFactor = analytics?.profit_factor || 0

  // Chart data preparation
  const pieData = useMemo(() => {
    if (totalTrades === 0) return []
    return [
      { name: 'Wins', value: winningTrades },
      { name: 'Losses', value: losingTrades }
    ].filter(item => item.value > 0)
  }, [winningTrades, losingTrades, totalTrades])

  const pnlChartData = useMemo(() => {
    if (closedTrades.length < 2) return []
    const sorted = [...closedTrades].sort((a, b) => new Date(a.exit_date || a.Date) - new Date(b.exit_date || b.Date))
    let cumulative = 0
    return sorted.map((trade, index) => {
      cumulative += trade['P&L'] || trade.actual_profit_loss || 0
      return {
        name: `T${index + 1}`,
        pnl: cumulative,
        trade: trade
      }
    })
  }, [closedTrades])

  const hasEnoughDataForCharts = totalTrades >= 3

  // Main Dashboard View
  if (!showDetails) {
    return (
      <div className="max-w-7xl mx-auto py-8 px-6 space-y-6">
        
        {/* Portfolio Summary */}
        <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-4 shadow-2xl shadow-black/20 w-full">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-lg font-medium text-white font-display">Portfolio</h2>
            <button
              onClick={() => setShowDetails(true)}
              className="text-xs text-neutral-400 hover:text-white transition-colors px-3 py-1 border border-neutral-700 rounded hover:border-neutral-500"
            >
              Details
            </button>
          </div>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 w-full">
            <div>
              <p className="text-xs text-neutral-500 mb-1">Portfolio Size</p>
              <p className="text-2xl font-light text-white">
                ${portfolio.portfolio_size?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}
              </p>
            </div>
            <div>
              <p className="text-xs text-neutral-500 mb-1">Total P&L</p>
              <p className={`text-2xl font-light ${totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {totalPnL >= 0 ? '+' : ''}${totalPnL.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
            </div>
            <div>
              <p className="text-xs text-neutral-500 mb-1">Win Rate</p>
              <p className="text-2xl font-light text-white">{winRate.toFixed(1)}%</p>
              <p className="text-xs text-neutral-600">{winningTrades}/{losingTrades} trades</p>
            </div>
            <div>
              <p className="text-xs text-neutral-500 mb-1">Open Trades</p>
              <p className="text-2xl font-light text-white">{openTradesCount}</p>
              <p className="text-xs text-neutral-600">Active positions</p>
            </div>
          </div>
        </div>

        {/* Main Layout: PlanTrade + OpenTrades */}
        <div className="space-y-6">
          
          {/* Plan Trade Section */}
          <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
            <PlanTrade onTradeAdded={handleTradeAdded} />
          </div>

          {/* Open Trades Section - Full Width */}
          <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
            <OpenTrades key={refreshKey} ref={openTradesRef} />
          </div>

          {/* Trade History Section - Full Width */}
          <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
            <TradeHistory />
          </div>
          
        </div>
        
      </div>
    )
  }

  // Portfolio Details View
  return (
    <div className="max-w-7xl mx-auto py-8 px-6">
      <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
        
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowDetails(false)}
              className="flex items-center gap-2 text-neutral-400 hover:text-white transition-colors px-3 py-2 border border-neutral-700 rounded hover:border-neutral-500"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m15 18-6-6 6-6"/>
              </svg>
              <span className="text-sm">Back</span>
            </button>
            <h2 className="text-xl font-medium text-white">Portfolio Analytics</h2>
          </div>
        </div>

        <div className="space-y-6">
          
          {/* Top Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="border border-neutral-800 rounded-xl p-5">
              <p className="text-xs text-neutral-500 mb-2 uppercase tracking-wider">Portfolio Size</p>
              <p className="text-3xl font-light text-white">
                ${portfolio.portfolio_size?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}
              </p>
            </div>
            <div className="border border-neutral-800 rounded-xl p-5">
              <p className="text-xs text-neutral-500 mb-2 uppercase tracking-wider">Total P&L</p>
              <p className={`text-3xl font-light ${totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {totalPnL >= 0 ? '+' : ''}${totalPnL.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
            </div>
            <div className="border border-neutral-800 rounded-xl p-5">
              <p className="text-xs text-neutral-500 mb-2 uppercase tracking-wider">Total Trades</p>
              <p className="text-3xl font-light text-white">{totalTrades}</p>
            </div>
            <div className="border border-neutral-800 rounded-xl p-5">
              <p className="text-xs text-neutral-500 mb-2 uppercase tracking-wider">Profit Factor</p>
              <p className={`text-3xl font-light ${profitFactor >= 1 ? 'text-green-400' : 'text-red-400'}`}>
                {profitFactor.toFixed(2)}
              </p>
            </div>
          </div>

          {/* Charts */}
          {hasEnoughDataForCharts && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="border border-neutral-800 rounded-xl p-5">
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={pnlChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="name" stroke="#52525b" fontSize={10} />
                      <YAxis stroke="#52525b" fontSize={10} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#18181b', border: '1px solid #3f3f46', borderRadius: '6px' }}
                        itemStyle={{ color: '#fff' }}
                      />
                      <Line type="monotone" dataKey="pnl" stroke="#3b82f6" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {pieData.length > 0 && (
                <div className="border border-neutral-800 rounded-xl p-5">
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={pieData}
                          cx="50%"
                          cy="50%"
                          innerRadius={60}
                          outerRadius={80}
                          paddingAngle={5}
                          dataKey="value"
                        >
                          {pieData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip 
                          contentStyle={{ backgroundColor: '#18181b', border: '1px solid #3f3f46', borderRadius: '6px' }}
                          itemStyle={{ color: '#fff' }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* More Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="border border-neutral-800 rounded-lg p-4">
              <p className="text-xs text-neutral-500 mb-1">Win Rate</p>
              <p className="text-2xl font-light text-white">{winRate.toFixed(1)}%</p>
            </div>
            <div className="border border-neutral-800 rounded-lg p-4">
              <p className="text-xs text-neutral-500 mb-1">Winning Trades</p>
              <p className="text-2xl font-light text-green-400">{winningTrades}</p>
            </div>
            <div className="border border-neutral-800 rounded-lg p-4">
              <p className="text-xs text-neutral-500 mb-1">Losing Trades</p>
              <p className="text-2xl font-light text-red-400">{losingTrades}</p>
            </div>
            <div className="border border-neutral-800 rounded-lg p-4">
              <p className="text-xs text-neutral-500 mb-1">Open Positions</p>
              <p className="text-2xl font-light text-white">{openTradesCount}</p>
            </div>
          </div>

          {/* Update Portfolio */}
          <div className="border border-neutral-800 rounded-xl p-6">
            <p className="text-sm text-neutral-400 mb-4">Update Portfolio Size</p>
            <div className="flex gap-3 max-w-md">
              <input
                type="number"
                value={newPortfolioSize}
                onChange={(e) => setNewPortfolioSize(e.target.value)}
                placeholder="Enter new size..."
                step="0.01"
                className="flex-1 px-4 py-3 bg-neutral-900 border border-neutral-700 rounded-lg text-white text-sm focus:outline-none focus:border-neutral-500 transition-colors"
              />
              <button
                onClick={handleUpdatePortfolio}
                disabled={isUpdating || !newPortfolioSize}
                className="px-6 py-3 bg-neutral-800 text-white text-sm rounded-lg hover:bg-neutral-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isUpdating ? 'Updating...' : 'Update'}
              </button>
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}
