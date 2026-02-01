import React, { useState, useEffect, useImperativeHandle, forwardRef, useCallback, useRef } from 'react'
import { X } from 'lucide-react'
import { getOpenTrades, closeTrade, partialCloseTrade, stopLossHit, deleteTrade } from '../api/trades'
import { TradeCardSkeleton } from '../components/LoadingSkeleton'

const OpenTrades = forwardRef((props, ref) => {
  const [trades, setTrades] = useState([])
  const [selectedTrade, setSelectedTrade] = useState(null)
  const [selectedTradeForDetail, setSelectedTradeForDetail] = useState(null)
  const [showCloseModal, setShowCloseModal] = useState(false)
  const [showTPModal, setShowTPModal] = useState(false)
  const [showSLModal, setShowSLModal] = useState(false)
  const [showTradeDetailModal, setShowTradeDetailModal] = useState(false)
  const [exitPrice, setExitPrice] = useState(0)
  const [loading, setLoading] = useState(true)
  const isInitialMount = useRef(true)

  const loadTrades = useCallback(async (showLoading = true) => {
    try {
      // Only show loading skeleton on very first mount
      if (showLoading && isInitialMount.current) {
      setLoading(true)
      }
      
      const res = await getOpenTrades()
      console.log('Open trades loaded:', res.data)
      setTrades(res.data?.trades || [])
      isInitialMount.current = false
    } catch (error) {
      console.error('Error loading trades:', error)
      console.error('Error details:', error.response?.data || error.message)
      console.error('Error config:', error.config)
      setTrades([])
      isInitialMount.current = false
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadTrades()
  }, [loadTrades])

  // Expose loadTrades to parent component (without showing loading skeleton)
  useImperativeHandle(ref, () => ({
    loadTrades: () => loadTrades(false)
  }))


  const handleCloseTrade = useCallback(async () => {
    if (!selectedTrade || exitPrice <= 0) {
      alert('Please enter a valid exit price')
      return
    }

    const tradeIndex = selectedTrade.index
    const originalTrades = [...trades]

    // Optimistic update - remove trade immediately
    setTrades(prev => prev.filter((_, idx) => {
      const actualIndex = prev[idx]._index !== undefined ? prev[idx]._index : idx
      return actualIndex !== tradeIndex
    }))
      setShowCloseModal(false)
      setSelectedTrade(null)
      setExitPrice(0)

    try {
      await closeTrade(tradeIndex, exitPrice)
      await loadTrades()
    } catch (error) {
      // Revert on error
      setTrades(originalTrades)
      alert(error.response?.data?.detail || 'Error closing trade')
    }
  }, [selectedTrade, exitPrice, trades, loadTrades])

  const handleTPHit = useCallback(async (tpIndex) => {
    if (!selectedTrade) return

    const tradeIndex = selectedTrade.index
    const originalTrades = [...trades]

    // Optimistic update - update trade immediately
    setTrades(prev => prev.map(trade => {
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
      const tps = JSON.parse(selectedTrade.TPs || '[]')
      const tp = tps[tpIndex]
      await partialCloseTrade(tradeIndex, tp.price, tp.allocation, tpIndex)
      await loadTrades()
    } catch (error) {
      // Revert on error
      setTrades(originalTrades)
      alert(error.response?.data?.detail || 'Error recording TP hit')
    }
  }, [selectedTrade, trades, loadTrades])

  const handleSLHit = useCallback(async (slIndex, slPrice, slAllocation) => {
    if (!selectedTrade) return

    const tradeIndex = selectedTrade.index
    const originalTrades = [...trades]

    // Optimistic update - update trade immediately
    setTrades(prev => prev.map(trade => {
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
      // Revert on error
      setTrades(originalTrades)
      alert(error.response?.data?.detail || 'Error recording SL hit')
    }
  }, [selectedTrade, trades, loadTrades])

  const handleDeleteTrade = useCallback(async (tradeIndex) => {
    if (!window.confirm('Are you sure you want to delete this trade? This action cannot be undone.')) {
      return
    }

    const originalTrades = [...trades]

    // Optimistic update - remove trade immediately
    setTrades(prev => prev.filter((_, idx) => {
      const actualIndex = prev[idx]._index !== undefined ? prev[idx]._index : idx
      return actualIndex !== tradeIndex
    }))

    try {
      await deleteTrade(tradeIndex)
      await loadTrades()
    } catch (error) {
      // Revert on error
      setTrades(originalTrades)
      alert(error.response?.data?.detail || 'Error deleting trade')
    }
  }, [trades, loadTrades])

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto py-12 px-6">
        <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-8 shadow-2xl shadow-black/20">
          <div className="space-y-4">
            {[...Array(3)].map((_, i) => (
              <TradeCardSkeleton key={i} />
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto py-12 px-6">
      <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-8 shadow-2xl shadow-black/20">
        <div className="space-y-1.5">
      {/* Trades List */}
      {trades.length === 0 ? (
        <div className="text-center py-4 text-neutral-500 text-sm">
          No open trades
        </div>
      ) : (
        <div className="space-y-1">
          {trades.map((trade, index) => {
            // Use the _index from backend, fallback to finding in array if not present
            const actualIndex = trade._index !== undefined ? trade._index : trades.findIndex(t => t === trade)
            const tps = JSON.parse(trade.TPs || '[]')
            const sls = JSON.parse(trade.SLs || '[]')
            const hitTPs = JSON.parse(trade.Hit_TPs || '[]')
            
            return (
              <div 
                key={index} 
                className="border border-neutral-700/30 rounded p-2.5 bg-black/50 hover:border-neutral-600/70 hover:bg-black/60 transition-all card relative cursor-pointer group"
                onClick={() => {
                  setSelectedTradeForDetail(trade)
                  setShowTradeDetailModal(true)
                }}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1.5">
                      <h3 className="text-sm font-medium text-white">{trade.Asset}</h3>
                      <span className={`px-1.5 py-0.5 text-xs rounded status-badge ${
                        trade.Direction?.toLowerCase() === 'long'
                          ? 'bg-green-500/10 text-green-400 border border-green-500/30'
                          : 'bg-red-500/10 text-red-400 border border-red-500/30'
                      }`}>
                        {trade.Direction?.toUpperCase()}
                      </span>
                    </div>
                    
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5 text-xs mb-1.5">
                      <div>
                        <p className="text-neutral-500 mb-0.5">Entry</p>
                        <p className="text-white">${trade.Entry?.toFixed(2)}</p>
                      </div>
                      <div>
                        <p className="text-neutral-500 mb-0.5">Stop Loss</p>
                        <p className="text-white">${trade.SL?.toFixed(2) || '-'}</p>
                      </div>
                      <div>
                        <p className="text-neutral-500 mb-0.5">Position Size</p>
                        <p className="text-white">${trade.Position_Size?.toFixed(2)}</p>
                      </div>
                      <div>
                        <p className="text-neutral-500 mb-0.5">Date</p>
                        <p className="text-white">{new Date(trade.Date).toLocaleDateString()}</p>
                      </div>
                    </div>

                    {tps.length > 0 && (
                      <div className="mb-2">
                        <p className="text-xs text-neutral-500 mb-1.5">Take Profits</p>
                        <div className="flex gap-1.5 flex-wrap">
                          {tps.map((tp, tpIdx) => {
                            const isHit = hitTPs.includes(tpIdx)
                            return (
                              <div
                                key={tpIdx}
                                className={`px-2 py-0.5 rounded text-xs border ${
                                  isHit
                                    ? 'bg-green-500/10 text-green-400 border-green-500/30'
                                    : 'bg-black/50 text-neutral-400 border-neutral-700/60'
                                }`}
                              >
                                TP{tpIdx + 1}: ${tp.price} ({tp.allocation * 100}%)
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )}

                    {sls.length > 0 && (
                      <div>
                        <p className="text-xs text-neutral-500 mb-1.5">Stop Losses</p>
                        <div className="flex gap-1.5 flex-wrap">
                          {sls.map((sl, slIdx) => (
                            <div
                              key={slIdx}
                              className="px-2 py-0.5 rounded text-xs border bg-black/50 text-neutral-400 border-neutral-700/60"
                            >
                              SL{slIdx + 1}: ${sl.price} ({sl.allocation * 100}%)
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex gap-1.5 ml-4" onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={async (e) => {
                        e.stopPropagation()
                        const tradeWithIndex = { ...trade, index: actualIndex }
                        const tps = JSON.parse(trade.TPs || '[]')
                        const hitTPs = JSON.parse(trade.Hit_TPs || '[]')
                        const availableTPs = tps.filter((_, i) => !hitTPs.includes(i))
                        
                        // If only 1 TP, automatically record it
                        if (availableTPs.length === 1) {
                          const tpIndex = tps.findIndex(t => t.price === availableTPs[0].price && t.allocation === availableTPs[0].allocation)
                          setSelectedTrade(tradeWithIndex)
                          await handleTPHit(tpIndex)
                        } else {
                          // Multiple TPs, show modal
                          setSelectedTrade(tradeWithIndex)
                          setShowTPModal(true)
                        }
                      }}
                      className="px-3 py-1.5 text-xs bg-green-500/10 hover:bg-green-500/20 border border-green-500/30 text-green-400 rounded transition-all btn-primary"
                    >
                      TP Hit
                    </button>
                    {(sls.length > 0 || trade.SL > 0) && (
                      <button
                        onClick={async (e) => {
                          e.stopPropagation()
                          const tradeWithIndex = { ...trade, index: actualIndex }
                          const slsArray = JSON.parse(trade.SLs || '[]')
                          const availableSLs = slsArray.length > 0 ? slsArray : (trade.SL > 0 ? [{ price: trade.SL, allocation: 1.0 }] : [])
                          
                          // If only 1 SL, automatically record it
                          if (availableSLs.length === 1) {
                            // If SLs array exists, use index 0, otherwise it's from the single SL field (index 0)
                            const slIndex = 0
                            setSelectedTrade(tradeWithIndex)
                            await handleSLHit(slIndex, availableSLs[0].price, availableSLs[0].allocation)
                          } else {
                            // Multiple SLs, show modal
                            setSelectedTrade(tradeWithIndex)
                            setShowSLModal(true)
                          }
                        }}
                        className="px-3 py-1.5 text-xs bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 rounded transition-colors"
                      >
                        SL Hit
                      </button>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setSelectedTrade({ ...trade, index: actualIndex })
                        setShowCloseModal(true)
                      }}
                      className="px-3 py-1.5 text-xs bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/30 text-blue-400 rounded transition-all btn-primary"
                    >
                      Close
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDeleteTrade(actualIndex)
                      }}
                      className="px-3 py-1.5 text-xs bg-orange-500/10 hover:bg-orange-500/20 border border-orange-500/30 text-orange-400 rounded transition-all btn-primary"
                      title="Delete trade"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Close Trade Modal */}
      {showCloseModal && selectedTrade && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-black/90 border border-neutral-700/70 rounded p-5 max-w-md w-full backdrop-blur-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-medium text-white">Close Trade</h3>
              <button onClick={() => setShowCloseModal(false)} className="text-neutral-500 hover:text-white">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <p className="text-xs text-neutral-500 mb-0.5">Asset: {selectedTrade.Asset}</p>
                <p className="text-xs text-neutral-500">Entry: ${selectedTrade.Entry}</p>
              </div>
              <div>
                <label className="block text-xs text-neutral-500 mb-1.5">Exit Price ($)</label>
                <input
                  type="number"
                  step="0.01"
                  value={exitPrice || ''}
                  onChange={(e) => setExitPrice(parseFloat(e.target.value) || 0)}
                  onWheel={(e) => e.target.blur()}
                  className="w-full px-3 py-2 bg-black/60 border border-neutral-700/60 rounded text-white text-sm focus:outline-none focus:border-gray-500"
                  autoFocus
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleCloseTrade}
                  className="flex-1 px-3 py-2 bg-orange-500/10 hover:bg-orange-500/20 border border-orange-500/20 text-orange-400 rounded text-sm transition-colors"
                >
                  Close Trade
                </button>
                <button
                  onClick={() => setShowCloseModal(false)}
                  className="flex-1 px-3 py-2 bg-transparent hover:bg-gray-800/50 border border-gray-800/50 text-white rounded text-sm transition-colors"
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
        const tps = JSON.parse(selectedTrade.TPs || '[]')
        const hitTPs = JSON.parse(selectedTrade.Hit_TPs || '[]')
        const availableTPs = tps.filter((_, i) => !hitTPs.includes(i))
        
        return (
          <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="bg-black/90 border border-neutral-700/70 rounded p-5 max-w-md w-full backdrop-blur-sm">
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
                      const originalIndex = tps.findIndex(t => t.price === tp.price && t.allocation === tp.allocation)
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
        const sls = JSON.parse(selectedTrade.SLs || '[]')
        // If no SLs in array but there's a single SL value, create a temporary SL object
        const availableSLs = sls.length > 0 ? sls : (selectedTrade.SL > 0 ? [{ price: selectedTrade.SL, allocation: 1.0 }] : [])
        
        return (
          <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="bg-black/90 border border-neutral-700/70 rounded p-5 max-w-md w-full backdrop-blur-sm">
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
                    {availableSLs.map((sl, idx) => {
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
          onClose={() => {
            setShowTradeDetailModal(false)
            setSelectedTradeForDetail(null)
          }} 
        />
      )}
        </div>
      </div>
    </div>
  )
})

function TradeDetailModal({ trade, onClose }) {
  const tps = JSON.parse(trade.TPs || '[]')
  const sls = JSON.parse(trade.SLs || '[]')
  const hitTPs = JSON.parse(trade.Hit_TPs || '[]')
  const confirmations = trade.Confirmations ? trade.Confirmations.split('\n').filter(c => c.trim()) : []

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div 
        className="bg-black/95 border border-neutral-700/60 rounded-xl p-5 max-w-5xl w-full max-h-[90vh] overflow-y-auto backdrop-blur-sm card relative"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="relative">
          {/* Header */}
          <div className="flex items-center justify-between mb-5 pb-3 border-b border-neutral-700/50">
            <div className="flex items-center gap-2.5">
              <h2 className="text-lg font-medium text-white">{trade.Asset}</h2>
              <span className={`px-2 py-0.5 text-xs rounded status-badge ${
                trade.Direction?.toLowerCase() === 'long'
                  ? 'bg-green-500/10 text-green-400 border border-green-500/30'
                  : 'bg-red-500/10 text-red-400 border border-red-500/30'
              }`}>
                {trade.Direction?.toUpperCase()}
              </span>
              {trade['P&L'] !== undefined && trade['P&L'] !== null && (
                <span className={`text-xs font-medium ${
                  (trade['P&L'] || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                }`}>
                  ${(trade['P&L'] || 0) >= 0 ? '+' : ''}{(trade['P&L'] || 0).toFixed(2)}
                </span>
              )}
            </div>
            <button 
              onClick={onClose}
              className="text-neutral-400 hover:text-green-400 transition-colors p-1 hover:bg-green-500/10 rounded"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-4">
            {/* Trade Overview */}
            <div className="border border-neutral-700/50 rounded-lg p-3.5 bg-black/40 card">
              <h3 className="text-xs font-medium text-neutral-400 mb-3 section-header">Trade Overview</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div>
                  <p className="text-xs text-neutral-500 mb-1">Entry Price</p>
                  <p className="text-white text-sm font-normal">${trade.Entry?.toFixed(2)}</p>
                </div>
                {trade.Exit_Price && (
                  <div>
                    <p className="text-xs text-neutral-500 mb-1">Exit Price</p>
                    <p className="text-white text-sm font-normal">${trade.Exit_Price?.toFixed(2)}</p>
                  </div>
                )}
                <div>
                  <p className="text-xs text-neutral-500 mb-1">Stop Loss</p>
                  <p className="text-white text-sm font-normal">${trade.SL?.toFixed(2) || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-neutral-500 mb-1">Position Size</p>
                  <p className="text-white text-sm font-normal">${trade.Position_Size?.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-xs text-neutral-500 mb-1">Status</p>
                  <span className={`px-1.5 py-0.5 text-xs rounded status-badge inline-block ${
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
                    <p className="text-white text-sm font-normal">{trade.Hold_Time}</p>
                  </div>
                )}
                <div className="md:col-span-2">
                  <p className="text-xs text-neutral-500 mb-1">Date</p>
                  <p className="text-white text-xs font-normal">{new Date(trade.Date).toLocaleString()}</p>
                </div>
              </div>
            </div>

            {/* Take Profits */}
            {tps.length > 0 && (
              <div className="border border-neutral-700/50 rounded-lg p-3.5 bg-black/40 card">
                <h3 className="text-xs font-medium text-neutral-400 mb-3 section-header">Take Profits</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
                  {tps.map((tp, tpIdx) => {
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
                            <span className="text-green-400 text-xs font-normal">✓</span>
                          )}
                        </div>
                        <p className="text-xs text-neutral-500 mb-0.5">Price</p>
                        <p className="text-sm font-normal mb-1.5">${tp.price?.toFixed(2)}</p>
                        <p className="text-xs text-neutral-500 mb-0.5">Allocation</p>
                        <p className="text-xs font-normal">{(tp.allocation * 100).toFixed(0)}%</p>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Stop Losses */}
            {sls.length > 0 && (
              <div className="border border-neutral-700/50 rounded-lg p-3.5 bg-black/40 card">
                <h3 className="text-xs font-medium text-neutral-400 mb-3 section-header">Stop Losses</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
                  {sls.map((sl, slIdx) => {
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
                            <span className="text-red-400 text-xs font-normal">✓</span>
                          )}
                        </div>
                        <p className="text-xs text-neutral-500 mb-0.5">Price</p>
                        <p className="text-sm font-normal mb-1.5">${sl.price?.toFixed(2)}</p>
                        <p className="text-xs text-neutral-500 mb-0.5">Allocation</p>
                        <p className="text-xs font-normal">{(sl.allocation * 100).toFixed(0)}%</p>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Confirmations */}
            {confirmations.length > 0 && (
              <div className="border border-neutral-700/50 rounded-lg p-3.5 bg-black/40 card">
                <h3 className="text-xs font-medium text-neutral-400 mb-3 section-header">Confirmations</h3>
                <div className="space-y-1.5">
                  {confirmations.map((conf, idx) => (
                    <div key={idx} className="flex items-start gap-2 bg-black/20 rounded-lg px-2.5 py-2 border border-neutral-700/40">
                      <span className="text-green-400 text-xs font-normal mt-0.5">{idx + 1}.</span>
                      <p className="text-white text-xs flex-1 leading-relaxed">{conf}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Thesis */}
            {trade.Thesis && (
              <div className="border border-neutral-700/50 rounded-lg p-3.5 bg-black/40 card">
                <h3 className="text-xs font-medium text-neutral-400 mb-3 section-header">Trade Thesis</h3>
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

