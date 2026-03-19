import api from './client'

export const calculatePositionSize = (entryPrice: number, stopLoss: number, leverage: number, direction: string, riskPercentage: number) =>
  api.post('/api/calculate/position-size', {
    entry_price: entryPrice,
    stop_loss: stopLoss,
    leverage,
    direction,
    risk_percentage: riskPercentage,
  })

export const calculateRiskReward = (entryPrice: number, stopLoss: number, takeProfits: Array<{ price: number; allocation: number }>, direction: string) => {
  const validTPs = takeProfits.filter(tp => tp.price > 0)
  if (validTPs.length === 0) {
    return Promise.resolve({ data: { rr_ratio: 0, message: 'No take profits set' } })
  }
  return api.post('/api/calculate/risk-reward', {
    entry_price: entryPrice,
    stop_loss: stopLoss,
    take_profits: validTPs,
    direction,
  })
}

export const calculateProfitLoss = (entryPrice: number, stopLoss: number, positionSize: number, takeProfits: Array<{ price: number; allocation: number }>, stopLosses: Array<{ price: number; allocation: number }>, direction: string, leverage: number) =>
  api.post('/api/calculate/profit-loss', {
    entry_price: entryPrice,
    stop_loss: stopLoss,
    position_size: positionSize,
    take_profits: takeProfits,
    stop_losses: stopLosses,
    direction,
    leverage,
  })
