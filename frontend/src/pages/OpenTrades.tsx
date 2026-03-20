import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { getOpenTrades, closeTrade, partialCloseTrade, stopLossHit } from '../api/trades'
import { getHyperliquidPrice, closeHyperliquidPosition } from '../api/hyperliquid'
import { TradeCardSkeleton } from '../components/LoadingSkeleton'
import { useMode } from '../contexts/ModeContext'
import type { Trade, ApiError } from '../types'

type TradeWithIndex = Trade & { index: number }

const OpenTrades = forwardRef(function OpenTrades(_props, ref) {
  const { mode } = useMode()
  const [trades, setTrades] = useState<Trade[]>([])
  const [selectedTrade, setSelectedTrade] = useState<TradeWithIndex | null>(null)
  const [selectedTradeForDetail, setSelectedTradeForDetail] = useState<Trade | null>(null)
  const [showCloseModal, setShowCloseModal] = useState(false)
  const [closeOnHyperliquid, setCloseOnHyperliquid] = useState(true)
  const [isClosing, setIsClosing] = useState(false)
  const [showTPModal, setShowTPModal] = useState(false)
  const [showSLModal, setShowSLModal] = useState(false)
  const [showTradeDetailModal, setShowTradeDetailModal] = useState(false)

  const [loading, setLoading] = useState(true)
  const [currentPrices, setCurrentPrices] = useState<Record<string, number>>({})
  const isInitialMount = useRef(true)

  // Fetch current prices for all open trades
  const fetchCurrentPrices = useCallback(async (tradesList: Trade[]) => {
    const prices: Record<string, number> = {}
    const uniqueAssets = [...new Set(tradesList.map((t: Trade) => t.Asset).filter((asset): asset is string => Boolean(asset)))] as string[]
    
    await Promise.all(
      uniqueAssets.map(async (asset: string) => {
        try {
          // Extract coin name from asset (e.g., "BTC" from "BTC-USDC")
          const coin = asset.split('-')[0] ?? ''
          const res = await getHyperliquidPrice(coin)
          if (res.data?.price) {
            prices[asset] = res.data.price
          }
        } catch (error) {
          console.error(`Error fetching price for ${asset}:`, error)
        }
      })
    )
    
    setCurrentPrices(prices)
  }, [])

  const loadTrades = useCallback(async (showLoading = true) => {
    try {
      if (showLoading && isInitialMount.current) {
        setLoading(true)
      }
      
      const res = await getOpenTrades()
      const tradesData: Trade[] = res.data?.trades || []
      setTrades(tradesData)
      isInitialMount.current = false
      
      // Fetch current prices for P&L calculation
      if (tradesData.length > 0) {
        fetchCurrentPrices(tradesData)
      }
    } catch (error) {
      console.error('Error loading trades:', error)
      setTrades([])
      isInitialMount.current = false
    } finally {
      setLoading(false)
    }
  }, [fetchCurrentPrices])

  useEffect(() => {
    loadTrades()
    
    // Poll prices every 670ms
    const interval = setInterval(() => {
      if (trades.length > 0) {
        fetchCurrentPrices(trades)
      }
    }, 670)
    
    return () => clearInterval(interval)
  }, [loadTrades, fetchCurrentPrices, trades.length])

  useImperativeHandle(ref, () => ({
    loadTrades: () => loadTrades(false)
  }))

  // Calculate unrealized P&L
  const calculatePnL = (trade: Trade) => {
    const asset = trade.Asset ?? ''
    const currentPrice = asset ? currentPrices[asset] : undefined
    if (!currentPrice || !trade.Entry) return null
    
    const entry = typeof trade.Entry === 'number' ? trade.Entry : parseFloat(String(trade.Entry ?? 0))
    const positionSize = typeof trade.Position_Size === 'number' ? trade.Position_Size : parseFloat(String(trade.Position_Size ?? 0)) || 0
    
    if (trade.Direction?.toLowerCase() === 'long') {
      return (currentPrice - entry) * (positionSize / entry)
    } else {
      return (entry - currentPrice) * (positionSize / entry)
    }
  }

  // Calculate liquidation price with maintenance margin (Hyperliquid formula)
  // MM = 1.25% for BTC (40x max leverage assets)
  const MAINTENANCE_MARGIN = 0.0125
  
  const calculateLiquidationPrice = (trade: Trade) => {
    const entry = typeof trade.Entry === 'number' ? trade.Entry : parseFloat(String(trade.Entry ?? 0))
    const leverage = typeof trade.Leverage === 'number' ? trade.Leverage : parseFloat(String(trade.Leverage ?? 0)) || 1
    
    if (!entry || !leverage) return null
    
    // Liquidation threshold = (1/leverage) - maintenance_margin
    const liquidationThreshold = (1 / leverage) - MAINTENANCE_MARGIN
    
    if (trade.Direction?.toLowerCase() === 'long') {
      return entry * (1 - liquidationThreshold)
    } else {
      return entry * (1 + liquidationThreshold)
    }
  }

  const handleCloseTrade = useCallback(async (): Promise<void> => {
    if (!selectedTrade) {
      alert('No trade selected')
      return
    }

    if (isClosing) {
      return
    }

    const tradeIndex = selectedTrade.index
    const asset = selectedTrade.Asset
    if (!asset) return
    // Extract coin name from asset (e.g., "BTC" from "BTC-USDC")
    const coin = asset.split('-')[0] ?? ''
    
    console.log(`[INFO] Attempting to close trade: index=${tradeIndex}, asset=${asset}, coin=${coin}`)
    console.log(`[INFO] selectedTrade:`, selectedTrade)
    console.log(`[INFO] Current trades:`, trades)
    
    setIsClosing(true)
    
    // Close position on Hyperliquid if requested and in live mode
    let fillPrice
    if (closeOnHyperliquid && mode === 'live') {
      try {
        console.log(`[INFO] Closing position on Hyperliquid for ${coin}...`)
        const response = await closeHyperliquidPosition(coin)
        console.log(`[INFO] Hyperliquid response:`, response.data)
        
        if (!response.data) {
          throw new Error('No response data from Hyperliquid API')
        }
        
        if (response.data?.status !== 'success') {
          throw new Error(response.data?.message || 'Failed to close position')
        }
        
        // Get the actual fill price from Hyperliquid response
        fillPrice = response.data?.fill_price
        if (!fillPrice || fillPrice <= 0) {
          throw new Error(`Invalid fill price from Hyperliquid: ${fillPrice}`)
        }
        
        console.log(`[INFO] Position closed on Hyperliquid at $${fillPrice.toFixed(2)}`)
      } catch (error) {
        console.error('[ERROR] Error closing Hyperliquid position:', error)
        const err = error as ApiError
        const errorMsg = err.response?.data?.detail || (error instanceof Error ? error.message : 'Unknown error')
        console.error('[ERROR] Error details:', errorMsg)
        
        // Ask user if they want to continue closing in journal despite Hyperliquid error
        const continueAnyway = confirm(
          `Error closing position on Hyperliquid:\n${errorMsg}\n\nDo you want to continue and close the trade in the journal anyway?`
        )
        if (!continueAnyway) {
          return
        }
        // Fall through to close in journal with current price
      }
    }
    
    // If no fill price from Hyperliquid (either skipped or failed), use current market price
    if (!fillPrice) {
      const currentPrice = asset ? currentPrices[asset] : undefined
      console.log(`[INFO] Current price lookup: asset=${asset}, currentPrices=`, currentPrices)
      if (currentPrice) {
        fillPrice = currentPrice
        console.log(`[INFO] Using current market price: $${fillPrice.toFixed(2)}`)
      } else {
        console.error('[ERROR] No current price found for asset:', asset)
        alert(`Could not determine price for closing trade: ${asset}`)
        return
      }
    }

    // Close trade in journal at the fill price
    console.log(`[INFO] Closing trade in journal: index=${tradeIndex}, fillPrice=$${fillPrice.toFixed(2)}`)
    setShowCloseModal(false)
    setSelectedTrade(null)
    setCloseOnHyperliquid(true)

    try {
      console.log(`[INFO] Calling closeTrade API with: tradeIndex=${tradeIndex}, exitPrice=${fillPrice}`)
      const closeResult = await closeTrade(tradeIndex, fillPrice)
      console.log(`[INFO] closeTrade API response:`, closeResult)
      console.log(`[INFO] Trade successfully closed in journal`)
      // Immediately remove the trade from local state while we reload from backend
      setTrades((prev: Trade[]) => prev.filter((_, idx) => {
        const actualIndex = prev[idx]._index !== undefined ? prev[idx]._index : idx
        console.log(`[DEBUG] Checking trade at index ${idx}: actualIndex=${actualIndex}, tradeIndex=${tradeIndex}, keep=${actualIndex !== tradeIndex}`)
        return actualIndex !== tradeIndex
      }))
      // Then reload from backend to ensure consistency
      console.log(`[INFO] Reloading trades from backend...`)
      await loadTrades()
      console.log(`[INFO] Trades reloaded successfully`)
      alert(`Trade closed successfully at $${fillPrice.toFixed(2)}`)
    } catch (error) {
      const err = error as ApiError
      console.error('[ERROR] Error closing trade in journal:', error)
      console.error('[ERROR] Full error object:', JSON.stringify(error, null, 2))
      const errorMsg = err.response?.data?.detail || (error instanceof Error ? error.message : 'Error closing trade in journal')
      alert(`Error: ${errorMsg}`)
    } finally {
      setIsClosing(false)
    }
  }, [selectedTrade, loadTrades, closeOnHyperliquid, currentPrices])

  const handleTPHit = useCallback(async (tpIndex: number): Promise<void> => {
    if (!selectedTrade) return

    const tradeIndex = selectedTrade.index
    const originalTrades = [...trades]

    setTrades((prev: Trade[]) => prev.map((trade) => {
      const actualIndex = trade._index !== undefined ? trade._index : prev.indexOf(trade)
      if (actualIndex === tradeIndex) {
        const hitTPs = JSON.parse(trade.Hit_TPs || '[]')
        return {
          ...trade,
          Hit_TPs: JSON.stringify([...hitTPs, tpIndex])
        }
      }
      return trade
    }))
    setShowTPModal(false)
    setSelectedTrade(null)

    try {
      const tps = JSON.parse(selectedTrade.TPs || '[]') as Array<{ price: number; allocation: number }>
      const tp = tps[tpIndex]
      await partialCloseTrade(tradeIndex, tp.price, tp.allocation, tpIndex)
      await loadTrades()
    } catch (error) {
      const err = error as ApiError
      setTrades(originalTrades)
      alert(err.response?.data?.detail || 'Error recording TP hit')
    }
  }, [selectedTrade, trades, loadTrades])

  const handleSLHit = useCallback(async (slIndex: number, slPrice: number, slAllocation: number): Promise<void> => {
    if (!selectedTrade) return

    const tradeIndex = selectedTrade.index
    const originalTrades = [...trades]

    setTrades((prev: Trade[]) => prev.map((trade) => {
      const actualIndex = trade._index !== undefined ? trade._index : prev.indexOf(trade)
      if (actualIndex === tradeIndex) {
        return {
          ...trade,
          SL_Hit: true,
          SL_Price: slPrice
        }
      }
      return trade
    }))
    setShowSLModal(false)
    setSelectedTrade(null)

    try {
      await stopLossHit(tradeIndex, slPrice, slAllocation, slIndex)
      await loadTrades()
    } catch (error) {
      const err = error as ApiError
      setTrades(originalTrades)
      alert(err.response?.data?.detail || 'Error recording SL hit')
    }
  }, [selectedTrade, trades, loadTrades])

  if (loading) {
    return (
      <div className="w-full py-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <TradeCardSkeleton key={i} />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="w-full">
      {trades.length === 0 ? (
        <div className="text-center py-8 text-neutral-500 text-sm">
          No open trades
        </div>
      ) : (
        <div className={`grid gap-4 ${
          trades.length === 1 ? 'grid-cols-1' : 
          trades.length === 2 ? 'grid-cols-2' : 
          'grid-cols-3'
        }`}>
          {trades.map((trade, index) => {
            const actualIndex = trade._index !== undefined ? trade._index : trades.findIndex(t => t === trade)
            const tps = JSON.parse(trade.TPs || '[]')
            const sls = JSON.parse(trade.SLs || '[]')
            const hitTPs = JSON.parse(trade.Hit_TPs || '[]')
            const pnl = calculatePnL(trade)
            const liqPrice = calculateLiquidationPrice(trade)
            const margin = (typeof trade.Margin === 'number' ? trade.Margin : parseFloat(String(trade.Margin ?? 0))) || ((typeof trade.Position_Size === 'number' ? trade.Position_Size : parseFloat(String(trade.Position_Size ?? 0))) / (typeof trade.Leverage === 'number' ? trade.Leverage : parseFloat(String(trade.Leverage ?? 1)) || 1))
            
            return (
              <div 
                key={index} 
                className="group p-4 glass-card hover:bg-white/[0.04] transition-colors cursor-pointer"
                onClick={() => {
                  setSelectedTradeForDetail(trade)
                  setShowTradeDetailModal(true)
                }}
              >
                {/* Header: Asset + Direction + PnL */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-medium text-white">{trade.Asset}</h3>
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      trade.Direction?.toLowerCase() === 'long'
                        ? 'bg-green-500/10 text-green-400'
                        : 'bg-red-500/10 text-red-400'
                    }`}>
                      {trade.Direction?.toUpperCase()}
                    </span>
                  </div>
                  <p className={`text-sm font-medium ${pnl !== null ? (pnl >= 0 ? 'text-green-400' : 'text-red-400') : 'text-neutral-400'}`}>
                    {pnl !== null
                      ? (() => {
                          const pnlPercent = margin > 0 ? (pnl / margin) * 100 : 0
                          return `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} (${pnl >= 0 ? '+' : ''}${pnlPercent.toFixed(1)}%)`
                        })()
                      : '-'
                    }
                  </p>
                </div>

                {/* Entry / Current */}
                <div className="flex items-center justify-between text-sm mb-3">
                  <div>
                    <span className="text-neutral-500">Entry: </span>
                    <span className="text-neutral-300">${trade.Entry?.toFixed(0)}</span>
                  </div>
                  <div>
                    <span className="text-neutral-500">Current: </span>
                    <span className="text-neutral-300">
                      {trade.Asset && currentPrices[trade.Asset] 
                        ? `$${currentPrices[trade.Asset].toFixed(0)}`
                        : '-'
                      }
                    </span>
                  </div>
                </div>

                {/* Position Details */}
                <div className="text-sm text-neutral-400 mb-3">
                  <div className="flex justify-between">
                    <span>Size: ${typeof trade.Position_Size === 'number' ? trade.Position_Size.toFixed(0) : '-'}</span>
                    <span>Margin: ${margin?.toFixed(0) || '-'}</span>
                  </div>
                  {liqPrice && (
                    <div className="text-neutral-500 mt-1">
                      Liq: ${liqPrice.toFixed(0)}
                    </div>
                  )}
                </div>

                {/* TP/SL Summary */}
                {(tps.length > 0 || sls.length > 0 || (trade.SL ?? 0) > 0) && (
                  <div className="text-sm text-neutral-500 mb-3">
                    {tps.length > 0 && (
                      <div className="flex gap-1 flex-wrap">
                        <span>TP:</span>
                        {(tps as Array<{ price: number; allocation: number }>).map((tp, tpIdx) => {
                          const isHit = hitTPs.includes(tpIdx)
                          return (
                            <span
                              key={tpIdx}
                              className={isHit ? 'text-green-400' : 'text-neutral-400'}
                            >
                              ${tp.price.toFixed(0)}
                              {tpIdx < tps.length - 1 && ','}
                            </span>
                          )
                        })}
                      </div>
                    )}
                    {(sls.length > 0 || (trade.SL ?? 0) > 0) && (
                      <div className="mt-1">
                        <span>SL: </span>
                        <span className="text-neutral-400">
                          ${sls.length > 0 
                            ? (sls as Array<{ price: number; allocation: number }>).map(sl => sl.price.toFixed(0)).join(', ')
                            : (trade.SL ?? 0).toFixed(0)
                          }
                        </span>
                      </div>
                    )}
                  </div>
                )}

                {/* Actions */}
                <div className="flex items-center justify-end text-sm pt-3 border-t border-neutral-700/30" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setSelectedTrade({ ...trade, index: actualIndex ?? 0 })
                      setCloseOnHyperliquid(true)
                      setShowCloseModal(true)
                    }}
                    className="text-neutral-400 hover:text-neutral-300"
                  >
                    Close
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Close Trade Modal */}
      {showCloseModal && selectedTrade && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="glass-panel p-5 max-w-md w-full">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-medium text-white">Close Trade</h3>
              <button onClick={() => {
                setShowCloseModal(false)
                setSelectedTrade(null)
                setCloseOnHyperliquid(true)
              }} className="text-neutral-500 hover:text-white">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <p className="text-xs text-neutral-500 mb-0.5">Asset: {selectedTrade.Asset}</p>
                <p className="text-xs text-neutral-500">Entry: ${selectedTrade.Entry}</p>
                <p className="text-xs text-neutral-500 mt-1">Direction: {selectedTrade.Direction?.toUpperCase()}</p>
                <p className="text-xs text-neutral-500">Position Size: ${selectedTrade.Position_Size?.toFixed(2)}</p>
              </div>
              {mode === 'live' && (
                <div className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    id="closeOnHL"
                    checked={closeOnHyperliquid}
                    onChange={(e) => setCloseOnHyperliquid(e.target.checked)}
                    className="w-3.5 h-3.5 rounded border-neutral-600 bg-neutral-800 text-orange-500 focus:ring-orange-500 focus:ring-offset-0"
                  />
                  <label htmlFor="closeOnHL" className="text-neutral-400 cursor-pointer select-none">
                    Close position on Hyperliquid at market price
                  </label>
                </div>
              )}
              <div className="bg-neutral-800/30 p-3 rounded border border-neutral-700/50">
                <p className="text-xs text-neutral-400 mb-1">This will:</p>
                <ul className="text-xs text-neutral-500 space-y-1 list-disc list-inside">
                  {closeOnHyperliquid && mode === 'live' && <li>Close the position on Hyperliquid at current market price</li>}
                  <li>Record the trade in your journal at {closeOnHyperliquid && mode === 'live' ? 'the fill price from Hyperliquid' : 'current market price'}</li>
                  <li>Update your portfolio balance</li>
                </ul>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleCloseTrade}
                  disabled={isClosing}
                  className={`flex-1 px-3 py-2 border text-sm transition-colors ${
                    isClosing
                      ? 'bg-orange-500/20 border-orange-500/30 text-orange-400/50 cursor-not-allowed'
                      : 'bg-orange-500/10 hover:bg-orange-500/20 border-orange-500/20 text-orange-400'
                  }`}
                >
                  {isClosing ? 'Closing...' : 'Close Trade'}
                </button>
                <button
                  onClick={() => {
                    setShowCloseModal(false)
                    setSelectedTrade(null)
                    setCloseOnHyperliquid(true)
                  }}
                  disabled={isClosing}
                  className={`flex-1 px-3 py-2 border text-sm transition-colors ${
                    isClosing
                      ? 'bg-gray-800/30 border-gray-700/50 text-white/50 cursor-not-allowed'
                      : 'bg-transparent hover:bg-gray-800/50 border-gray-800/50 text-white'
                  }`}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TP Hit Modal */}
      {showTPModal && selectedTrade && (() => {
        const tps = JSON.parse(selectedTrade.TPs || '[]') as Array<{ price: number; allocation: number }>
        const hitTPs = JSON.parse(selectedTrade.Hit_TPs || '[]') as number[]
        const availableTPs = tps.filter((_: { price: number; allocation: number }, i: number) => !hitTPs.includes(i))
        
        return (
          <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="glass-panel p-5 max-w-md w-full">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-medium text-white">Take Profit Hit</h3>
                <button onClick={() => setShowTPModal(false)} className="text-neutral-500 hover:text-white">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="space-y-3">
                <div>
                  <p className="text-xs text-neutral-500 mb-0.5">Asset: {selectedTrade.Asset}</p>
                  <p className="text-xs text-neutral-500">Entry: ${selectedTrade.Entry}</p>
                </div>
                {availableTPs.length > 0 ? (
                  <div className="space-y-1.5">
                    {availableTPs.map((tp, idx) => {
                      const originalIndex = tps.findIndex((t: { price: number; allocation: number }) => t.price === tp.price && t.allocation === tp.allocation)
                      return (
                        <button
                          key={idx}
                          onClick={() => handleTPHit(originalIndex)}
                          className="w-full px-3 py-2 bg-black/60 hover:bg-green-500/10 rounded text-left transition-colors border border-neutral-700/60 hover:border-green-500/40"
                        >
                          <p className="text-white text-sm">TP{originalIndex + 1}: ${tp.price}</p>
                          <p className="text-xs text-neutral-500">Allocation: {tp.allocation * 100}%</p>
                        </button>
                      )
                    })}
                  </div>
                ) : (
                  <p className="text-neutral-500 text-center py-4 text-sm">All take profits have been hit</p>
                )}
                <button
                  onClick={() => setShowTPModal(false)}
                  className="w-full px-3 py-2 bg-black/60 hover:bg-black/80 border border-neutral-700/60 text-white rounded text-sm transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )
      })()}

      {/* SL Hit Modal */}
      {showSLModal && selectedTrade && (() => {
        const sls = JSON.parse(selectedTrade.SLs || '[]') as Array<{ price: number; allocation: number }>
        const availableSLs = sls.length > 0 ? sls : ((selectedTrade.SL ?? 0) > 0 ? [{ price: selectedTrade.SL ?? 0, allocation: 1.0 }] : [])
        
        return (
          <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="glass-panel p-5 max-w-md w-full">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-medium text-white">Stop Loss Hit</h3>
                <button onClick={() => setShowSLModal(false)} className="text-neutral-500 hover:text-white">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="space-y-3">
                <div>
                  <p className="text-xs text-neutral-500 mb-0.5">Asset: {selectedTrade.Asset}</p>
                  <p className="text-xs text-neutral-500">Entry: ${selectedTrade.Entry}</p>
                </div>
                {availableSLs.length > 0 ? (
                  <div className="space-y-1.5">
                    {(availableSLs as Array<{ price: number; allocation: number }>).map((sl, idx) => {
                      const originalIndex = sls.length > 0 ? idx : 0
                      return (
                        <button
                          key={idx}
                          onClick={() => handleSLHit(originalIndex, sl.price, sl.allocation)}
                          className="w-full px-3 py-2 bg-black/60 hover:bg-red-500/10 rounded text-left transition-colors border border-neutral-700/60 hover:border-red-500/40"
                        >
                          <p className="text-white text-sm">SL{originalIndex + 1}: ${sl.price}</p>
                          <p className="text-xs text-neutral-500">Allocation: {sl.allocation * 100}%</p>
                        </button>
                      )
                    })}
                  </div>
                ) : (
                  <p className="text-neutral-500 text-center py-4 text-sm">No stop losses configured</p>
                )}
                <button
                  onClick={() => setShowSLModal(false)}
                  className="w-full px-3 py-2 bg-black/60 hover:bg-black/80 border border-neutral-700/60 text-white rounded text-sm transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )
      })()}

      {/* Trade Detail Modal */}
      {showTradeDetailModal && selectedTradeForDetail && (
        <TradeDetailModal 
          trade={selectedTradeForDetail}
          currentPrice={selectedTradeForDetail.Asset ? currentPrices[selectedTradeForDetail.Asset] : undefined}
          onClose={() => {
            setShowTradeDetailModal(false)
            setSelectedTradeForDetail(null)
          }} 
        />
      )}
    </div>
  )
})


type TradeDetailModalProps = { trade: Trade; currentPrice?: number; onClose: () => void }
function TradeDetailModal({ trade, currentPrice, onClose }: TradeDetailModalProps) {
  const tps = JSON.parse(trade.TPs || '[]')
  const sls = JSON.parse(trade.SLs || '[]')
  const hitTPs = JSON.parse(trade.Hit_TPs || '[]')
  const confirmations = trade.Confirmations ? trade.Confirmations.split('\n').filter((c: string) => c.trim()) : []

  // Calculate P&L
  const calculatePnL = () => {
    if (!currentPrice || !trade.Entry) return null
    
    const entry = typeof trade.Entry === 'number' ? trade.Entry : parseFloat(String(trade.Entry ?? 0))
    const positionSize = typeof trade.Position_Size === 'number' ? trade.Position_Size : parseFloat(String(trade.Position_Size ?? 0)) || 0
    
    if (trade.Direction?.toLowerCase() === 'long') {
      return (currentPrice - entry) * (positionSize / entry)
    } else {
      return (entry - currentPrice) * (positionSize / entry)
    }
  }

  const pnl = calculatePnL()

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div 
        className="glass-panel p-5 max-w-5xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="relative">
          {/* Header */}
          <div className="flex items-center justify-between mb-5 pb-3 border-b border-neutral-700/50">
            <div className="flex items-center gap-2.5">
              <h2 className="text-lg font-medium text-white font-display">{trade.Asset}</h2>
              <span className={`px-2 py-0.5 text-xs rounded ${
                trade.Direction?.toLowerCase() === 'long'
                  ? 'bg-green-500/10 text-green-400 border border-green-500/30'
                  : 'bg-red-500/10 text-red-400 border border-red-500/30'
              }`}>
                {trade.Direction?.toUpperCase()}
              </span>
              {pnl !== null && (
                <span className={`text-xs font-medium ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  ${pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}
                </span>
              )}
            </div>
            <button 
              onClick={onClose}
              className="text-neutral-400 hover:text-white transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-4">
            {/* Trade Overview */}
            <div className="glass-card p-3.5">
              <h3 className="text-xs font-medium text-neutral-400 mb-3">Trade Overview</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div>
                  <p className="text-xs text-neutral-500 mb-1">Entry Price</p>
                  <p className="text-white text-sm">${trade.Entry?.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-xs text-neutral-500 mb-1">Current Price</p>
                  <p className="text-white text-sm">{currentPrice ? `$${currentPrice.toFixed(2)}` : '-'}</p>
                </div>
                {trade.Exit_Price && (
                  <div>
                    <p className="text-xs text-neutral-500 mb-1">Exit Price</p>
                    <p className="text-white text-sm">${trade.Exit_Price?.toFixed(2)}</p>
                  </div>
                )}
                <div>
                  <p className="text-xs text-neutral-500 mb-1">Stop Loss</p>
                  <p className="text-white text-sm">${trade.SL?.toFixed(2) || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-neutral-500 mb-1">Position Size</p>
                  <p className="text-white text-sm">${trade.Position_Size?.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-xs text-neutral-500 mb-1">Status</p>
                  <span className={`px-1.5 py-0.5 text-xs rounded inline-block ${
                    trade.Status === 'Open'
                      ? 'bg-blue-500/10 text-blue-400 border border-blue-500/30'
                      : trade.Status === 'Closed'
                      ? 'bg-gray-500/10 text-neutral-400 border border-gray-500/30'
                      : 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/30'
                  }`}>
                    {trade.Status}
                  </span>
                </div>
                {trade.Hold_Time && (
                  <div>
                    <p className="text-xs text-neutral-500 mb-1">Hold Time</p>
                    <p className="text-white text-sm">{trade.Hold_Time}</p>
                  </div>
                )}
              </div>
            </div>

            {/* Take Profits */}
            {tps.length > 0 && (
              <div className="glass-card p-3.5">
                <h3 className="text-xs font-medium text-neutral-400 mb-3">Take Profits</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
                  {tps.map((tp: { price: number; allocation: number }, tpIdx: number) => {
                    const isHit = hitTPs.includes(tpIdx)
                    return (
                      <div
                        key={tpIdx}
                        className={`px-3 py-2.5 rounded-lg border transition-all ${
                          isHit
                            ? 'bg-green-500/10 text-green-400 border-green-500/30'
                            : 'bg-black/20 text-gray-300 border-neutral-700/40'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <p className="font-normal text-xs">TP{tpIdx + 1}</p>
                          {isHit && (
                            <span className="text-green-400 text-xs">✓</span>
                          )}
                        </div>
                        <p className="text-xs text-neutral-500 mb-0.5">Price</p>
                        <p className="text-sm mb-1.5">${tp.price?.toFixed(2)}</p>
                        <p className="text-xs text-neutral-500 mb-0.5">Allocation</p>
                        <p className="text-xs">{(tp.allocation * 100).toFixed(0)}%</p>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Stop Losses */}
            {sls.length > 0 && (
              <div className="glass-card p-3.5">
                <h3 className="text-xs font-medium text-neutral-400 mb-3">Stop Losses</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
                  {sls.map((sl: { price: number; allocation: number }, slIdx: number) => {
                    const isHit = trade.SL_Hit && trade.SL_Price && Math.abs(trade.SL_Price - sl.price) < 0.01
                    return (
                      <div
                        key={slIdx}
                        className={`px-3 py-2.5 rounded-lg border transition-all ${
                          isHit
                            ? 'bg-red-500/10 text-red-400 border-red-500/30'
                            : 'bg-black/20 text-gray-300 border-neutral-700/40'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <p className="font-normal text-xs">SL{slIdx + 1}</p>
                          {isHit && (
                            <span className="text-red-400 text-xs">✓</span>
                          )}
                        </div>
                        <p className="text-xs text-neutral-500 mb-0.5">Price</p>
                        <p className="text-sm mb-1.5">${sl.price?.toFixed(2)}</p>
                        <p className="text-xs text-neutral-500 mb-0.5">Allocation</p>
                        <p className="text-xs">{(sl.allocation * 100).toFixed(0)}%</p>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Confirmations */}
            {confirmations.length > 0 && (
              <div className="glass-card p-3.5">
                <h3 className="text-xs font-medium text-neutral-400 mb-3">Confirmations</h3>
                <div className="space-y-1.5">
                  {confirmations.map((conf: string, idx: number) => (
                    <div key={idx} className="flex items-start gap-2 bg-black/20 rounded-lg px-2.5 py-2 border border-neutral-700/40">
                      <span className="text-green-400 text-xs mt-0.5">{idx + 1}.</span>
                      <p className="text-white text-xs flex-1 leading-relaxed">{conf}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Thesis */}
            {trade.Thesis && (
              <div className="glass-card p-3.5">
                <h3 className="text-xs font-medium text-neutral-400 mb-3">Trade Thesis</h3>
                <p className="text-white text-xs leading-relaxed whitespace-pre-wrap bg-black/20 rounded-lg px-3 py-2.5 border border-neutral-700/40">
                  {trade.Thesis}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default OpenTrades
