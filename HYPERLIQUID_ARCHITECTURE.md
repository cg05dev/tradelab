# Hyperliquid Integration Architecture

## Overview
Direct integration with Hyperliquid exchange for real-time price tracking, position monitoring, and trade execution.

## Components

### 1. Backend Module: `hyperliquid_client.py`
- **Info Client**: Read-only market data and user state
- **Exchange Client**: Trade execution and order management
- **WebSocket Manager**: Real-time price feed handling

### 2. API Endpoints
```
# Price Data (Public)
GET  /api/hyperliquid/price/BTC           - Current BTC price
WS   /api/hyperliquid/ws/price/BTC        - WebSocket price stream

# Account/Positions (Auth Required)
GET  /api/hyperliquid/positions           - All open positions
GET  /api/hyperliquid/account             - Account balance & margin
GET  /api/hyperliquid/position/BTC        - Specific position details

# Trading (Auth Required)
POST /api/hyperliquid/order               - Place order
POST /api/hyperliquid/order/cancel        - Cancel order
GET  /api/hyperliquid/orders/open         - Open orders

# Trade Details
GET  /api/hyperliquid/fills               - Recent fills
GET  /api/hyperliquid/liquidation-price   - Calculate liquidation price
```

### 3. Frontend Components
- **Price Ticker**: Real-time BTC price display
- **Position Monitor**: Live position tracking with PnL
- **Trade Executor**: Direct order placement from trade planning
- **Connection Status**: API connection health indicator

## Data Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│   FastAPI        │────▶│  Hyperliquid    │
│   (React)       │◀────│   Backend        │◀────│  Exchange       │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                        │
        │                        │
        ▼                        ▼
┌─────────────────┐     ┌──────────────────┐
│   WebSocket     │◀────│   WebSocket      │
│   Price Feed    │     │   Manager        │
└─────────────────┘     └──────────────────┘
```

## Security Implementation

### Configuration (.env)
```bash
HYPERLIQUID_ENABLED=true
HYPERLIQUID_WALLET_ADDRESS=0x...
HYPERLIQUID_PRIVATE_KEY=0x...
HYPERLIQUID_USE_TESTNET=false
```

### Security Measures
1. Private key never exposed to frontend
2. All trading happens through backend
3. Optional: API wallet with restricted permissions
4. Rate limiting on trade endpoints
5. Order confirmation dialog for all trades

## Implementation Phases

### Phase 1: Setup & Price Feed
1. Install hyperliquid-python-sdk
2. Create Hyperliquid client wrapper
3. Implement WebSocket price feed for BTC
4. Add price ticker to dashboard

### Phase 2: Position Monitoring
1. Add position tracking endpoints
2. Create position monitoring UI
3. Display liquidation prices
4. Show unrealized PnL

### Phase 3: Trade Execution
1. Add order placement endpoint
2. Create trade execution UI
3. Link trade planning to execution
4. Add order confirmation flow

## Available Trade Details from Hyperliquid

### Position Data
- Position size (sz)
- Entry price (entryPx)
- Leverage
- Liquidation price (liqPx)
- Unrealized PnL (unrealizedPnl)
- Margin used
- Funding payments

### Order Data
- Order ID
- Order type (limit/market)
- Side (buy/sell)
- Size
- Price
- Filled size
- Status (open/filled/cancelled)
- Slippage (for market orders)

### Account Data
- Total account value
- Available margin
- Total margin used
- Withdrawable amount

## Error Handling

### Connection Errors
- Automatic WebSocket reconnection
- Fallback to REST API polling
- Connection status indicator

### Trading Errors
- Insufficient margin
- Invalid order parameters
- Rate limiting
- Order rejection reasons

## Configuration Files

### .env.example
```
# Hyperliquid Configuration
HYPERLIQUID_ENABLED=true
HYPERLIQUID_WALLET_ADDRESS=your_wallet_address_here
HYPERLIQUID_PRIVATE_KEY=your_private_key_here
HYPERLIQUID_USE_TESTNET=false
```

### config.json (for SDK)
```json
{
  "account_address": "0x...",
  "secret_key": "0x..."
}
```

## Testing Strategy

1. Test price feed on mainnet (no auth required)
2. Test positions/account on testnet first
3. Use small test orders on testnet
4. Verify all trade details before mainnet trading

## Future Enhancements

- Multiple asset support (ETH, SOL, etc.)
- Advanced order types (stop-loss, take-profit)
- Automated trading strategies
- Price alerts/notifications
- Trade history sync with journal
