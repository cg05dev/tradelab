# Architecture

Architectural decisions and patterns discovered during implementation.

## Frontend Stack

- **React 18** with TypeScript
- **TanStack Router** - File-based routing with type-safe navigation
- **TanStack Query** - Server state management with caching
- **Tailwind CSS** - Utility-first styling, dark theme
- **Vite** - Dev server and build tool

## Backend Stack

- **FastAPI** - Python async web framework
- **Hyperliquid SDK** - DEX integration
- **CSV storage** - Simple file-based persistence (trades.csv, portfolio_config.json)

## Key Patterns

### Routing (TanStack Router)
Routes defined in `frontend/src/router.tsx`:
```tsx
const Route = createFileRoute('/path')()
```

### Data Fetching (TanStack Query)
```tsx
const { data } = useQuery({ queryKey: ['key'], queryFn: fetchFn })
```

### Styling (Tailwind)
- Dark theme: `bg-black`, `border-neutral-800`, `text-white`
- Accents: `text-green-500`, `text-red-500`
- Buttons: `px-4 py-2 rounded-lg font-semibold`

## Component Structure

```
frontend/src/
├── router.tsx          # Route definitions + PrimaryNav
├── pages/              # Page components
│   ├── PlanTrade.tsx   # Trade planner form
│   ├── OpenTrades.tsx  # Open trades grid
│   └── TradeHistory.tsx # Closed trades list
├── components/         # Shared components
│   ├── Layout.tsx      # Main shell
│   └── PortfolioHeader.tsx
└── api/                # API client functions
    ├── trades.ts
    ├── hyperliquid.ts
    └── ...
```
