import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Search, TrendingUp, TrendingDown } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { getAnalyticsMetrics, getPnlSeries } from '../api/analytics'
import { getClosedTrades, getClosedTradesCount } from '../api/trades'
import { useMode } from '../contexts/ModeContext'
import type { Trade } from '../types'

const TIMEFRAMES = [
  { label: 'All', value: 'all' },
  { label: '7D', value: '7d' },
  { label: '30D', value: '30d' },
  { label: '90D', value: '90d' },
  { label: 'YTD', value: 'ytd' },
  { label: '1Y', value: '1y' },
] as const

export default function AnalyticsPage() {
  const { mode } = useMode()
  const [timeframe, setTimeframe] = useState<'all' | '7d' | '30d' | '90d' | 'ytd' | '1y'>('all')
  const [asset, setAsset] = useState('')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('date_desc')
  const [page, setPage] = useState(1)
  const limit = 10

  const metricsQuery = useQuery({ queryKey: ['analytics-metrics', timeframe, mode], queryFn: async () => (await getAnalyticsMetrics(timeframe, mode)).data })
  const seriesQuery = useQuery({ queryKey: ['analytics-pnl-series', timeframe, mode], queryFn: async () => (await getPnlSeries(timeframe, mode)).data ?? [] })
  const countQuery = useQuery({ queryKey: ['closed-trades-count', mode], queryFn: async () => (await getClosedTradesCount(mode)).data?.count ?? 0 })
  const tradesQuery = useQuery({
    queryKey: ['closed-trades', { timeframe, asset, search, sort, page, limit, mode }],
    queryFn: async () => (await getClosedTrades({ asset: asset || undefined, search: search || undefined, sort, page, limit, mode })).data ?? { trades: [] },
  })

  const trades = (tradesQuery.data?.trades ?? []) as Trade[]
  const totalCount = countQuery.data ?? tradesQuery.data?.count ?? 0
  const totalPages = Math.max(1, Math.ceil(totalCount / limit))

  const assets = useMemo(() => {
    const values = new Set<string>()
    trades.forEach((trade) => { if (trade.Asset) values.add(trade.Asset) })
    return Array.from(values).sort()
  }, [trades])

  // Determine chart color based on final P&L
  const chartColor = useMemo(() => {
    const series = seriesQuery.data ?? []
    if (series.length === 0) return '#22c55e' // green
    const lastPoint = series[series.length - 1]
    const finalPnl = lastPoint?.cumulative_pnl ?? 0
    return finalPnl >= 0 ? '#22c55e' : '#ef4444' // green or red
  }, [seriesQuery.data])

  return (
    <div className="space-y-6">
      <section className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20 space-y-6">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold text-white">Performance Overview</h2>
            <p className="text-sm text-neutral-400">View key metrics and cumulative P&amp;L by timeframe.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {TIMEFRAMES.map((item) => (
              <button key={item.value} onClick={() => setTimeframe(item.value)} className={timeframe === item.value ? 'px-3 py-1.5 rounded-full border border-green-500 text-green-400 text-xs font-semibold' : 'px-3 py-1.5 rounded-full border border-neutral-700 text-neutral-400 text-xs hover:text-white'}>{item.label}</button>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <MetricCard label="Total P&L" value={metricsQuery.data?.total_pnl ?? 0} showCurrency isPnl />
          <MetricCard label="Win Rate" value={`${(metricsQuery.data?.win_rate ?? 0).toFixed(1)}%`} />
          <MetricCard label="Avg Win" value={metricsQuery.data?.avg_win ?? 0} showCurrency />
          <MetricCard label="Avg Loss" value={metricsQuery.data?.avg_loss ?? 0} showCurrency isLoss />
        </div>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={seriesQuery.data ?? []}>
              <defs>
                <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={chartColor} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={chartColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
              <XAxis dataKey="date" stroke="#737373" />
              <YAxis stroke="#737373" />
              <Tooltip contentStyle={{ background: '#0a0a0a', border: '1px solid #262626' }} />
              <Line type="monotone" dataKey="cumulative_pnl" stroke={chartColor} strokeWidth={2} dot={false} fill="url(#pnlGradient)" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20 space-y-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <h2 className="text-lg font-semibold text-white">Trade History</h2>
          <div className="text-sm text-neutral-400">{totalCount} total trades</div>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
          <label className="rounded-lg bg-black border border-neutral-700 px-3 py-2 text-sm text-white flex items-center gap-2">
            <span className="text-neutral-500 text-xs uppercase tracking-wide">Asset</span>
            <select value={asset} onChange={(e) => { setAsset(e.target.value); setPage(1) }} className="w-full bg-transparent outline-none"><option value="">All Assets</option>{assets.map((a) => <option key={a} value={a}>{a}</option>)}</select>
          </label>
          <label className="rounded-lg bg-black border border-neutral-700 px-3 py-2 text-sm text-white flex items-center gap-2">
            <span className="text-neutral-500 text-xs uppercase tracking-wide">Date Range</span>
            <input type="date" value="" readOnly className="w-full bg-transparent outline-none opacity-50 text-neutral-400 [&::-webkit-calendar-picker-indicator]:filter [&::-webkit-calendar-picker-indicator]:invert" aria-label="Date range filter coming soon" />
          </label>
          <label className="rounded-lg bg-black border border-neutral-700 px-3 py-2 text-sm text-white flex items-center gap-2">
            <span className="text-neutral-500 text-xs uppercase tracking-wide">P&amp;L Sort</span>
            <select value={sort} onChange={(e) => { setSort(e.target.value); setPage(1) }} className="w-full bg-transparent outline-none"><option value="date_desc">Date: Newest</option><option value="date_asc">Date: Oldest</option><option value="pnl_desc">P&amp;L: High to Low</option><option value="pnl_asc">P&amp;L: Low to High</option></select>
          </label>
          <label className="rounded-lg bg-black border border-neutral-700 px-3 py-2 text-sm text-white flex items-center gap-2">
            <Search className="h-4 w-4 text-neutral-500" />
            <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} placeholder="Search trades" className="w-full bg-transparent outline-none placeholder-neutral-500" />
          </label>
        </div>
        <div className="space-y-3">
          {trades.length === 0 ? <div className="rounded-lg border border-dashed border-neutral-700 p-6 text-sm text-neutral-500 text-center">No trades match the selected filters.</div> : trades.map((trade, index) => {
            const pnl = trade['P&L'] ?? 0
            const isLong = trade.Direction?.toUpperCase() === 'LONG'
            const directionLabel = isLong ? 'L' : 'S'
            const directionColor = isLong ? 'bg-green-500/20 text-green-400 border-green-500/30' : 'bg-red-500/20 text-red-400 border-red-500/30'
            const entryPrice = trade.Entry
            const exitPrice = trade.Exit_Price
            const leverage = trade.Leverage

            return (
              <div key={`${trade._index ?? index}`} className="rounded-lg border border-neutral-700 bg-black/40 p-4 flex items-center justify-between gap-4">
                {/* Left: Ticker + Badge + Date */}
                <div className="flex items-center gap-3 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-white font-medium">{trade.Asset}</span>
                    <span className={`px-1.5 py-0.5 rounded text-xs font-semibold border ${directionColor}`}>{directionLabel}</span>
                  </div>
                  <div className="text-xs text-neutral-500">{trade.Date}</div>
                </div>

                {/* Middle: Entry -> Exit | Leverage */}
                <div className="flex items-center gap-4 text-sm text-neutral-300">
                  <div className="flex items-center gap-1.5">
                    {entryPrice !== undefined && exitPrice !== undefined ? (
                      <>
                        <span className="text-neutral-400">${entryPrice.toFixed(2)}</span>
                        <span className="text-neutral-600">→</span>
                        <span className="text-neutral-400">${exitPrice.toFixed(2)}</span>
                      </>
                    ) : (
                      <span className="text-neutral-600">—</span>
                    )}
                  </div>
                  {leverage !== undefined && (
                    <div className="px-2 py-0.5 rounded bg-neutral-800 text-xs text-neutral-400">
                      {leverage}x
                    </div>
                  )}
                </div>

                {/* Right: P&L */}
                <div className="flex items-center gap-2">
                  {pnl >= 0 ? <TrendingUp className="h-4 w-4 text-green-400" /> : <TrendingDown className="h-4 w-4 text-red-400" />}
                  <span className={pnl >= 0 ? 'text-green-400 font-semibold' : 'text-red-400 font-semibold'}>{formatCurrency(pnl)}</span>
                </div>
              </div>
            )
          })}
        </div>
        {totalCount > limit && (
          <div className="flex items-center justify-between">
            <button disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))} className="inline-flex items-center gap-2 rounded-lg border border-neutral-700 px-3 py-2 text-sm text-neutral-300 disabled:opacity-40"><ChevronLeft className="h-4 w-4" /> Previous</button>
            <div className="text-sm text-neutral-400">Page {page} of {totalPages}</div>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))} className="inline-flex items-center gap-2 rounded-lg border border-neutral-700 px-3 py-2 text-sm text-neutral-300 disabled:opacity-40">Next <ChevronRight className="h-4 w-4" /></button>
          </div>
        )}
      </section>
    </div>
  )
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value)
}

function MetricCard({ label, value, showCurrency = false, isPnl = false, isLoss = false }: { label: string; value: number | string; showCurrency?: boolean; isPnl?: boolean; isLoss?: boolean }) {
  const numValue = typeof value === 'number' ? value : parseFloat(value) || 0
  const display = typeof value === 'number'
    ? (showCurrency ? formatCurrency(numValue) : numValue.toFixed(2))
    : value

  // Determine color based on type and value
  let colorClass = 'text-white'
  let indicator = null

  if (isPnl) {
    if (numValue > 0) {
      colorClass = 'text-green-400'
      indicator = <TrendingUp className="h-4 w-4 text-green-400 inline ml-1" />
    } else if (numValue < 0) {
      colorClass = 'text-red-400'
      indicator = <TrendingDown className="h-4 w-4 text-red-400 inline ml-1" />
    }
  } else if (isLoss) {
    colorClass = numValue > 0 ? 'text-red-400' : 'text-neutral-400'
  } else if (showCurrency && numValue > 0) {
    // Avg Win - green for positive
    colorClass = 'text-green-400'
  }

  return (
    <div className="rounded-xl border border-neutral-800 bg-black/40 p-4">
      <div className="text-xs uppercase tracking-wider text-neutral-500">{label}</div>
      <div className={`mt-2 text-2xl font-semibold ${colorClass}`}>
        {display}
        {indicator}
      </div>
    </div>
  )
}
