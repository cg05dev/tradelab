// Trade math the planner sizes real orders with. Pure functions, covered by trading.test.ts.
import type { TakeProfit, TradeDetails } from './types'

// BTC's maximum leverage, assumed when an asset's isn't known yet
export const DEFAULT_MAX_LEVERAGE = 40

export type FeeRates = { taker: number; maker: number; stop_slippage: number; source: 'account' | 'default' }

// Hyperliquid's base tier, used until the account's own rates load (slightly high, so risk is never undersized)
export const DEFAULT_FEES: FeeRates = { taker: 0.00045, maker: 0.00015, stop_slippage: 0.0005, source: 'default' }

// Hyperliquid's maintenance margin: half the initial margin at the asset's maximum leverage
// (1.25% for 40x BTC, 5% for a 10x asset)
export function maintenanceMargin(maxLeverage?: number | null): number {
  return 1 / (2 * (maxLeverage || DEFAULT_MAX_LEVERAGE))
}

// Where an isolated position opened at `entry` with `leverage` is liquidated: where its margin has
// fallen to the maintenance margin. Hyperliquid's formula, as in backend/risk.py.
export function liquidationPrice(entry: number, leverage: number, direction?: string, maxLeverage?: number | null): number {
  const mm = maintenanceMargin(maxLeverage)
  return direction?.toLowerCase() === 'short'
    ? entry * (1 + 1 / leverage) / (1 + mm)
    : entry * (1 - 1 / leverage) / (1 - mm)
}

export type TradePlanInput = {
  price: number
  portfolioSize: number
  riskPercent: number
  leverage: number
  direction: string
  stopLoss?: number | null
  // Allocations as percentages of the position, as the form edits them
  takeProfits: TakeProfit[]
  fees: FeeRates
  maxLeverage?: number | null
}

// Size a market entry so the loss at the stop, both taker fees and the stop's slippage included, is
// exactly the risk amount. Without a valid stop, the position is sized against its liquidation price.
export function planTrade(input: TradePlanInput): TradeDetails {
  const { price, leverage, direction, stopLoss, fees } = input
  const riskAmount = Math.max(input.portfolioSize, 0) * input.riskPercent / 100
  const liquidation = liquidationPrice(price, leverage, direction, input.maxLeverage)
  const isStopLossValid = Boolean(stopLoss && stopLoss > 0 && (
    direction === 'short'
      ? stopLoss < liquidation && stopLoss > price
      : stopLoss > liquidation && stopLoss < price
  ))
  const exitPrice = isStopLossValid && stopLoss ? stopLoss : liquidation
  const distance = Math.abs(price - exitPrice) / price
  const costAtStop = 2 * fees.taker + fees.stop_slippage
  const positionSizeDollars = riskAmount / (distance + costAtStop)
  const positionSize = positionSizeDollars / price
  // Targets are resting limit orders: the entry's taker fee plus a maker fee at the target
  const tpProfits = input.takeProfits
    .filter((tp) => tp.price > 0 && tp.allocation > 0)
    .map((tp, index) => {
      const share = tp.allocation / 100
      const gross = (tp.price - price) * positionSize * share * (direction === 'short' ? -1 : 1)
      const tpFees = positionSizeDollars * share * fees.taker + tp.price * positionSize * share * fees.maker
      return { ...tp, index: index + 1, profit: gross - tpFees }
    })
  const estimatedProfit = tpProfits.reduce((sum, tp) => sum + tp.profit, 0)

  return {
    liquidationPrice: liquidation,
    positionSize,
    positionSizeDollars,
    marginRequired: positionSizeDollars / leverage,
    riskRewardRatio: riskAmount > 0 ? estimatedProfit / riskAmount : 0,
    estimatedLoss: riskAmount,
    estimatedProfit,
    tpProfits,
    positionValue: positionSizeDollars,
    currentPrice: price,
    isStopLossValid,
    priceLossAtStop: positionSizeDollars * distance,
    feesAtStop: positionSizeDollars * 2 * fees.taker,
    slippageAtStop: positionSizeDollars * fees.stop_slippage,
  }
}
