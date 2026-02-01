import { useState, useEffect } from 'react'
import { addTrade } from '../api/trades'
import { getPortfolio } from '../api/portfolio'
import { getHyperliquidPrice, placeHyperliquidOrder, getHyperliquidAssets } from '../api/hyperliquid'

export default function PlanTrade({ onTradeAdded }) {
  const [asset, setAsset] = useState('')
  const [direction, setDirection] = useState('long')
  const [leverage, setLeverage] = useState(10)
  const [riskPercentage, setRiskPercentage] = useState(2.0)
  const [stopLoss, setStopLoss] = useState(null)
  const [numTakeProfits, setNumTakeProfits] = useState(0)
  const [takeProfits, setTakeProfits] = useState([])
  const [thesis, setThesis] = useState('')
  const [portfolioSize, setPortfolioSize] = useState(2000)
  const [currentPrice, setCurrentPrice] = useState(null)
  const [tradeDetails, setTradeDetails] = useState(null)
  const [assets, setAssets] = useState([])
  const [maxLeverage, setMaxLeverage] = useState(50)
  const [loading, setLoading] = useState(false)
  const [executeLoading, setExecuteLoading] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)

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
    const primarySL = stopLoss
    const slDistance = primarySL ? Math.abs(currentPrice - primarySL) : currentPrice * (1 / leverage)
    const slPercentage = slDistance / currentPrice
    const positionSizeDollars = primarySL ? riskAmount / slPercentage : riskAmount / (1 / leverage)
    const positionSizeUnits = positionSizeDollars / currentPrice
    const marginRequired = positionSizeDollars / leverage
    const positionValue = positionSizeDollars

    const liquidationPrice = direction === 'long'
      ? currentPrice * (1 - (1 / leverage))
      : currentPrice * (1 + (1 / leverage))

    // Calculate estimated P&L based on TP and SL
    let estimatedProfit = 0
    let estimatedLoss = 0
    let riskRewardRatio = 0
    const tpProfits = []

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
    if (primarySL) {
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

  const updateLastUpdated = () => {
    setLastUpdated(new Date().toISOString())
  }

  const handleAssetSelect = (selectedAsset) => {
    setAsset(selectedAsset)
    updateLastUpdated()
  }

  const handleAddTP = () => {
    if (numTakeProfits >= 4) return
    const newCount = numTakeProfits + 1
    const equalAllocation = 100 / newCount
    setNumTakeProfits(newCount)
    const updatedTPs = takeProfits.map(tp => ({ ...tp, allocation: equalAllocation }))
    updatedTPs.push({ price: 0, allocation: equalAllocation })
    setTakeProfits(updatedTPs)
  }

  const handleRemoveTP = (index) => {
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

  const handleTPChange = (index, field, value) => {
    const updated = [...takeProfits]
    updated[index] = { ...updated[index], [field]: parseFloat(value) || 0 }
    setTakeProfits(updated)
  }

  const handleExecuteTrade = async () => {
    if (!asset || !currentPrice) {
      alert('Please select an asset first')
      return
    }

    setExecuteLoading(true)
    try {
      // First save to journal
      const validTPs = takeProfits.filter(tp => tp.price > 0).map(tp => ({
        price: tp.price,
        allocation: tp.allocation / 100
      }))
      
      await addTrade({
        asset: asset,
        direction,
        entry_price: currentPrice,
        stop_loss: stopLoss || 0,
        position_size: tradeDetails?.positionSize || 0,
        take_profits: validTPs,
        stop_losses: stopLoss > 0 ? [{ price: stopLoss, allocation: 1.0 }] : [],
        thesis: thesis || null
      })

      // Then execute on Hyperliquid
      const isBuy = direction === 'long'
      const coin = asset.split('-')[0]
      
      // Prepare TP/SL data for Hyperliquid
      const tpData = validTPs.map(tp => ({
        price: tp.price,
        allocation: tp.allocation
      }))
      
      const slData = stopLoss > 0 ? [{ price: stopLoss, allocation: 1.0 }] : []
      
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

      updateLastUpdated()
      alert('Trade saved to journal and order placed on Hyperliquid!')
      
      if (onTradeAdded) {
        onTradeAdded()
      }
    } catch (error) {
      console.error('Error executing trade:', error)
      alert(error.response?.data?.detail || error.message || 'Error executing trade')
    } finally {
      setExecuteLoading(false)
    }
  }

  return (
    <div className="max-w-6xl mx-auto py-8 px-6">
      
      {/* Live Price Display */}
      {asset && currentPrice && (
        <div className="mb-6">
          <div className="flex items-baseline gap-3">
            <span className="text-4xl font-light tracking-tight text-white">
              ${currentPrice?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            <span className="text-sm text-neutral-500">
              {lastUpdated && new Date(lastUpdated).toLocaleTimeString()}
            </span>
          </div>
        </div>
      )}

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Column - Form */}
        <div className="lg:col-span-2 space-y-6">
          <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
            <form onSubmit={(e) => e.preventDefault()} className="space-y-8">
              
              {/* Asset + Direction */}
              <div className="flex gap-4">
                <select
                  value={asset}
                  onChange={(e) => handleAssetSelect(e.target.value)}
                  className="flex-1 px-4 py-3 bg-neutral-900 border border-neutral-700 rounded-lg text-white text-sm focus:outline-none focus:border-neutral-500 transition-colors"
                  required
                >
                  <option value="">Select Asset</option>
                  <option value="BTC-USDC">BTC-USDC</option>
                </select>
                
                {asset && (
                  <div className="flex gap-1">
                    <button
                      type="button"
                      onClick={() => setDirection('long')}
                      className={`px-6 py-3 rounded-lg text-sm font-medium transition-colors ${
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
                      className={`px-6 py-3 rounded-lg text-sm font-medium transition-colors ${
                        direction === 'short'
                          ? 'text-red-400 border border-red-400/30'
                          : 'text-neutral-500 hover:text-neutral-300'
                      }`}
                    >
                      Short
                    </button>
                  </div>
                )}
              </div>

              {/* Leverage */}
              {asset && (
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
              )}

              {/* Take Profits */}
              {asset && (
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
              )}

              {/* Stop Loss */}
              {asset && (
                <div className="space-y-3">
                  <p className="text-xs text-neutral-500 uppercase tracking-wider">Stop Loss</p>
                  <input
                    type="number"
                    value={stopLoss || ''}
                    onChange={(e) => setStopLoss(parseFloat(e.target.value) || null)}
                    placeholder="Stop price"
                    step="0.01"
                    className="w-full px-0 py-2 bg-transparent border-b border-neutral-700 text-white text-sm placeholder-neutral-600 focus:outline-none focus:border-red-400 transition-colors"
                  />
                </div>
              )}

              {/* Notes */}
              {asset && (
                <div className="space-y-2">
                  <p className="text-xs text-neutral-500 uppercase tracking-wider">Notes</p>
                  <textarea
                    value={thesis}
                    onChange={(e) => setThesis(e.target.value)}
                    placeholder="Trade notes..."
                    rows="3"
                    className="w-full px-0 py-2 bg-transparent border-b border-neutral-700 text-white text-sm placeholder-neutral-600 focus:outline-none focus:border-white transition-colors resize-none"
                  />
                </div>
              )}
            </form>
          </div>
        </div>

        {/* Right Column - Trade Details */}
        {tradeDetails && asset && (
          <div className="lg:col-span-1">
            <div className="sticky top-8 border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
              <h3 className="text-sm font-medium text-neutral-400 mb-6">Trade Details</h3>
              
              <div className="space-y-6">
                <div>
                  <p className="text-xs text-neutral-500 mb-1">Entry Price</p>
                  <p className="text-xl font-light text-white">
                    ${currentPrice?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </p>
                </div>

                <div>
                  <p className="text-xs text-neutral-500 mb-1">Position Size</p>
                  <p className="text-xl font-light text-white">
                    ${tradeDetails.positionSizeDollars?.toFixed(2)}
                  </p>
                  <p className="text-sm text-neutral-400">
                    ({tradeDetails.positionSize?.toFixed(6)} {asset.split('-')[0]})
                  </p>
                </div>

                <div>
                  <p className="text-xs text-neutral-500 mb-1">Margin Required</p>
                  <p className="text-xl font-light text-white">
                    ${tradeDetails.marginRequired?.toFixed(2)}
                  </p>
                </div>

                <div>
                  <p className="text-xs text-neutral-500 mb-1">Liquidation Price</p>
                  <p className="text-xl font-light text-orange-400">
                    ${tradeDetails.liquidationPrice?.toFixed(2)}
                  </p>
                </div>

                <div>
                  <div className="flex items-baseline gap-3 mb-1">
                    <p className="text-xs text-neutral-500">Risk Amount ({riskPercentage}%)</p>
                    <button
                      onClick={() => {
                        const newRisk = prompt('Enter risk percentage (1-100):', riskPercentage)
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
                    ${(portfolioSize * riskPercentage / 100)?.toFixed(2)}
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
                        Total Profit: ${tradeDetails.estimatedProfit?.toFixed(2)}
                      </p>
                    </div>
                  )}
                </div>

                <div>
                  <p className="text-xs text-neutral-500 mb-1">Estimated Loss (SL)</p>
                  <p className="text-xl font-light text-red-400">
                    ${tradeDetails.estimatedLoss?.toFixed(2)}
                  </p>
                </div>

                <div>
                  <p className="text-xs text-neutral-500 mb-1">Risk/Reward Ratio</p>
                  <p className="text-xl font-light text-white">
                    1:{tradeDetails.riskRewardRatio?.toFixed(2)}
                  </p>
                </div>
              </div>
              

            </div>
          </div>
        )}
      </div>

      {/* Execute Trade Button - Full Width */}
      {asset && (
        <div className="mt-6 flex justify-center">
          <button
            onClick={handleExecuteTrade}
            disabled={executeLoading}
            className="px-8 py-2 text-sm text-neutral-400 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {executeLoading ? 'Executing...' : 'Execute Trade'}
          </button>
        </div>
      )}

    </div>
  )
}
