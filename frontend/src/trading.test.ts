import { describe, expect, it } from 'vitest'
import { DEFAULT_FEES, liquidationPrice, maintenanceMargin, planTrade, type FeeRates, type TradePlanInput } from './trading'

const NO_FEES: FeeRates = { taker: 0, maker: 0, stop_slippage: 0, source: 'default' }

const plan = (overrides: Partial<TradePlanInput> = {}) => planTrade({
  price: 100,
  portfolioSize: 10_000,
  riskPercent: 1,
  leverage: 10,
  direction: 'long',
  stopLoss: 95,
  takeProfits: [],
  fees: DEFAULT_FEES,
  ...overrides,
})

describe('maintenanceMargin', () => {
  it.each([[40, 0.0125], [20, 0.025], [10, 0.05], [3, 1 / 6]])('is half the initial margin at %sx max leverage', (maxLeverage, expected) => {
    expect(maintenanceMargin(maxLeverage)).toBeCloseTo(expected, 10)
  })

  it("assumes BTC's 40x when the asset's limit isn't known", () => {
    expect(maintenanceMargin(undefined)).toBe(0.0125)
    expect(maintenanceMargin(null)).toBe(0.0125)
  })
})

describe('liquidationPrice', () => {
  it.each([
    ['long', 10, 40], ['short', 10, 40], ['long', 3, 3], ['short', 20, 20], ['long', 5, 10], ['short', 5, 10],
  ] as const)('%s %sx on a %sx-max asset: margin has fallen to the maintenance margin', (direction, leverage, maxLeverage) => {
    const entry = 100
    const units = 2
    const price = liquidationPrice(entry, leverage, direction, maxLeverage)
    const side = direction === 'long' ? 1 : -1
    const equity = entry * units / leverage + side * (price - entry) * units
    expect(equity).toBeCloseTo(maintenanceMargin(maxLeverage) * price * units, 9)
  })

  it('matches the backend (backend/tests/test_risk.py)', () => {
    expect(liquidationPrice(100, 10, 'long')).toBeCloseTo(91.139, 3)
    expect(liquidationPrice(100, 10, 'short')).toBeCloseTo(108.642, 3)
    expect(liquidationPrice(100, 5, 'long', 10)).toBeCloseTo(84.211, 3)
    expect(liquidationPrice(100, 5, 'SHORT', 10)).toBeCloseTo(114.286, 3)
  })
})

describe('planTrade', () => {
  it('sizes so the loss at the stop, fees and slippage included, is exactly the risk', () => {
    const details = plan()

    // $100 risk / (5% stop + two 0.045% taker fees + 0.05% slippage)
    expect(details.estimatedLoss).toBe(100)
    expect(details.positionSizeDollars).toBeCloseTo(100 / 0.0514, 9)
    expect(details.priceLossAtStop + details.feesAtStop + details.slippageAtStop).toBeCloseTo(100, 9)
    expect(details.positionSize).toBeCloseTo(details.positionSizeDollars / 100, 12)
    expect(details.marginRequired).toBeCloseTo(details.positionSizeDollars / 10, 9)
    expect(details.isStopLossValid).toBe(true)
  })

  it("uses the account's fee rates", () => {
    const details = plan({ fees: { taker: 0.000432, maker: 0.000144, stop_slippage: 0.0005, source: 'account' } })

    expect(details.positionSizeDollars).toBeCloseTo(100 / (0.05 + 2 * 0.000432 + 0.0005), 9)
  })

  it('sizes a short against a stop above the price', () => {
    const details = plan({ direction: 'short', stopLoss: 105, fees: NO_FEES })

    expect(details.isStopLossValid).toBe(true)
    expect(details.positionSizeDollars).toBeCloseTo(2_000, 9)
  })

  it('without a stop, sizes against the liquidation price', () => {
    const details = plan({ stopLoss: null, fees: NO_FEES })

    expect(details.isStopLossValid).toBe(false)
    expect(details.liquidationPrice).toBeCloseTo(90 / 0.9875, 9)
    expect(details.positionSizeDollars).toBeCloseTo(100 / (1 - 90 / 0.9875 / 100), 6)
  })

  it.each([
    ['on the wrong side of the price', { stopLoss: 101 }],
    ['past the liquidation price', { stopLoss: 90 }],
    ['zero', { stopLoss: 0 }],
  ])('ignores a stop %s and sizes against liquidation', (_label, overrides) => {
    const details = plan({ ...overrides, fees: NO_FEES })

    expect(details.isStopLossValid).toBe(false)
    expect(details.priceLossAtStop).toBeCloseTo(100, 9)
    expect(details.positionSizeDollars).toBeCloseTo(plan({ stopLoss: null, fees: NO_FEES }).positionSizeDollars, 9)
  })

  it("uses the asset's maintenance margin: a stop past an altcoin's real liquidation price is rejected", () => {
    // 5x long: liquidated at 81.01 with BTC's 1.25% maintenance, at 84.21 on a 10x-max asset (5%)
    const onBtc = plan({ stopLoss: 83, leverage: 5, maxLeverage: 40 })
    const onAlt = plan({ stopLoss: 83, leverage: 5, maxLeverage: 10 })

    expect(onBtc.isStopLossValid).toBe(true)
    expect(onAlt.liquidationPrice).toBeCloseTo(80 / 0.95, 9)
    expect(onAlt.isStopLossValid).toBe(false) // it would be liquidated before the stop could fill
  })

  it('sizes nothing without a balance', () => {
    expect(plan({ portfolioSize: 0 }).positionSizeDollars).toBe(0)
    expect(plan({ portfolioSize: -50 }).positionSizeDollars).toBe(0)
  })

  it('counts take-profit profit after the entry taker fee and the exit maker fee', () => {
    const details = plan({ fees: NO_FEES, stopLoss: 95, takeProfits: [{ price: 110, allocation: 50 }, { price: 120, allocation: 50 }] })
    const withFees = plan({ stopLoss: 95, takeProfits: [{ price: 110, allocation: 100 }] })
    const units = withFees.positionSize

    // Without fees: $2,000 at 100 is 20 units; half exits +10, half +20
    expect(details.tpProfits.map((tp) => tp.profit)).toEqual([expect.closeTo(100, 9), expect.closeTo(200, 9)])
    expect(details.estimatedProfit).toBeCloseTo(300, 9)
    expect(details.riskRewardRatio).toBeCloseTo(3, 9)
    expect(withFees.tpProfits[0]?.profit).toBeCloseTo(10 * units - 100 * units * 0.00045 - 110 * units * 0.00015, 9)
  })

  it('ignores take profits without a price or allocation', () => {
    const details = plan({ takeProfits: [{ price: 0, allocation: 50 }, { price: 110, allocation: 0 }, { price: 110, allocation: 100 }] })

    expect(details.tpProfits).toHaveLength(1)
    expect(details.tpProfits[0]?.index).toBe(1)
  })
})
