import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { addTrade } from '../api/trades'
import { getPortfolio } from '../api/portfolio'
import { getHyperliquidPrice, placeHyperliquidOrder, getHyperliquidAssets } from '../api/hyperliquid'
import { getErrorMessage } from '../api/error'
import { useMode, type UITradingMode } from '../contexts/ModeContext'
import type { HyperliquidAsset, TakeProfit, TradeDetails, HyperliquidOrderRequest } from '../types'

const MAINTENANCE_MARGIN = 0.0125
const normalizeMode = (value?: string | null): UITradingMode => value === 'paper' ? 'paper' : 'live'

export default function PlanTrade({ onTradeAdded }: { onTradeAdded?: () => void }) {
  const queryClient = useQueryClient()
  const { mode } = useMode()
  const [asset] = useState('BTC-USDC')
  const [direction, setDirection] = useState('long')
  const [leverage, setLeverage] = useState(10)
  const [riskPercentage, setRiskPercentage] = useState(2.0)
  const [stopLoss, setStopLoss] = useState<number | null>(null)
  const [numTakeProfits, setNumTakeProfits] = useState(0)
  const [takeProfits, setTakeProfits] = useState<TakeProfit[]>([])
  const [thesis, setThesis] = useState('')
  const [currentPrice, setCurrentPrice] = useState<number | null>(null)
  const [tradeDetails, setTradeDetails] = useState<TradeDetails | null>(null)
  const portfolioQuery = useQuery({ queryKey: ['portfolio'], queryFn: async () => (await getPortfolio()).data })
  const assetsQuery = useQuery<HyperliquidAsset[]>({ queryKey: ['hyperliquid-assets'], queryFn: async () => (await getHyperliquidAssets()).data?.assets || [] })

  const priceQuery = useQuery({
    queryKey: ['hyperliquid-price', asset],
    queryFn: async () => (await getHyperliquidPrice(asset.split('-')[0] ?? '')).data?.price ?? null,
    enabled: Boolean(asset),
    refetchInterval: 670,
    refetchOnWindowFocus: false,
    retry: 1,
  })

  useEffect(() => {
    const price = priceQuery.data
    setCurrentPrice(price ?? null)
  }, [priceQuery.data])

  useEffect(() => {
    if (!currentPrice) return
    const liquidationPrice = direction === 'long'
      ? currentPrice * (1 - (1 / leverage) + MAINTENANCE_MARGIN)
      : currentPrice * (1 + (1 / leverage) - MAINTENANCE_MARGIN)
    const positionSize = ((portfolioQuery.data?.portfolio_size || 2000) * riskPercentage / 100 * leverage) / currentPrice
    const positionSizeDollars = positionSize * currentPrice
    const marginRequired = positionSizeDollars / leverage
    const estimatedLoss = (portfolioQuery.data?.portfolio_size || 2000) * riskPercentage / 100
    const tpProfits = takeProfits.filter(tp => tp.price > 0 && tp.allocation > 0).map((tp, index) => ({ ...tp, index: index + 1, profit: ((tp.price - currentPrice) * positionSize * tp.allocation / 100) * (direction === 'short' ? -1 : 1) }))
    const estimatedProfit = tpProfits.reduce((sum, tp) => sum + tp.profit, 0)
    const riskRewardRatio = estimatedLoss > 0 ? estimatedProfit / estimatedLoss : 0
    setTradeDetails({ liquidationPrice, positionSize, positionSizeDollars, marginRequired, riskRewardRatio, estimatedLoss, estimatedProfit, tpProfits, positionValue: positionSizeDollars, currentPrice })
  }, [currentPrice, direction, leverage, portfolioQuery.data?.portfolio_size, riskPercentage, takeProfits])

  const executeMutation = useMutation({
    mutationFn: async () => {
      if (normalizeMode(mode) !== 'live') {
        throw { error: 'mode_blocked', mode: 'planning' as const, reason: 'Trading is in planning mode. Switch to live mode to execute real trades.' }
      }
      if (!asset || !currentPrice) throw new Error('Please select an asset first')
      const trade = {
        asset,
        direction,
        leverage,
        entry_price: currentPrice,
        stop_loss: stopLoss ?? 0,
        position_size: tradeDetails?.positionSizeDollars ?? 0,
        take_profits: takeProfits,
        stop_losses: stopLoss ? [{ price: stopLoss, allocation: 100 }] : [],
        thesis,
      }
      await addTrade(trade)
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
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['closed-trades'] })
      await queryClient.invalidateQueries({ queryKey: ['portfolio'] })
      await queryClient.invalidateQueries({ queryKey: ['open-trades'] })
      await queryClient.invalidateQueries({ queryKey: ['mode'] })
      onTradeAdded?.()
      alert('Trade saved to journal and order placed on Hyperliquid!')
    },
    onError: (error) => {
      alert(getErrorMessage(error, 'Error executing trade'))
    },
  })

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
      <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
        <form onSubmit={(e) => e.preventDefault()} className="space-y-8">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-medium text-white">BTC-USDC</h3>
              <p className="text-xs text-neutral-400">Perpetual</p>
            </div>
            <div className="flex gap-1">
              <button type="button" onClick={() => setDirection('long')} className={direction === 'long' ? 'px-6 py-2 rounded-lg text-sm font-medium transition-colors text-green-400 border border-green-400/30' : 'px-6 py-2 rounded-lg text-sm font-medium transition-colors text-neutral-500 hover:text-neutral-300'}>Long</button>
              <button type="button" onClick={() => setDirection('short')} className={direction === 'short' ? 'px-6 py-2 rounded-lg text-sm font-medium transition-colors text-red-400 border border-red-400/30' : 'px-6 py-2 rounded-lg text-sm font-medium transition-colors text-neutral-500 hover:text-neutral-300'}>Short</button>
            </div>
          </div>
          <div className="flex items-center gap-6"><span className="text-sm text-neutral-400 w-20">Leverage</span><span className="text-sm text-white w-12">{leverage}x</span><input type="range" min="1" max={assetsQuery.data?.find(a => a.symbol === asset.split('-')[0])?.max_leverage ?? 50} value={leverage} onChange={(e) => setLeverage(parseInt(e.target.value))} className="flex-1 accent-neutral-500" /><span className="text-xs text-neutral-500">Max: {assetsQuery.data?.find(a => a.symbol === asset.split('-')[0])?.max_leverage ?? 50}x</span></div>
          <div className="space-y-3"><p className="text-xs text-neutral-500 uppercase tracking-wider">Take Profits</p>{takeProfits.map((tp, index) => (<div key={index} className="flex items-center gap-4"><input type="number" value={tp.price || ''} onChange={(e) => { const updated = [...takeProfits]; updated[index] = { ...updated[index], price: Number(e.target.value) || 0 }; setTakeProfits(updated) }} placeholder="Target price" step="0.01" className="flex-1 px-0 py-2 bg-transparent border-b border-neutral-700 text-white text-sm placeholder-neutral-600 focus:outline-none focus:border-green-400 transition-colors" /><input type="number" value={tp.allocation || ''} onChange={(e) => { const updated = [...takeProfits]; updated[index] = { ...updated[index], allocation: Number(e.target.value) || 0 }; setTakeProfits(updated) }} placeholder="%" min="0" max="100" step="1" className="w-16 px-0 py-2 bg-transparent border-b border-neutral-700 text-white text-sm placeholder-neutral-600 focus:outline-none focus:border-green-400 transition-colors" /></div>))}{numTakeProfits < 4 && <button type="button" onClick={() => { if (numTakeProfits >= 4) return; const newCount = numTakeProfits + 1; const equalAllocation = 100 / newCount; setNumTakeProfits(newCount); setTakeProfits(takeProfits.map(tp => ({ ...tp, allocation: equalAllocation })).concat({ price: 0, allocation: equalAllocation })) }} className="text-sm text-neutral-500 hover:text-green-400 transition-colors">+ Add target</button>}</div>
          <div className="space-y-3"><p className="text-xs text-neutral-500 uppercase tracking-wider">Stop Loss</p><input type="number" value={stopLoss === null ? undefined : stopLoss} onChange={(e) => setStopLoss(e.target.value ? Number(e.target.value) : null)} placeholder="Stop price" step="0.01" className="w-full px-0 py-2 bg-transparent border-b border-neutral-700 text-white text-sm placeholder-neutral-600 focus:outline-none focus:border-red-400 transition-colors" /></div>
          <div className="space-y-2"><p className="text-xs text-neutral-500 uppercase tracking-wider">Notes</p><textarea value={thesis} onChange={(e) => setThesis(e.target.value)} placeholder="Trade notes..." rows={3} className="w-full px-0 py-2 bg-transparent border-b border-neutral-700 text-white text-sm placeholder-neutral-600 focus:outline-none focus:border-white transition-colors resize-none" /></div>
        </form>
      </div>
      <div className="space-y-6">
        {tradeDetails && <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20 sticky top-8"><h3 className="text-sm font-medium text-neutral-400 mb-6">Trade Details</h3><div className="space-y-6"><div className="grid grid-cols-2 gap-4"><div><p className="text-xs text-neutral-500 mb-1">Entry Price</p><p className="text-xl font-light text-white">${currentPrice?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p></div><div><p className="text-xs text-neutral-500 mb-1">Liquidation Price</p><p className="text-xl font-light text-orange-400">${tradeDetails.liquidationPrice?.toFixed(2)}</p></div></div><div className="grid grid-cols-2 gap-4"><div><p className="text-xs text-neutral-500 mb-1">Position Size</p><p className="text-xl font-light text-white">${tradeDetails.positionSizeDollars?.toFixed(2)}</p><p className="text-sm text-neutral-400">({tradeDetails.positionSize?.toFixed(6)} BTC)</p></div><div><p className="text-xs text-neutral-500 mb-1">Margin Required</p><p className="text-xl font-light text-white">${tradeDetails.marginRequired?.toFixed(2)}</p></div></div><div className="grid grid-cols-2 gap-4"><div><p className="text-xs text-neutral-500 mb-1">Risk/Reward Ratio</p><p className="text-xl font-light text-white">1:{tradeDetails.riskRewardRatio?.toFixed(2)}</p></div><div><div className="flex items-baseline gap-3 mb-1"><p className="text-xs text-neutral-500">Risk Amount ({riskPercentage}%)</p><button onClick={() => { const newRisk = prompt('Enter risk percentage (1-100):', String(riskPercentage)); if (newRisk !== null) { const parsed = parseFloat(newRisk); if (!Number.isNaN(parsed) && parsed > 0 && parsed <= 100) setRiskPercentage(parsed) } }} className="text-[10px] text-neutral-500 hover:text-white transition-colors underline">Adjust</button></div><p className="text-xl font-light text-white">${((portfolioQuery.data?.portfolio_size || 2000) * riskPercentage / 100).toFixed(2)}</p></div></div><div className="grid grid-cols-2 gap-4"><div><p className="text-xs text-neutral-500 mb-1">Estimated Loss (SL)</p><p className="text-xl font-light text-red-400">${tradeDetails.estimatedLoss?.toFixed(2)}</p></div><div><p className="text-xs text-neutral-500 mb-2">Estimated Profit</p>{tradeDetails.tpProfits && tradeDetails.tpProfits.length > 0 && <div className="space-y-1">{tradeDetails.tpProfits.map((tp) => (<p key={tp.index} className="text-sm text-green-400">TP {tp.index} (${tp.price.toLocaleString()}): ${tp.profit.toFixed(2)}</p>))}<p className="text-sm font-medium text-green-400 pt-1 border-t border-neutral-700">Total: ${tradeDetails.estimatedProfit?.toFixed(2)}</p></div>}</div></div></div></div>}
        <div className="pt-2 flex justify-center">
          <button
            onClick={() => executeMutation.mutate()}
            disabled={executeMutation.isPending}
            className={`px-8 py-3 rounded-xl text-sm font-semibold border border-neutral-700/30 bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow ${
              mode === 'paper' 
                ? 'text-indigo-400 hover:text-indigo-300 shadow-indigo-500/10' 
                : 'text-emerald-400 hover:text-emerald-300 shadow-emerald-500/10'
            }`}
          >
            {executeMutation.isPending ? 'Executing...' : 'Execute Trade'}
          </button>
        </div>
      </div>
    </div>
  )
}
