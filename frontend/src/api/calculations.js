import api from './client'

export const calculatePositionSize = (entryPrice, stopLoss, leverage, direction, riskPercentage) =>
  api.post('/api/calculate/position-size', {
    entry_price: entryPrice,
    stop_loss: stopLoss,
    leverage: leverage,
    direction: direction,
    risk_percentage: riskPercentage
  })

export const calculateRiskReward = (entryPrice, stopLoss, takeProfits, direction) => {
  const validTPs = takeProfits.filter(tp => tp.price > 0)
  if (validTPs.length === 0) {
    return Promise.resolve({ data: { rr_ratio: 0, message: 'No take profits set' } })
  }
  return api.post('/api/calculate/risk-reward', {
    entry_price: entryPrice,
    stop_loss: stopLoss,
    take_profits: validTPs,
    direction: direction
  })
}

export const calculateProfitLoss = (entryPrice, stopLoss, positionSize, takeProfits, stopLosses, direction, leverage) =>
  api.post('/api/calculate/profit-loss', {
    entry_price: entryPrice,
    stop_loss: stopLoss,
    position_size: positionSize,
    take_profits: takeProfits,
    stop_losses: stopLosses,
    direction: direction,
    leverage: leverage
  })

