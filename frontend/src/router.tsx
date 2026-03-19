import { Outlet, createRootRoute, createRoute, createRouter, Link, redirect, useRouter } from '@tanstack/react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import Layout from './components/Layout'
import WelcomeScreen from './components/WelcomeScreen'
import PortfolioHeader from './components/PortfolioHeader'
import PlanTrade from './pages/PlanTrade'
import OpenTrades from './pages/OpenTrades'
import TradeHistory from './pages/TradeHistory'
import { getPortfolio } from './api/portfolio'

function PrimaryNav() {
  const navItems = [
    { to: '/trade', label: 'Trade' },
    { to: '/analytics', label: 'Analytics' },
  ] as const

  return (
    <div className="flex flex-wrap gap-2 text-xs text-neutral-400">
      {navItems.map((item) => (
        <Link
          key={item.to}
          to={item.to}
          className="rounded-full border border-neutral-700 px-3 py-1 transition-colors hover:border-neutral-500 hover:text-white data-[status=active]:border-green-500 data-[status=active]:text-green-400"
          activeProps={{ className: 'rounded-full border border-green-500 px-3 py-1 text-green-400' }}
        >
          {item.label}
        </Link>
      ))}
    </div>
  )
}

function RouterLayout() {
  return (
    <Layout>
      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <PortfolioHeader />
          <PrimaryNav />
        </div>
        <Outlet />
      </div>
    </Layout>
  )
}

function RootRoute() {
  const queryClient = useQueryClient()
  const router = useRouter()
  const portfolioQuery = useQuery({
    queryKey: ['portfolio'],
    queryFn: async () => (await getPortfolio()).data ?? { portfolio_size: 0 },
  })

  if (portfolioQuery.isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-green-500" />
      </div>
    )
  }

  if ((portfolioQuery.data?.portfolio_size ?? 0) <= 0) {
    return <WelcomeScreen onComplete={async () => {
      await queryClient.invalidateQueries({ queryKey: ['portfolio'] })
      router.navigate({ to: '/trade' })
    }} />
  }

  return <Outlet />
}

function TradeRoute() {
  return (
    <div className="space-y-6">
      <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
        <h2 className="text-sm font-medium text-neutral-400 mb-4">Trade</h2>
        <PlanTrade />
      </div>
      <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
        <h2 className="text-sm font-medium text-neutral-400 mb-4">Open Trades</h2>
        <OpenTrades />
      </div>
      <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
        <h2 className="text-sm font-medium text-neutral-400 mb-4">Trade History</h2>
        <TradeHistory />
      </div>
    </div>
  )
}

function AnalyticsRoute() {
  return (
    <div className="border border-neutral-700/30 rounded-xl bg-gradient-to-b from-neutral-900/20 to-black/20 backdrop-blur-sm p-6 shadow-2xl shadow-black/20">
      <p className="text-sm text-neutral-400">Analytics view is available from the portfolio header.</p>
    </div>
  )
}

function RedirectToTrade() {
  return redirect({ to: '/trade' })
}

function NotFoundRoute() {
  return (
    <div className="min-h-[50vh] flex items-center justify-center">
      <div className="text-center space-y-4">
        <h1 className="text-2xl font-semibold text-white">NotFound</h1>
        <p className="text-sm text-neutral-400">The page you requested does not exist.</p>
        <Link to="/" className="inline-flex rounded border border-neutral-700 px-4 py-2 text-sm text-neutral-300 hover:border-neutral-500 hover:text-white">
          Go home
        </Link>
      </div>
    </div>
  )
}

const rootRoute = createRootRoute({
  component: RootRoute,
})

const layoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'layout',
  component: RouterLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/',
  beforeLoad: RedirectToTrade,
})

const tradeRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/trade',
  component: TradeRoute,
})

const plannerRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/planner',
  beforeLoad: RedirectToTrade,
})

const openTradesRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/open-trades',
  beforeLoad: RedirectToTrade,
})

const historyRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/history',
  beforeLoad: RedirectToTrade,
})

const analyticsRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/analytics',
  component: AnalyticsRoute,
})

const notFoundRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '*',
  component: NotFoundRoute,
})

const routeTree = rootRoute.addChildren([
  layoutRoute.addChildren([indexRoute, tradeRoute, plannerRoute, openTradesRoute, historyRoute, analyticsRoute]),
  notFoundRoute,
])

export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
