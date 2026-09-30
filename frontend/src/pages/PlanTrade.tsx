import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { addTrade } from '../api/trades'
import { getPortfolio } from '../api/portfolio'
import { getHyperliquidPrice, placeHyperliquidOrder, getHyperliquidAssets } from '../api/hyperliquid'
import { getErrorMessage } from '../api/error'
import { useMode, type UITradingMode } from '../contexts/ModeContext'
import type { HyperliquidAsset, TakeProfit, TradeDetails, HyperliquidOrderRequest } from '../types'

const MAINTENANCE_MARGIN = 0.0125
const MAX_LIVE_RISK_PERCENT = 5
const normalizeMode = (value?: string | null): UITradingMode => value === 'paper' ? 'paper' : 'live'
const formatMoney = (value?: number | null) =>
  value == null
    ? '—'
    : `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export default function PlanTrade({ onTradeAdded }: { onTradeAdded?: () => void }) {
  const queryClient = useQueryClient()
  const { mode } = useMode()
  const [asset] = useState('BTC-USDC')
  const [direction, setDirection] = useState('long')
  const [leverage, setLeverage] = useState(10)
  const [riskPercentage, setRiskPercentage] = useState(2)
  const [stopLoss, setStopLoss] = useState<number | null>(null)
  const [takeProfits, setTakeProfits] = useState<TakeProfit[]>([])
  const [thesis, setThesis] = useState('')
  const [currentPrice, setCurrentPrice] = useState<number | null>(null)
  const [tradeDetails, setTradeDetails] = useState<TradeDetails | null>(null)
  const [showConfirmation, setShowConfirmation] = useState(false)
  const [toast, setToast] = useState<{ tone: 'success' | 'error'; message: string } | null>(null)

  const portfolioQuery = useQuery({
    queryKey: ['portfolio', mode],
    queryFn: async () => (await getPortfolio(mode)).data,
    refetchInterval: 1000,
  })
  const assetsQuery = useQuery<HyperliquidAsset[]>({
    queryKey: ['hyperliquid-assets'],
    queryFn: async () => (await getHyperliquidAssets()).data?.assets || [],
  })
  const priceQuery = useQuery({
    queryKey: ['hyperliquid-price', asset],
    queryFn: async () => (await getHyperliquidPrice(asset.split('-')[0] ?? '')).data?.price ?? null,
    enabled: Boolean(asset),
    refetchInterval: 1000,
    refetchOnWindowFocus: false,
    retry: 1,
  })

  useEffect(() => {
    if (priceQuery.data != null) setCurrentPrice(priceQuery.data)
  }, [priceQuery.data])

  useEffect(() => {
    if (!toast) return
    const timeout = window.setTimeout(() => setToast(null), 4000)
    return () => window.clearTimeout(timeout)
  }, [toast])

  useEffect(() => {
    if (!currentPrice) return

    const portfolioSize = portfolioQuery.data?.portfolio_size || 2000
    const riskAmount = portfolioSize * riskPercentage / 100
    const liquidationPrice = direction === 'long'
      ? currentPrice * (1 - (1 / leverage) + MAINTENANCE_MARGIN)
      : currentPrice * (1 + (1 / leverage) - MAINTENANCE_MARGIN)
    const isStopLossValid = Boolean(stopLoss && stopLoss > 0 && (
      direction === 'long'
        ? stopLoss > liquidationPrice && stopLoss < currentPrice
        : stopLoss < liquidationPrice && stopLoss > currentPrice
    ))
    const riskDistancePercent = isStopLossValid && stopLoss
      ? Math.abs(currentPrice - stopLoss) / currentPrice
      : Math.abs(currentPrice - liquidationPrice) / currentPrice
    const positionSizeDollars = riskAmount / riskDistancePercent
    const positionSize = positionSizeDollars / currentPrice
    const marginRequired = positionSizeDollars / leverage
    const tpProfits = takeProfits
      .filter((tp) => tp.price > 0 && tp.allocation > 0)
      .map((tp, index) => ({
        ...tp,
        index: index + 1,
        profit: ((tp.price - currentPrice) * positionSize * tp.allocation / 100) * (direction === 'short' ? -1 : 1),
      }))
    const estimatedProfit = tpProfits.reduce((sum, tp) => sum + tp.profit, 0)

    setTradeDetails({
      liquidationPrice,
      positionSize,
      positionSizeDollars,
      marginRequired,
      riskRewardRatio: riskAmount > 0 ? estimatedProfit / riskAmount : 0,
      estimatedLoss: riskAmount,
      estimatedProfit,
      tpProfits,
      positionValue: positionSizeDollars,
      currentPrice,
      isStopLossValid,
    })
  }, [currentPrice, direction, leverage, portfolioQuery.data?.portfolio_size, riskPercentage, takeProfits, stopLoss])

  const executeMutation = useMutation({
    mutationFn: async () => {
      if (!asset || !currentPrice) throw new Error('A live market price is required before placing a trade')
      const currentMode = normalizeMode(mode)
      await addTrade({
        asset,
        direction,
        leverage,
        entry_price: currentPrice,
        stop_loss: stopLoss ?? 0,
        position_size: tradeDetails?.positionSizeDollars ?? 0,
        take_profits: takeProfits,
        stop_losses: stopLoss ? [{ price: stopLoss, allocation: 100 }] : [],
        thesis,
      }, currentMode)

      if (currentMode === 'live') {
        const order: HyperliquidOrderRequest = {
          coin: asset.split('-')[0] ?? asset,
          is_buy: direction === 'long',
          margin_amount: ((portfolioQuery.data?.portfolio_size || 2000) * riskPercentage / 100),
          leverage,
          entry_price: currentPrice,
          take_profits: takeProfits,
          stop_losses: stopLoss ? [{ price: stopLoss, allocation: 100 }] : [],
          is_isolated: true,
        }
        await placeHyperliquidOrder(order)
      }
    },
    onSuccess: async () => {
      setShowConfirmation(false)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['closed-trades'] }),
        queryClient.invalidateQueries({ queryKey: ['portfolio'] }),
        queryClient.invalidateQueries({ queryKey: ['open-trades'] }),
        queryClient.invalidateQueries({ queryKey: ['mode'] }),
      ])
      onTradeAdded?.()
      setToast({
        tone: 'success',
        message: mode === 'live'
          ? 'Live order placed and saved to your journal.'
          : 'Paper trade saved to your journal.',
      })
    },
    onError: (error) => setToast({ tone: 'error', message: getErrorMessage(error, 'Error executing trade') }),
  })

  const maxLeverage = assetsQuery.data?.find((item) => item.symbol === asset.split('-')[0])?.max_leverage ?? 50
  const validTargets = tradeDetails?.tpProfits ?? []
  const hasStop = Boolean(stopLoss && tradeDetails?.isStopLossValid)
  const stopDistance = stopLoss && currentPrice ? Math.abs(stopLoss - currentPrice) / currentPrice * 100 : null
  const actionLabel = mode === 'live' ? 'Place Live Order' : 'Open Paper Trade'
  const allocationTotal = takeProfits.reduce((total, target) => total + target.allocation, 0)
  const remainingAllocation = 100 - allocationTotal
  const allocationsValid = takeProfits.length > 0 && Math.abs(remainingAllocation) < 0.01
  const targetsValid = Boolean(currentPrice && takeProfits.length > 0 && takeProfits.every((target) =>
    target.price > 0 && (
      direction === 'long'
        ? target.price > currentPrice
        : target.price < currentPrice
    )
  ))
  const riskValid = riskPercentage > 0 && riskPercentage <= MAX_LIVE_RISK_PERCENT
  const liveReadiness = [
    { valid: Boolean(currentPrice && !priceQuery.isError), message: 'Wait for a current live market price.' },
    { valid: hasStop, message: 'Configure a valid stop loss before placing a live order.' },
    { valid: targetsValid, message: 'Add at least one valid profit target before placing a live order.' },
    { valid: allocationsValid, message: 'Set target allocations to a total of 100%.' },
    { valid: riskValid, message: `Keep risk at or below ${MAX_LIVE_RISK_PERCENT}%.` },
  ]
  const addTarget = () => {
    if (takeProfits.length >= 4) return
    const count = takeProfits.length + 1
    const allocation = 100 / count
    setTakeProfits([...takeProfits.map((tp) => ({ ...tp, allocation })), { price: 0, allocation }])
  }

  const removeTarget = (index: number) => {
    const remaining = takeProfits.filter((_, itemIndex) => itemIndex !== index)
    const allocation = remaining.length ? 100 / remaining.length : 0
    setTakeProfits(remaining.map((tp) => ({ ...tp, allocation })))
  }

  const reviewLiveOrder = () => {
    const firstIncompleteItem = liveReadiness.find((item) => !item.valid)
    if (firstIncompleteItem) {
      setToast({ tone: 'error', message: firstIncompleteItem.message })
      return
    }
    setShowConfirmation(true)
  }

  return (
    <>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_430px]">
        <div className="space-y-0">
          <div className={`${mode === 'paper' ? 'glass-panel' : 'glass-panel-live'} p-7 md:p-8 shadow-2xl shadow-black/20 !rounded-b-none border-b-0`}>
            <form onSubmit={(event) => event.preventDefault()} className="space-y-8">
              <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
                    <h2 className="font-display text-lg font-semibold text-white">{asset}</h2>
                    <span className="font-display text-2xl font-medium tabular-nums text-white">
                      {priceQuery.isLoading && !currentPrice ? 'Loading…' : formatMoney(currentPrice)}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center gap-2 text-sm">
                    <span className="text-neutral-400">Perpetual</span>
                    <span className="text-neutral-700">•</span>
                    <span
                      className={priceQuery.isError ? 'text-amber-400' : 'text-neutral-400'}
                      title={priceQuery.dataUpdatedAt ? `Last price update: ${new Date(priceQuery.dataUpdatedAt).toLocaleTimeString()}` : undefined}
                    >
                      <span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${priceQuery.isError ? 'bg-amber-400' : 'animate-pulse bg-emerald-400'}`} />
                      {priceQuery.isError ? 'Price stale' : 'Live market'}
                    </span>
                  </div>
                </div>
                <div className="flex rounded-xl border border-white/10 bg-black/20 p-1" aria-label="Trade direction">
                  {['long', 'short'].map((side) => (
                    <button
                      key={side}
                      type="button"
                      onClick={() => setDirection(side)}
                      className={`min-w-24 rounded-lg px-6 py-2.5 text-sm font-semibold capitalize ${
                        direction === side
                          ? side === 'long'
                            ? 'border border-green-400/30 bg-green-400/10 text-green-400'
                            : 'border border-red-400/30 bg-red-400/10 text-red-400'
                          : 'text-neutral-400 hover:text-white'
                      }`}
                    >
                      {side}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid items-center gap-4 sm:grid-cols-[100px_64px_minmax(0,1fr)_72px]">
                <label htmlFor="leverage" className="text-sm font-medium text-neutral-300">Leverage</label>
                <span className="font-display text-base font-semibold tabular-nums text-white">{leverage}x</span>
                <input id="leverage" type="range" min="1" max={maxLeverage} value={leverage} onChange={(event) => setLeverage(Number(event.target.value))} className="leverage-slider w-full accent-neutral-400" />
                <span className="text-right text-xs text-neutral-400">Max {maxLeverage}x</span>
              </div>

              <div className="overflow-hidden rounded-xl border border-white/[0.07] bg-black/20">
                <section className="p-5 md:p-6">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-300">Take profits</h3>
                      <p className="mt-1 text-xs text-neutral-500">Up to four targets with percentage allocations.</p>
                    </div>
                    {takeProfits.length > 0 && takeProfits.length < 4 && (
                      <button type="button" onClick={addTarget} className="rounded-lg px-3 py-2 text-sm font-medium text-green-400 hover:bg-green-400/10">
                        + Add another target
                      </button>
                    )}
                  </div>
                  {takeProfits.length === 0 ? (
                    <button type="button" onClick={addTarget} className="w-full rounded-lg border border-dashed border-white/10 px-4 py-4 text-sm text-neutral-400 hover:border-green-400/30 hover:text-green-400">
                      Add a profit target to calculate potential return
                    </button>
                  ) : (
                    <div className="space-y-3">
                      <div className="grid grid-cols-[1fr_96px_110px_28px] gap-3 px-1 text-[11px] font-medium uppercase tracking-wider text-neutral-500">
                        <span>Target price</span><span>Allocation</span><span>Est. profit</span><span />
                      </div>
                      {takeProfits.map((tp, index) => (
                        <div key={index} className="grid grid-cols-[1fr_96px_110px_28px] items-center gap-3">
                          <input type="number" value={tp.price || ''} onChange={(event) => { const updated = [...takeProfits]; updated[index] = { ...updated[index], price: Number(event.target.value) || 0 }; setTakeProfits(updated) }} placeholder="68,000.00" step="0.01" className="rounded-lg border border-white/10 bg-white/[0.025] px-3 py-2.5 text-sm tabular-nums text-white placeholder-neutral-600 focus:outline-none focus:border-green-400/50" />
                          <div className="relative"><input type="number" value={Number(tp.allocation.toFixed(2)) || ''} onChange={(event) => { const updated = [...takeProfits]; updated[index] = { ...updated[index], allocation: Number(event.target.value) || 0 }; setTakeProfits(updated) }} min="0" max="100" step="1" className="w-full rounded-lg border border-white/10 bg-white/[0.025] px-3 py-2.5 pr-7 text-sm tabular-nums text-white focus:outline-none focus:border-green-400/50" /><span className="pointer-events-none absolute right-3 top-2.5 text-sm text-neutral-500">%</span></div>
                          <span className="text-sm tabular-nums text-green-400">{formatMoney(tradeDetails?.tpProfits[index]?.profit)}</span>
                          <button type="button" onClick={() => removeTarget(index)} aria-label={`Remove target ${index + 1}`} className="flex h-8 w-8 items-center justify-center rounded-md text-lg text-neutral-500 hover:bg-red-400/10 hover:text-red-400">×</button>
                        </div>
                      ))}
                      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] pt-3 text-xs">
                        <span className={allocationsValid ? 'text-green-400' : 'text-amber-300'}>
                          {allocationsValid
                            ? 'Allocation complete'
                            : remainingAllocation > 0
                              ? `${remainingAllocation.toFixed(remainingAllocation % 1 ? 2 : 0)}% remaining`
                              : `${Math.abs(remainingAllocation).toFixed(Math.abs(remainingAllocation) % 1 ? 2 : 0)}% over-allocated`}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            const allocation = 100 / takeProfits.length
                            setTakeProfits(takeProfits.map((target) => ({ ...target, allocation })))
                          }}
                          className="rounded px-2 py-1 text-neutral-400 hover:bg-white/5 hover:text-white"
                        >
                          Equalize allocations
                        </button>
                      </div>
                    </div>
                  )}
                </section>

                <section className="border-t border-white/[0.07] p-5 md:p-6">
                  <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-300">Stop loss</h3>
                  <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
                    <input type="number" value={stopLoss ?? ''} onChange={(event) => setStopLoss(event.target.value ? Number(event.target.value) : null)} placeholder="Stop price" step="0.01" className="min-w-0 flex-1 rounded-lg border border-white/10 bg-white/[0.025] px-3 py-2.5 text-sm tabular-nums text-white placeholder-neutral-600 focus:outline-none focus:border-red-400/50" />
                    {stopDistance != null && (
                      <span className={`text-sm tabular-nums ${tradeDetails?.isStopLossValid ? 'text-neutral-300' : 'text-red-400'}`}>
                        {stopDistance.toFixed(2)}% from market
                      </span>
                    )}
                  </div>
                  <p className={`mt-2 text-xs ${stopLoss && !tradeDetails?.isStopLossValid ? 'text-red-400' : 'text-neutral-500'}`}>
                    {stopLoss && !tradeDetails?.isStopLossValid
                      ? `Stop must be between the market and liquidation price for a ${direction} position.`
                      : hasStop
                        ? `Estimated maximum loss at this stop: ${formatMoney(tradeDetails?.estimatedLoss)}.`
                        : 'No stop set. Position sizing currently uses the estimated liquidation price.'}
                  </p>
                </section>

                <section className="border-t border-white/[0.07] p-5 md:p-6">
                  <label htmlFor="trade-notes" className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-300">Notes</label>
                  <textarea id="trade-notes" value={thesis} onChange={(event) => setThesis(event.target.value)} placeholder="Trade thesis, invalidation, and context…" rows={3} className="mt-3 w-full resize-none rounded-lg border border-white/10 bg-white/[0.025] px-3 py-3 text-sm text-white placeholder-neutral-600 focus:outline-none focus:border-white/30" />
                </section>
              </div>
            </form>
          </div>

          <button
            type="button"
            onClick={() => mode === 'live' ? reviewLiveOrder() : executeMutation.mutate()}
            disabled={executeMutation.isPending || !currentPrice}
            className={`w-full rounded-b-xl border px-5 py-4 text-sm font-semibold transition-all disabled:cursor-not-allowed disabled:opacity-50 ${
              mode === 'paper'
                ? 'border-indigo-400/30 bg-indigo-400/[0.06] text-indigo-300 hover:bg-indigo-400/10'
                : direction === 'short'
                  ? 'border-red-400/30 bg-red-400/[0.06] text-red-400 hover:bg-red-400/10'
                  : 'border-green-400/30 bg-green-400/[0.06] text-green-400 hover:bg-green-400/10'
            }`}
          >
            {executeMutation.isPending ? 'Submitting trade…' : actionLabel}
          </button>
        </div>

        {tradeDetails && (
          <aside className={`${mode === 'paper' ? 'glass-panel' : 'glass-panel-live'} self-stretch p-7 shadow-2xl shadow-black/20 xl:sticky xl:top-8`}>
            <div className="mb-7 flex items-center justify-between">
              <div>
                <h3 className="font-display text-base font-semibold text-white">Trade details</h3>
                <p className="mt-1 text-xs text-neutral-500">Updates with the live market.</p>
              </div>
              <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${mode === 'paper' ? 'bg-indigo-400/10 text-indigo-300' : 'bg-green-400/10 text-green-400'}`}>{mode}</span>
            </div>
            <PriceRange
              currentPrice={currentPrice}
              liquidationPrice={tradeDetails.liquidationPrice}
              stopPrice={hasStop ? stopLoss : null}
              targetPrice={targetsValid ? takeProfits[0]?.price : null}
              direction={direction}
            />
            <p className="mb-7 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs leading-5 text-neutral-400">
              Position sizing: <span className="tabular-nums text-neutral-200">{formatMoney(tradeDetails.estimatedLoss)}</span> risk ÷{' '}
              <span className="tabular-nums text-neutral-200">
                {(hasStop && stopDistance != null
                  ? stopDistance
                  : Math.abs(currentPrice! - tradeDetails.liquidationPrice) / currentPrice! * 100).toFixed(2)}%
              </span>{' '}
              {hasStop ? 'stop' : 'liquidation'} distance = <span className="tabular-nums text-white">{formatMoney(tradeDetails.positionSizeDollars)}</span> position.
            </p>
            <div className="grid grid-cols-2 gap-x-5 gap-y-7">
              <Metric label="Current price" value={formatMoney(currentPrice)} />
              <Metric label="Liquidation price" value={formatMoney(tradeDetails.liquidationPrice)} tone="text-orange-400" />
              <Metric label="Position size" value={formatMoney(tradeDetails.positionSizeDollars)} detail={`${tradeDetails.positionSize.toFixed(6)} BTC`} />
              <Metric label="Margin required" value={formatMoney(tradeDetails.marginRequired)} />
              <Metric label="Risk / reward" value={validTargets.length ? `1:${tradeDetails.riskRewardRatio.toFixed(2)}` : '—'} detail={validTargets.length ? undefined : 'Add a target'} />
              <div>
                <div className="mb-1 flex items-center gap-2">
                  <p className="text-xs font-medium text-neutral-400">Risk amount</p>
                  <label>
                    <span className="sr-only">Risk percentage</span>
                    <select
                      value={riskPercentage}
                      onChange={(event) => setRiskPercentage(Number(event.target.value))}
                      className="rounded-md border border-white/10 bg-white/[0.04] px-2 py-1 text-[11px] font-medium tabular-nums text-neutral-200 focus:outline-none"
                    >
                      {[0.5, 1, 2, 3, 5].map((preset) => <option key={preset} value={preset}>{preset}%</option>)}
                    </select>
                  </label>
                </div>
                <p className="font-display text-xl font-medium tabular-nums text-white">{formatMoney((portfolioQuery.data?.portfolio_size || 2000) * riskPercentage / 100)}</p>
              </div>
              <Metric label={hasStop ? 'Estimated loss at stop' : 'Loss at liquidation'} value={formatMoney(tradeDetails.estimatedLoss)} tone="text-red-400" detail={hasStop ? undefined : 'No stop configured'} />
              <Metric label="Estimated profit" value={validTargets.length ? formatMoney(tradeDetails.estimatedProfit) : '—'} tone={validTargets.length ? 'text-green-400' : 'text-white'} detail={validTargets.length ? `${validTargets.length} active target${validTargets.length === 1 ? '' : 's'}` : 'Add a target'} />
            </div>
          </aside>
        )}
      </div>

      {showConfirmation && tradeDetails && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
          <div className="glass-panel w-full max-w-md p-6 shadow-2xl">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-green-400">Live order</p>
                <h2 className="mt-1 font-display text-xl font-semibold text-white">Confirm order details</h2>
              </div>
              <button type="button" onClick={() => setShowConfirmation(false)} className="rounded-lg p-2 text-neutral-400 hover:bg-white/5 hover:text-white" aria-label="Close confirmation"><X className="h-4 w-4" /></button>
            </div>
            <div className="mt-6 divide-y divide-white/[0.07] rounded-xl border border-white/[0.07] bg-black/20 px-4">
              <ConfirmRow label="Market" value={asset} />
              <ConfirmRow label="Direction" value={direction.toUpperCase()} />
              <ConfirmRow label="Market entry" value={formatMoney(currentPrice)} />
              <ConfirmRow label="Position / margin" value={`${formatMoney(tradeDetails.positionSizeDollars)} / ${formatMoney(tradeDetails.marginRequired)}`} />
              <ConfirmRow label="Leverage" value={`${leverage}x isolated`} />
              <ConfirmRow label="Maximum risk" value={formatMoney(tradeDetails.estimatedLoss)} />
              <ConfirmRow label="Stop loss" value={formatMoney(stopLoss)} />
              <ConfirmRow label="Profit targets" value={`${validTargets.length} · ${allocationTotal.toFixed(0)}% allocated`} />
              <ConfirmRow label="Liquidation" value={formatMoney(tradeDetails.liquidationPrice)} />
            </div>
            <p className="mt-4 rounded-lg border border-green-400/20 bg-green-400/[0.06] px-3 py-2 text-xs text-green-300">
              All live-order safeguards passed. This action will submit a market order to Hyperliquid.
            </p>
            <div className="mt-6 grid grid-cols-2 gap-3">
              <button type="button" onClick={() => setShowConfirmation(false)} className="rounded-lg border border-white/10 px-4 py-3 text-sm font-semibold text-neutral-300 hover:bg-white/5">Cancel</button>
              <button type="button" onClick={() => executeMutation.mutate()} disabled={executeMutation.isPending} className="rounded-lg border border-green-400/30 bg-green-400/10 px-4 py-3 text-sm font-semibold text-green-400 hover:bg-green-400/15 disabled:opacity-50">{executeMutation.isPending ? 'Placing…' : 'Confirm live order'}</button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div
          role="status"
          className={`fixed bottom-6 right-6 z-[60] max-w-sm rounded-xl border px-4 py-3 text-sm shadow-2xl backdrop-blur-md ${
            toast.tone === 'success'
              ? 'border-green-400/25 bg-[#101a14]/95 text-green-200'
              : 'border-red-400/25 bg-[#1b1113]/95 text-red-200'
          }`}
        >
          <div className="flex items-start gap-3">
            <span className="mt-0.5">{toast.tone === 'success' ? '✓' : '!'}</span>
            <p>{toast.message}</p>
            <button type="button" onClick={() => setToast(null)} className="ml-2 text-current opacity-60 hover:opacity-100" aria-label="Dismiss notification">×</button>
          </div>
        </div>
      )}
    </>
  )
}

function Metric({ label, value, detail, tone = 'text-white' }: { label: string; value: string; detail?: string; tone?: string }) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-neutral-400">{label}</p>
      <p className={`font-display text-xl font-medium tabular-nums ${tone}`}>{value}</p>
      {detail && <p className="mt-1 text-xs text-neutral-500">{detail}</p>}
    </div>
  )
}

function ConfirmRow({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between gap-4 py-3 text-sm"><span className="text-neutral-400">{label}</span><span className="text-right font-medium tabular-nums text-white">{value}</span></div>
}

function PriceRange({
  currentPrice,
  liquidationPrice,
  stopPrice,
  targetPrice,
  direction,
}: {
  currentPrice: number | null
  liquidationPrice: number
  stopPrice: number | null
  targetPrice?: number | null
  direction: string
}) {
  if (!currentPrice) return null
  const points = [
    { label: 'Liquidation', value: liquidationPrice, color: 'bg-orange-400' },
    ...(stopPrice ? [{ label: 'Stop', value: stopPrice, color: 'bg-red-400' }] : []),
    { label: 'Market', value: currentPrice, color: 'bg-white' },
    ...(targetPrice ? [{ label: 'Target 1', value: targetPrice, color: 'bg-green-400' }] : []),
  ]
  const values = points.map((point) => point.value)
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  const span = maximum - minimum || 1

  return (
    <div className="mb-7 rounded-xl border border-white/[0.07] bg-black/20 p-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-neutral-400">Price risk range</p>
        <p className="text-[11px] capitalize text-neutral-500">{direction} position</p>
      </div>
      <div className="relative my-5 h-1 rounded-full bg-gradient-to-r from-orange-400/30 via-red-400/20 to-green-400/30">
        {points.map((point) => (
          <span
            key={point.label}
            className={`absolute top-1/2 h-3 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-[#0f0f12] ${point.color}`}
            style={{ left: `${((point.value - minimum) / span) * 100}%` }}
            title={`${point.label}: ${formatMoney(point.value)}`}
          />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-2">
        {points.map((point) => (
          <div key={point.label} className="flex items-center justify-between gap-2 text-[11px]">
            <span className="flex items-center gap-1.5 text-neutral-500"><span className={`h-1.5 w-1.5 rounded-full ${point.color}`} />{point.label}</span>
            <span className="tabular-nums text-neutral-300">{formatMoney(point.value)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
