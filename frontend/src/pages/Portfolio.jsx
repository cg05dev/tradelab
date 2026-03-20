import { useState, useEffect, useCallback, useMemo } from 'react'
import { getPortfolio, updatePortfolio } from '../api/portfolio'
import { getAnalyticsOverview } from '../api/analytics'
import { LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

const COLORS = ['#10b981', '#ef4444', '#6b7280']

export default function Portfolio() {
  const [portfolio, setPortfolio] = useState({ portfolio_size: 0 })
  const [analytics, setAnalytics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [pnlTimeframe, setPnlTimeframe] = useState('daily')

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const [portfolioRes, analyticsRes] = await Promise.all([
        getPortfolio(),
        getAnalyticsOverview()
      ])
      setPortfolio(portfolioRes.data)
      setAnalytics(analyticsRes.data)
    } catch (error) {
      console.error('Error loading portfolio data:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const totalPnL = analytics?.total_pnl || 0
  const winRate = analytics?.win_rate || 0
  const totalTrades = analytics?.total_trades || 0

  // Win/Loss data for pie chart
  const pieData = useMemo(() => {
    const wins = analytics?.winning_trades || 0
    const losses = analytics?.losing_trades || 0
    const data = [
      { name: 'Wins', value: wins },
      { name: 'Losses', value: losses }
    ].filter(item => item.value > 0)
    return data
  }, [analytics])

  // P&L chart data (simplified)
  const pnlData = useMemo(() => {
    if (!analytics?.daily_pnl) return []
    return analytics.daily_pnl.map(item => ({
      date: item.date,
      pnl: item.pnl
    }))
  }, [analytics])

  const handleUpdatePortfolio = async () => {
    const newSize = prompt('Enter new portfolio size:', portfolio.portfolio_size)
    if (newSize && !isNaN(parseFloat(newSize))) {
      try {
        await updatePortfolio(parseFloat(newSize))
        await loadData()
      } catch (error) {
        console.error('Error updating portfolio:', error)
      }
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

  return (
    <div className="max-w-3xl mx-auto py-12 px-6">
      <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-8 shadow-2xl shadow-black/20">
        <div className="space-y-4">
      {/* Portfolio Value */}
      <div className="border border-neutral-700/30 rounded-lg p-4 bg-black/30">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-neutral-500 mb-1">Portfolio Value</p>
            <p className="text-3xl font-bold text-white">
              ${portfolio.portfolio_size?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}
            </p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className={`text-lg font-medium ${totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {totalPnL >= 0 ? '+' : ''}${totalPnL.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span className="text-xs text-neutral-500">Total P&L</span>
            </div>
          </div>
          <button
            onClick={handleUpdatePortfolio}
            className="px-3 py-1.5 text-xs bg-black/50 text-neutral-400 border border-neutral-700 rounded hover:bg-black/70 hover:text-white transition-colors"
          >
            Update Size
          </button>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-3 gap-3">
        <div className="border border-neutral-700/30 rounded-lg p-3 bg-black/30">
          <p className="text-xs text-neutral-500 mb-1">Win Rate</p>
          <p className={`text-xl font-bold ${winRate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
            {winRate.toFixed(1)}%
          </p>
          <p className="text-xs text-neutral-500 mt-1">{analytics?.winning_trades || 0}/{totalTrades} trades</p>
        </div>
        <div className="border border-neutral-700/30 rounded-lg p-3 bg-black/30">
          <p className="text-xs text-neutral-500 mb-1">Profit Factor</p>
          <p className={`text-xl font-bold ${(analytics?.profit_factor || 0) >= 1 ? 'text-green-400' : 'text-red-400'}`}>
            {(analytics?.profit_factor || 0).toFixed(2)}
          </p>
        </div>
        <div className="border border-neutral-700/30 rounded-lg p-3 bg-black/30">
          <p className="text-xs text-neutral-500 mb-1">Total Trades</p>
          <p className="text-xl font-bold text-white">{totalTrades}</p>
        </div>
      </div>

      {/* Charts */}
      {pieData.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Win/Loss Pie Chart */}
          <div className="border border-neutral-700/30 rounded-lg p-4 bg-black/30">
            <h3 className="text-sm font-medium text-neutral-400 mb-3">Win/Loss Distribution</h3>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={70}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#000', border: '1px solid #374151', borderRadius: '4px' }}
                    itemStyle={{ color: '#fff' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* P&L Over Time */}
          {pnlData.length > 0 && (
            <div className="border border-neutral-700/30 rounded-lg p-4 bg-black/30">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium text-neutral-400">P&L Over Time</h3>
                <select
                  value={pnlTimeframe}
                  onChange={(e) => setPnlTimeframe(e.target.value)}
                  className="text-xs bg-black/50 border border-neutral-700/30 rounded px-2 py-1 text-white"
                >
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="all">All Time</option>
                </select>
              </div>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={pnlData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="date" stroke="#6b7280" fontSize={10} />
                    <YAxis stroke="#6b7280" fontSize={10} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#000', border: '1px solid #374151', borderRadius: '4px' }}
                      itemStyle={{ color: '#fff' }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="pnl" 
                      stroke="#10b981" 
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>
      )}
        </div>
      </div>
    </div>
  )
}
