import { useState, useEffect, type ChangeEvent } from 'react'
import { addTrade } from '../api/trades'
import { getPortfolio } from '../api/portfolio'
import { getHyperliquidPrice, placeHyperliquidOrder, getHyperliquidAssets } from '../api/hyperliquid'
import type { ApiError, HyperliquidAsset, TakeProfit, TradeDetails } from '../types'

// Hyperliquid maintenance margin: 1.25% for BTC (40x max leverage -> 1/(2*40))
const MAINTENANCE_MARGIN = 0.0125

export default function PlanTrade({ onTradeAdded }: { onTradeAdded?: () => void }) {
  const [asset, setAsset] = useState('BTC-USDC')
  const [direction, setDirection] = useState('long')
  const [leverage, setLeverage] = useState(10)
  const [riskPercentage, setRiskPercentage] = useState(2.0)
  const [stopLoss, setStopLoss] = useState<number | null>(null)
  const [numTakeProfits, setNumTakeProfits] = useState(0)
  const [takeProfits, setTakeProfits] = useState<TakeProfit[]>([])
  const [thesis, setThesis] = useState('')
  const [portfolioSize, setPortfolioSize] = useState(2000)
  const [currentPrice, setCurrentPrice] = useState<number | null>(null)
  const [tradeDetails, setTradeDetails] = useState<TradeDetails | null>(null)
  const [assets, setAssets] = useState<HyperliquidAsset[]>([])
  const [maxLeverage, setMaxLeverage] = useState(50)
  const [loading, setLoading] = useState(false)
  const [executeLoading, setExecuteLoading] = useState(false)

  useEffect(() => {
    const fetchPortfolio = async () => {
      try {
        const res = await getPortfolio()
        if (res.data?.portfolio_size) {
          setPortfolioSize(res.data.portfolio_size)
        }
      } catch (err) {
        console.error('Error fetching portfolio:', err)
      }
    }
    fetchPortfolio()
  }, [])

  // Fetch available assets and their max leverage
  useEffect(() => {
    const fetchAssets = async () => {
      try {
        const res = await getHyperliquidAssets()
        if (res.data?.assets) {
          setAssets(res.data.assets)
        }
      } catch (err) {
        console.error('Error fetching assets:', err)
      }
    }
    fetchAssets()
  }, [])

  // Update max leverage when asset changes
  useEffect(() => {
    if (!asset || assets.length === 0) return
    
    const coin = asset.split('-')[0]
    const assetData = assets.find(a => a.symbol === coin)
    
    if (assetData) {
      const newMaxLeverage = assetData.max_leverage
      setMaxLeverage(newMaxLeverage)
      
      // If current leverage exceeds new max, cap it
      if (leverage > newMaxLeverage) {
        setLeverage(newMaxLeverage)
      }
    }
  }, [asset, assets])

  useEffect(() => {
    if (!asset) {
      setCurrentPrice(null)
      setTradeDetails(null)
      return
    }

    const fetchPrice = async () => {
      try {
        const res = await getHyperliquidPrice(asset.split('-')[0])
        const price = res.data?.price
        if (price) {
          setCurrentPrice(price)
        }
      } catch (err) {
        console.error('Error fetching price:', err)
      }
    }

    fetchPrice()
    const interval = setInterval(fetchPrice, 1000)
    return () => clearInterval(interval)
  }, [asset])

  useEffect(() => {
    if (!asset || !currentPrice || leverage <= 0) {
      setTradeDetails(null)
      return
    }

    const riskAmount = portfolioSize * (riskPercentage / 100)
    
    // Get primary stop loss
    const primarySL = stopLoss ?? undefined
    const slDistance = primarySL !== undefined ? Math.abs(currentPrice - primarySL) : currentPrice * (1 / leverage)
    const slPercentage = slDistance / currentPrice
    const positionSizeDollars = primarySL ? riskAmount / slPercentage : riskAmount / (1 / leverage)
    const positionSizeUnits = positionSizeDollars / currentPrice
    const marginRequired = positionSizeDollars / leverage
    const positionValue = positionSizeDollars

    // Liquidation price with maintenance margin (Hyperliquid formula)
    // Liquidation % = (1/leverage) - maintenance_margin
    const liquidationThreshold = (1 / leverage) - MAINTENANCE_MARGIN
    const liquidationPrice = direction === 'long'
      ? currentPrice * (1 - liquidationThreshold)
      : currentPrice * (1 + liquidationThreshold)

    // Calculate estimated P&L based on TP and SL
    let estimatedProfit = 0
    let estimatedLoss = 0
    let riskRewardRatio = 0
    const tpProfits: Array<{ index: number; price: number; allocation: number; profit: number }> = []

    // Calculate profit from take profits (individual and total)
    if (takeProfits && takeProfits.length > 0) {
      takeProfits.forEach((tp, index) => {
        if (tp.price > 0 && tp.allocation > 0) {
          const allocation = tp.allocation / 100
          const tpSize = positionSizeUnits * allocation
          let priceDiff = 0
          if (direction === 'long') {
            priceDiff = tp.price - currentPrice
          } else {
            priceDiff = currentPrice - tp.price
          }
          const tpProfit = tpSize * priceDiff
          estimatedProfit += tpProfit
          tpProfits.push({
            index: index + 1,
            price: tp.price,
            allocation: tp.allocation,
            profit: tpProfit
          })
        }
      })
    }

    // Calculate loss from stop loss (single) or use margin if no SL
    if (primarySL !== null && primarySL !== undefined) {
      let priceDiff = 0
      if (direction === 'long') {
        priceDiff = currentPrice - primarySL
      } else {
        priceDiff = primarySL - currentPrice
      }
      estimatedLoss = positionSizeUnits * priceDiff
    } else {
      // No SL set - estimated loss is the margin (liquidation scenario)
      estimatedLoss = marginRequired
    }

    // Calculate R:R ratio
    if (estimatedLoss > 0) {
      riskRewardRatio = estimatedProfit / estimatedLoss
    }

    setTradeDetails({
      positionSize: positionSizeUnits,
      positionSizeDollars,
      marginRequired,
      positionValue,
      liquidationPrice,
      currentPrice,
      estimatedProfit,
      estimatedLoss,
      riskRewardRatio,
      tpProfits
    })
  }, [asset, currentPrice, leverage, direction, stopLoss, takeProfits, riskPercentage, portfolioSize])

  const handleAssetSelect = (selectedAsset: string): void => {
    setAsset(selectedAsset)
  }

  const handleAddTP = (): void => {
    if (numTakeProfits >= 4) return
    const newCount = numTakeProfits + 1
    const equalAllocation = 100 / newCount
    setNumTakeProfits(newCount)
    const updatedTPs = takeProfits.map(tp => ({ ...tp, allocation: equalAllocation }))
    updatedTPs.push({ price: 0, allocation: equalAllocation })
    setTakeProfits(updatedTPs)
  }

  const handleRemoveTP = (index: number): void => {
    const updatedTPs = takeProfits.filter((_, i) => i !== index)
    if (updatedTPs.length > 0) {
      const equalAllocation = 100 / updatedTPs.length
      const reallocatedTPs = updatedTPs.map(tp => ({ ...tp, allocation: equalAllocation }))
      setTakeProfits(reallocatedTPs)
    } else {
      setTakeProfits([])
    }
    setNumTakeProfits(updatedTPs.length)
  }

  const handleTPChange = (index: number, field: keyof TakeProfit, value: string): void => {
    const updated = [...takeProfits]
    updated[index] = {
      ...updated[index],
      [field]: Number(value) || 0,
    } as TakeProfit
    setTakeProfits(updated)
  }

  const handleExecuteTrade = async (): Promise<void> => {
    if (!asset || !currentPrice) {
      alert('Please select an asset first')
      return
    }

    setExecuteLoading(true)
    try {
      // First save to journal
      const validTPs: TakeProfit[] = takeProfits.filter((tp): tp is TakeProfit => tp.price > 0).map(tp => ({
        price: tp.price,
        allocation: tp.allocation / 100
      }))
      
      await addTrade({
        asset: asset,
        direction,
        entry_price: currentPrice,
        stop_loss: stopLoss ?? 0,
        position_size: tradeDetails?.positionSize ?? 0,
        take_profits: validTPs,
        stop_losses: (stopLoss ?? 0) > 0 ? [{ price: stopLoss ?? 0, allocation: 1.0 }] : [],
        thesis: thesis || null,
        margin: tradeDetails?.marginRequired ?? (((tradeDetails?.positionSize ?? 0) / leverage) || 0),
        leverage: leverage
      })

      // Then execute on Hyperliquid
      const isBuy = direction === 'long'
      const coin = asset.split('-')[0]
      
      // Prepare TP/SL data for Hyperliquid
      const tpData = validTPs.map(tp => ({
        price: tp.price,
        allocation: tp.allocation
      }))
      
      const slData = (stopLoss ?? 0) > 0 ? [{ price: stopLoss ?? 0, allocation: 1.0 }] : []
      
      const response = await placeHyperliquidOrder({
        coin: coin,
        is_buy: isBuy,
        margin_amount: tradeDetails?.marginRequired || 1,
        leverage: leverage,
        entry_price: currentPrice,
        take_profits: tpData,
        stop_losses: slData,
        is_isolated: true
      })

      alert('Trade saved to journal and order placed on Hyperliquid!')
      
      if (onTradeAdded) {
        onTradeAdded()
      }
    } catch (error) {
      const err = error as ApiError
      console.error('Error executing trade:', error)
      alert(err.response?.data?.detail || (error instanceof Error ? error.message : 'Error executing trade'))
    } finally {
      setExecuteLoading(false)
    }
  }

  return (
    <div>
      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Column - Form */}
        <div className="lg:col-span-2 space-y-6">
          <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
            <form onSubmit={(e) => e.preventDefault()} className="space-y-8">
              
              {/* Trading Pair & Direction */}
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-medium text-white">BTC-USDC</h3>
                  <p className="text-xs text-neutral-400">Perpetual</p>
                </div>
                
                <div className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => setDirection('long')}
                    className={`px-6 py-2 rounded-lg text-sm font-medium transition-colors ${
                      direction === 'long'
                        ? 'text-green-400 border border-green-400/30'
                        : 'text-neutral-500 hover:text-neutral-300'
                    }`}
                  >
                    Long
                  </button>
                  <button
                    type="button"
                    onClick={() => setDirection('short')}
                    className={`px-6 py-2 rounded-lg text-sm font-medium transition-colors ${
                      direction === 'short'
                        ? 'text-red-400 border border-red-400/30'
                        : 'text-neutral-500 hover:text-neutral-300'
                    }`}
                  >
                    Short
                  </button>
                </div>
              </div>

              {/* Leverage */}
              <div className="flex items-center gap-6">
                <span className="text-sm text-neutral-400 w-20">Leverage</span>
                <span className="text-sm text-white w-12">{leverage}x</span>
                <input
                  type="range"
                  min="1"
                  max={maxLeverage}
                  value={leverage}
                  onChange={(e) => setLeverage(parseInt(e.target.value))}
                  className="flex-1 accent-neutral-500"
                />
                <span className="text-xs text-neutral-500">Max: {maxLeverage}x</span>
              </div>

              {/* Take Profits */}
              <div className="space-y-3">
                <p className="text-xs text-neutral-500 uppercase tracking-wider">Take Profits</p>
                {takeProfits.map((tp, index) => (
                  <div key={index} className="flex items-center gap-4">
                    <input
                      type="number"
                      value={tp.price || ''}
                      onChange={(e) => handleTPChange(index, 'price', e.target.value)}
                      placeholder="Target price"
                      step="0.01"
                      className="flex-1 px-0 py-2 bg-transparent border-b border-neutral-700 text-white text-sm placeholder-neutral-600 focus:outline-none focus:border-green-400 transition-colors"
                    />
                    <input
                      type="number"
                      value={tp.allocation || ''}
                      onChange={(e) => handleTPChange(index, 'allocation', e.target.value)}
                      placeholder="%"
                      min="0"
                      max="100"
                      step="1"
                      className="w-16 px-0 py-2 bg-transparent border-b border-neutral-700 text-white text-sm placeholder-neutral-600 focus:outline-none focus:border-green-400 transition-colors"
                    />
                    <button
                      type="button"
                      onClick={() => handleRemoveTP(index)}
                      className="text-neutral-500 hover:text-neutral-300 text-sm px-2"
                    >
                      ×
                    </button>
                  </div>
                ))}
                {numTakeProfits < 4 && (
                  <button
                    type="button"
                    onClick={handleAddTP}
                    className="text-sm text-neutral-500 hover:text-green-400 transition-colors"
                  >
                    + Add target
                  </button>
                )}
              </div>

              {/* Stop Loss */}
              <div className="space-y-3">
                <p className="text-xs text-neutral-500 uppercase tracking-wider">Stop Loss</p>
                <input
                  type="number"
                  value={stopLoss === null ? undefined : stopLoss}
                  onChange={(e) => setStopLoss(e.target.value ? Number(e.target.value) : null)}
                  placeholder="Stop price"
                  step="0.01"
                  className="w-full px-0 py-2 bg-transparent border-b border-neutral-700 text-white text-sm placeholder-neutral-600 focus:outline-none focus:border-red-400 transition-colors"
                />
              </div>

              {/* Notes */}
              <div className="space-y-2">
                <p className="text-xs text-neutral-500 uppercase tracking-wider">Notes</p>
                <textarea
                  value={thesis}
                  onChange={(e) => setThesis(e.target.value)}
                  placeholder="Trade notes..."
                  rows={3}
                  className="w-full px-0 py-2 bg-transparent border-b border-neutral-700 text-white text-sm placeholder-neutral-600 focus:outline-none focus:border-white transition-colors resize-none"
                />
              </div>
            </form>
          </div>
        </div>

        {/* Right Column - Trade Details */}
        {tradeDetails && (
          <div className="lg:col-span-1">
            <div className="sticky top-8 border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
              <h3 className="text-sm font-medium text-neutral-400 mb-6">Trade Details</h3>
              
              <div className="space-y-6">
                {/* Row 1: Entry Price | Liquidation Price */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-neutral-500 mb-1">Entry Price</p>
                    <p className="text-xl font-light text-white">
                      ${currentPrice?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-neutral-500 mb-1">Liquidation Price</p>
                    <p className="text-xl font-light text-orange-400">
                      ${tradeDetails.liquidationPrice?.toFixed(2)}
                    </p>
                  </div>
                </div>

                {/* Row 2: Position Size | Margin Required */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-neutral-500 mb-1">Position Size</p>
                    <p className="text-xl font-light text-white">
                      ${tradeDetails.positionSizeDollars?.toFixed(2)}
                    </p>
                    <p className="text-sm text-neutral-400">
                      ({tradeDetails.positionSize?.toFixed(6)} BTC)
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-neutral-500 mb-1">Margin Required</p>
                    <p className="text-xl font-light text-white">
                      ${tradeDetails.marginRequired?.toFixed(2)}
                    </p>
                  </div>
                </div>

                {/* Row 3: Risk/Reward Ratio | Risk Amount */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-neutral-500 mb-1">Risk/Reward Ratio</p>
                    <p className="text-xl font-light text-white">
                      1:{tradeDetails.riskRewardRatio?.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <div className="flex items-baseline gap-3 mb-1">
                      <p className="text-xs text-neutral-500">Risk Amount ({riskPercentage}%)</p>
                      <button
                        onClick={() => {
                          const newRisk = prompt('Enter risk percentage (1-100):', String(riskPercentage))
                          if (newRisk !== null) {
                            const parsed = parseFloat(newRisk)
                            if (!isNaN(parsed) && parsed > 0 && parsed <= 100) {
                              setRiskPercentage(parsed)
                            }
                          }
                        }}
                        className="text-[10px] text-neutral-500 hover:text-white transition-colors underline"
                      >
                        Adjust
                      </button>
                    </div>
                    <p className="text-xl font-light text-white">
                      ${(portfolioSize * riskPercentage / 100).toFixed(2)}
                    </p>
                  </div>
                </div>

                {/* Row 4: Estimated Loss | Estimated Profit */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-neutral-500 mb-1">Estimated Loss (SL)</p>
                    <p className="text-xl font-light text-red-400">
                      ${tradeDetails.estimatedLoss?.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-neutral-500 mb-2">Estimated Profit</p>
                    {tradeDetails.tpProfits && tradeDetails.tpProfits.length > 0 && (
                      <div className="space-y-1">
                        {tradeDetails.tpProfits.map((tp) => (
                          <p key={tp.index} className="text-sm text-green-400">
                            TP {tp.index} (${tp.price.toLocaleString()}): ${tp.profit.toFixed(2)}
                          </p>
                        ))}
                        <p className="text-sm font-medium text-green-400 pt-1 border-t border-neutral-700">
                          Total: ${tradeDetails.estimatedProfit?.toFixed(2)}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
              

            </div>
          </div>
        )}
      </div>

      {/* Execute Trade Button - Full Width */}
      <div className="mt-6 flex justify-center">
        <button
          onClick={handleExecuteTrade}
          disabled={executeLoading}
          className="px-8 py-2 text-sm text-neutral-400 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {executeLoading ? 'Executing...' : 'Execute Trade'}
        </button>
      </div>
    </div>
  )
}
