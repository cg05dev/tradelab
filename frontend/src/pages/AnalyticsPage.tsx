import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Search, TrendingDown, TrendingUp } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getAnalyticsMetrics, getPnlSeries, type PnlSeriesPoint } from '../api/analytics'
import { getClosedTrades } from '../api/trades'
import { useMode } from '../contexts/ModeContext'
import type { Trade } from '../types'

const TIMEFRAMES = [
  { label: '7D', value: '7d' },
  { label: '30D', value: '30d' },
  { label: '90D', value: '90d' },
  { label: 'YTD', value: 'ytd' },
  { label: '1Y', value: '1y' },
  { label: 'All', value: 'all' },
] as const

type Timeframe = typeof TIMEFRAMES[number]['value']
type ChartMode = 'equity' | 'drawdown'

export default function AnalyticsPage() {
  const { mode } = useMode()
  const [timeframe, setTimeframe] = useState<Timeframe>('all')
  const [chartMode, setChartMode] = useState<ChartMode>('equity')
  const [asset, setAsset] = useState('')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('date_desc')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [expandedTrade, setExpandedTrade] = useState<number | null>(null)

  const metricsQuery = useQuery({
    queryKey: ['analytics-metrics', timeframe, mode],
    queryFn: async () => (await getAnalyticsMetrics(timeframe, mode)).data,
  })
  const seriesQuery = useQuery({
    queryKey: ['analytics-pnl-series', timeframe, mode],
    queryFn: async () => (await getPnlSeries(timeframe, mode)).data ?? [],
  })
  const timeframeStart = startDate || getTimeframeStart(timeframe)
  const tradesQuery = useQuery({
    queryKey: ['closed-trades', { timeframe, asset, search, sort, startDate: timeframeStart, endDate, page, limit: pageSize, mode }],
    queryFn: async () => (await getClosedTrades({
      asset: asset || undefined,
      search: search || undefined,
      sort,
      start: timeframeStart || undefined,
      end: endDate || undefined,
      page,
      limit: pageSize,
      mode,
    })).data ?? { trades: [], count: 0 },
  })

  const metrics = metricsQuery.data
  const trades = useMemo(() => (tradesQuery.data?.trades ?? []) as Trade[], [tradesQuery.data])
  const totalCount = tradesQuery.data?.count ?? 0
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize))
  const firstVisibleTrade = totalCount === 0 ? 0 : (page - 1) * pageSize + 1
  const lastVisibleTrade = Math.min(page * pageSize, totalCount)

  const assets = useMemo(() => {
    const values = new Set<string>()
    trades.forEach((trade) => { if (trade.Asset) values.add(trade.Asset) })
    return Array.from(values).sort()
  }, [trades])

  const chartData = useMemo(() => {
    const points = []
    let peak = 0
    for (const point of seriesQuery.data ?? []) {
      const cumulative = point.cumulative_pnl ?? 0
      peak = Math.max(peak, cumulative)
      points.push({ ...point, drawdown: cumulative - peak })
    }
    return points
  }, [seriesQuery.data])
  const finalPnl = chartData[chartData.length - 1]?.cumulative_pnl ?? 0
  const chartColor = chartMode === 'drawdown' ? '#f97316' : finalPnl >= 0 ? '#22c55e' : '#ef4444'
  const chartDataKey = chartMode === 'equity' ? 'cumulative_pnl' : 'drawdown'

  const changeTimeframe = (value: Timeframe) => {
    setTimeframe(value)
    setStartDate('')
    setEndDate('')
    setPage(1)
  }

  const clearFilters = () => {
    setAsset('')
    setSearch('')
    setSort('date_desc')
    setStartDate('')
    setEndDate('')
    setPage(1)
  }
  const hasFilters = Boolean(asset || search || startDate || endDate || sort !== 'date_desc')

  return (
    <div className="space-y-5">
      <section className={`${mode === 'paper' ? 'glass-panel' : 'glass-panel-live'} space-y-5 p-6 shadow-2xl shadow-black/20`}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="font-display text-lg font-semibold text-white">Performance overview</h2>
            <p className="mt-1 text-sm text-neutral-400">Closed-trade results for your {mode} portfolio.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {TIMEFRAMES.map((item) => (
              <button key={item.value} onClick={() => changeTimeframe(item.value)} className={timeframe === item.value ? 'rounded-full border border-green-500 px-3 py-1.5 text-xs font-semibold text-green-400' : 'rounded-full border border-neutral-700 px-3 py-1.5 text-xs text-neutral-400 hover:text-white'}>{item.label}</button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
          <MetricCard label="Total P&L" value={metrics?.total_pnl ?? 0} showCurrency isPnl detail={`${metrics?.trade_count ?? 0} closed trades`} mode={mode} />
          <MetricCard label="Win rate" value={`${(metrics?.win_rate ?? 0).toFixed(1)}%`} detail={`${metrics?.win_count ?? 0} wins · ${metrics?.loss_count ?? 0} losses`} mode={mode} />
          <MetricCard label="Average win" value={metrics?.avg_win ?? 0} showCurrency detail={`${metrics?.win_count ?? 0} winning trades`} mode={mode} />
          <MetricCard label="Average loss" value={metrics?.avg_loss ?? 0} showCurrency isLoss detail={`${metrics?.loss_count ?? 0} losing trades`} mode={mode} />
          <MetricCard label="Profit factor" value={metrics?.profit_factor == null ? '—' : metrics.profit_factor.toFixed(2)} detail="Gross profit ÷ loss" mode={mode} />
          <MetricCard label="Max drawdown" value={metrics?.max_drawdown ?? 0} showCurrency isLoss detail="Peak-to-trough P&L" mode={mode} />
        </div>

        <div className="rounded-xl border border-white/[0.06] bg-black/20 p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-white">{chartMode === 'equity' ? 'Cumulative P&L' : 'Drawdown'}</h3>
              <p className="mt-0.5 text-xs text-neutral-500">{chartData.length} closed-trade data points</p>
            </div>
            <div className="flex rounded-lg border border-white/[0.08] bg-black/30 p-1">
              {(['equity', 'drawdown'] as ChartMode[]).map((item) => (
                <button key={item} onClick={() => setChartMode(item)} className={`rounded-md px-3 py-1.5 text-xs font-medium capitalize ${chartMode === item ? 'bg-white/10 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}>{item}</button>
              ))}
            </div>
          </div>
          <div className="h-72">
            {chartData.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-neutral-500">No closed trades in this timeframe.</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#262626" vertical={false} />
                  <ReferenceLine y={0} stroke="#525252" strokeDasharray="4 4" />
                  <XAxis dataKey="date" stroke="#737373" tick={{ fontSize: 11 }} minTickGap={60} tickFormatter={formatChartDate} />
                  <YAxis stroke="#737373" tick={{ fontSize: 11 }} width={64} tickFormatter={(value) => formatCompactCurrency(Number(value))} />
                  <Tooltip content={<ChartTooltip mode={chartMode} />} />
                  <Line type="stepAfter" dataKey={chartDataKey} stroke={chartColor} strokeWidth={2} dot={{ r: 3, fill: chartColor, strokeWidth: 0 }} activeDot={{ r: 5 }} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </section>

      <section className={`${mode === 'paper' ? 'glass-panel' : 'glass-panel-live'} space-y-4 p-6 shadow-2xl shadow-black/20`}>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="font-display text-lg font-semibold text-white">Trade history</h2>
            <p className="mt-1 text-sm text-neutral-400">Inspect realized outcomes and expand a row for journal details.</p>
          </div>
          <div className="flex items-center gap-3 text-sm text-neutral-400">
            <span>{totalCount} trades</span>
            <select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1) }} className="rounded border border-neutral-700 bg-black px-2 py-1.5 text-xs text-white outline-none" aria-label="Trades per page">
              <option value={10}>10 rows</option><option value={25}>25 rows</option><option value={50}>50 rows</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-2 lg:grid-cols-[1fr_1fr_1fr_1.35fr_auto]">
          <select value={asset} onChange={(event) => { setAsset(event.target.value); setPage(1) }} className="rounded-lg border border-neutral-700 bg-black px-3 py-2.5 text-sm text-white outline-none"><option value="">All assets</option>{assets.map((item) => <option key={item} value={item}>{item}</option>)}</select>
          <input type="date" value={startDate} onChange={(event) => { setStartDate(event.target.value); setPage(1) }} className="rounded-lg border border-neutral-700 bg-black px-3 py-2.5 text-sm text-neutral-300 outline-none [color-scheme:dark]" aria-label="Start date" />
          <input type="date" value={endDate} onChange={(event) => { setEndDate(event.target.value); setPage(1) }} className="rounded-lg border border-neutral-700 bg-black px-3 py-2.5 text-sm text-neutral-300 outline-none [color-scheme:dark]" aria-label="End date" />
          <label className="flex items-center gap-2 rounded-lg border border-neutral-700 bg-black px-3 py-2.5 text-sm text-white">
            <Search className="h-4 w-4 text-neutral-500" />
            <input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="Search asset or notes…" className="w-full bg-transparent outline-none placeholder-neutral-500" />
          </label>
          <select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1) }} className="rounded-lg border border-neutral-700 bg-black px-3 py-2.5 text-sm text-white outline-none"><option value="date_desc">Newest</option><option value="date_asc">Oldest</option><option value="pnl_desc">Highest P&L</option><option value="pnl_asc">Lowest P&L</option></select>
        </div>
        {hasFilters && <button type="button" onClick={clearFilters} className="text-xs text-neutral-400 underline underline-offset-4 hover:text-white">Clear filters</button>}

        <div className="overflow-hidden rounded-xl border border-white/[0.07]">
          <div className="hidden grid-cols-[minmax(180px,1.3fr)_170px_minmax(230px,1fr)_90px_140px_28px] gap-4 border-b border-white/[0.07] bg-white/[0.025] px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-neutral-500 md:grid">
            <span>Market / side</span><span>Closed</span><span>Entry → exit</span><span>Leverage</span><span className="text-right">Realized P&L</span><span />
          </div>
          {trades.length === 0 ? (
            <div className="p-8 text-center text-sm text-neutral-500">No trades match the selected filters.</div>
          ) : trades.map((trade, index) => {
            const tradeKey = trade._index ?? index
            const expanded = expandedTrade === tradeKey
            const pnl = Number(trade['P&L'] ?? 0)
            const margin = Number(trade.Margin ?? 0)
            const positionSize = Number(trade.Position_Size ?? 0)
            const returnBase = margin > 0 ? margin : positionSize
            const returnPercent = returnBase > 0 ? pnl / returnBase * 100 : null
            const isLong = trade.Direction?.toUpperCase() === 'LONG'

            return (
              <div key={tradeKey} className="border-b border-white/[0.06] last:border-b-0">
                <button type="button" onClick={() => setExpandedTrade(expanded ? null : tradeKey)} className="grid w-full items-center gap-3 px-4 py-3 text-left hover:bg-white/[0.025] md:grid-cols-[minmax(180px,1.3fr)_170px_minmax(230px,1fr)_90px_140px_28px] md:gap-4">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-white">{trade.Asset}</span>
                    <span className={`rounded border px-2 py-0.5 text-xs font-semibold ${isLong ? 'border-green-500/30 bg-green-500/10 text-green-400' : 'border-red-500/30 bg-red-500/10 text-red-400'}`}>{isLong ? 'Long' : 'Short'}</span>
                  </div>
                  <span className="text-xs tabular-nums text-neutral-400">{formatTradeDate(trade.Date)}</span>
                  <div className="flex items-center gap-2 text-sm tabular-nums text-neutral-300"><span>{formatCurrency(trade.Entry ?? 0)}</span><span className="text-neutral-600">→</span><span>{formatCurrency(trade.Exit_Price ?? 0)}</span></div>
                  <span className="w-fit rounded bg-neutral-800 px-2 py-0.5 text-xs tabular-nums text-neutral-300">{trade.Leverage ?? '—'}x</span>
                  <div className={`text-right font-semibold tabular-nums ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    <span>{formatCurrency(pnl)}</span>
                    <span className="ml-1.5 text-xs opacity-70">{returnPercent == null ? '' : `${returnPercent >= 0 ? '+' : ''}${returnPercent.toFixed(1)}%`}</span>
                  </div>
                  {expanded ? <ChevronUp className="h-4 w-4 text-neutral-500" /> : <ChevronDown className="h-4 w-4 text-neutral-500" />}
                </button>
                {expanded && <TradeDetails trade={trade} returnPercent={returnPercent} />}
              </div>
            )
          })}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-neutral-500">{totalCount ? `Showing ${firstVisibleTrade}–${lastVisibleTrade} of ${totalCount}` : 'No trades to show'}</p>
          {totalPages > 1 && (
            <div className="flex items-center gap-3">
              <button disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="inline-flex items-center gap-1 rounded-lg border border-neutral-700 px-3 py-2 text-sm text-neutral-300 disabled:opacity-40"><ChevronLeft className="h-4 w-4" /> Previous</button>
              <span className="text-sm tabular-nums text-neutral-400">{page} / {totalPages}</span>
              <button disabled={page >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))} className="inline-flex items-center gap-1 rounded-lg border border-neutral-700 px-3 py-2 text-sm text-neutral-300 disabled:opacity-40">Next <ChevronRight className="h-4 w-4" /></button>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

function TradeDetails({ trade, returnPercent }: { trade: Trade; returnPercent: number | null }) {
  const targets = parseLevels(trade.TPs)
  const stops = parseLevels(trade.SLs)
  return (
    <div className="grid gap-4 border-t border-white/[0.06] bg-black/20 px-4 py-4 text-sm md:grid-cols-4">
      <Detail label="Position / margin" value={`${formatCurrency(trade.Position_Size ?? 0)} / ${formatCurrency(trade.Margin ?? 0)}`} />
      <Detail label="Return on margin" value={returnPercent == null ? '—' : `${returnPercent >= 0 ? '+' : ''}${returnPercent.toFixed(2)}%`} />
      <Detail label="Stop loss" value={stops.length ? stops.map((item) => formatCurrency(item.price)).join(', ') : trade.SL ? formatCurrency(trade.SL) : 'Not recorded'} />
      <Detail label="Profit targets" value={targets.length ? targets.map((item) => `${formatCurrency(item.price)} (${item.allocation}%)`).join(', ') : 'Not recorded'} />
      <div className="md:col-span-4"><Detail label="Trade notes" value={trade.Thesis || 'No thesis or notes recorded.'} /></div>
    </div>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs text-neutral-500">{label}</p><p className="mt-1 text-neutral-300">{value}</p></div>
}

function ChartTooltip({ active, payload, mode }: { active?: boolean; payload?: Array<{ payload: PnlSeriesPoint & { drawdown?: number } }>; mode: ChartMode }) {
  const point = payload?.[0]?.payload
  if (!active || !point) return null
  return (
    <div className="rounded-lg border border-neutral-700 bg-[#0a0a0c]/95 p-3 text-xs shadow-xl">
      <p className="font-medium text-white">{formatTradeDate(point.date)}</p>
      {point.asset && <p className="mt-1 text-neutral-400">{point.asset} · Trade P&amp;L <span className={Number(point.pnl) >= 0 ? 'text-green-400' : 'text-red-400'}>{formatCurrency(point.pnl ?? 0)}</span></p>}
      <p className="mt-1 text-neutral-400">{mode === 'equity' ? 'Cumulative P&L' : 'Drawdown'} <span className="font-medium text-white">{formatCurrency(mode === 'equity' ? point.cumulative_pnl ?? 0 : point.drawdown ?? 0)}</span></p>
    </div>
  )
}

function MetricCard({ label, value, detail, showCurrency = false, isPnl = false, isLoss = false, mode }: { label: string; value: number | string; detail: string; showCurrency?: boolean; isPnl?: boolean; isLoss?: boolean; mode: 'paper' | 'live' }) {
  const numberValue = typeof value === 'number' ? value : Number.NaN
  const display = typeof value === 'number' ? showCurrency ? formatCurrency(value) : value.toFixed(2) : value
  const color = isPnl && numberValue !== 0 ? numberValue > 0 ? 'text-green-400' : 'text-red-400' : isLoss && numberValue > 0 ? 'text-orange-400' : 'text-white'
  return (
    <div className={`${mode === 'paper' ? 'glass-card' : 'glass-card-live'} min-w-0 p-4`}>
      <p className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">{label}</p>
      <div className={`mt-2 flex items-center text-xl font-semibold tabular-nums ${color}`}>
        {display}
        {isPnl && numberValue > 0 && <TrendingUp className="ml-1.5 h-4 w-4" />}
        {isPnl && numberValue < 0 && <TrendingDown className="ml-1.5 h-4 w-4" />}
      </div>
      <p className="mt-1 text-xs text-neutral-500">{detail}</p>
    </div>
  )
}

function getTimeframeStart(timeframe: Timeframe) {
  if (timeframe === 'all') return ''
  const date = new Date()
  if (timeframe === 'ytd') date.setMonth(0, 1)
  else if (timeframe === '1y') date.setFullYear(date.getFullYear() - 1)
  else date.setDate(date.getDate() - Number.parseInt(timeframe, 10))
  return date.toISOString().slice(0, 10)
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
}

function formatCompactCurrency(value: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

function formatChartDate(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function formatTradeDate(value?: string) {
  if (!value) return 'Unknown date'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function parseLevels(value?: string): Array<{ price: number; allocation: number }> {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}
