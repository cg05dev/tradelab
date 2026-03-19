import { useEffect, useState } from 'react'
import { getHyperliquidPositions } from '../api/hyperliquid'

type Position = {
  coin?: string
  size?: number
  entry_price?: number
  position_value?: number
  unrealized_pnl?: number
  liquidation_price?: number
  margin_used?: number
  max_leverage?: number
}

export default function HyperliquidPositions() {
  const [positions, setPositions] = useState<Position[]>([])
  useEffect(() => { void getHyperliquidPositions().then(res => setPositions(res.data?.positions || [])) }, [])
  return <div>{positions.length}</div>
}
