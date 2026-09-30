import { Outlet, createRootRoute, createRoute, createRouter, Link, Navigate, useRouter } from '@tanstack/react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import Layout from './components/Layout'
import WelcomeScreen from './components/WelcomeScreen'
import PortfolioHeader from './components/PortfolioHeader'
import ModeToggle from './components/ModeToggle'
import { ModeProvider } from './contexts/ModeContext'
import TradePage from './pages/TradePage'
import AnalyticsPage from './pages/AnalyticsPage'
import { getPortfolio } from './api/portfolio'

function PrimaryNav() {
  const navItems = [
    { to: '/trade', label: 'Trade' },
    { to: '/analytics', label: 'Analytics' },
  ] as const

  return (
    <nav className="flex flex-wrap gap-2 text-sm text-neutral-400" aria-label="Primary navigation">
      {navItems.map((item) => (
        <Link
          key={item.to}
          to={item.to}
          className="rounded-full border border-neutral-700 px-4 py-1.5 transition-colors hover:border-neutral-500 hover:text-white data-[status=active]:border-white data-[status=active]:text-white"
          activeProps={{ className: 'rounded-full border border-white px-4 py-1.5 text-white' }}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  )
}

function RouterLayout() {
  return (
    <ModeProvider>
      <Layout>
        <div className="mx-auto max-w-[1320px] space-y-7 px-5 py-6 md:px-8 md:py-8">
          <header className="flex flex-wrap items-center justify-between gap-5">
            <div>
              <h1 className="font-display text-xl font-semibold tracking-tight text-white">TradeLab</h1>
              <p className="mt-1 text-xs text-neutral-500">Plan risk. Execute with intent.</p>
            </div>
            <div className="flex items-center gap-4">
              <PrimaryNav />
              <ModeToggle />
            </div>
          </header>
          <div>
            <PortfolioHeader />
          </div>
          <Outlet />
        </div>
      </Layout>
    </ModeProvider>
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

function RedirectLegacyRoute() {
  return <Navigate to="/trade" />
}

function NotFoundRoute() {
  return (
    <div className="min-h-[50vh] flex items-center justify-center">
      <div className="text-center space-y-4">
        <h1 className="text-2xl font-semibold text-white">NotFound</h1>
        <p className="text-sm text-neutral-400">The page you requested does not exist.</p>
        <Link to="/trade" className="inline-flex rounded border border-neutral-700 px-4 py-2 text-sm text-neutral-300 hover:border-neutral-500 hover:text-white">
          Go home
        </Link>
      </div>
    </div>
  )
}

const rootRoute = createRootRoute({ component: RootRoute })
const layoutRoute = createRoute({ getParentRoute: () => rootRoute, id: 'layout', component: RouterLayout })
const indexRoute = createRoute({ getParentRoute: () => layoutRoute, path: '/', component: RedirectLegacyRoute })
const tradeRoute = createRoute({ getParentRoute: () => layoutRoute, path: '/trade', component: TradePage })
const analyticsRoute = createRoute({ getParentRoute: () => layoutRoute, path: '/analytics', component: AnalyticsPage })
const plannerRoute = createRoute({ getParentRoute: () => layoutRoute, path: '/planner', component: RedirectLegacyRoute })
const openTradesRoute = createRoute({ getParentRoute: () => layoutRoute, path: '/open-trades', component: RedirectLegacyRoute })
const historyRoute = createRoute({ getParentRoute: () => layoutRoute, path: '/history', component: RedirectLegacyRoute })
const notFoundRoute = createRoute({ getParentRoute: () => rootRoute, path: '*', component: NotFoundRoute })

const routeTree = rootRoute.addChildren([
  layoutRoute.addChildren([indexRoute, tradeRoute, analyticsRoute, plannerRoute, openTradesRoute, historyRoute]),
  notFoundRoute,
])

export const router = createRouter({ routeTree, defaultPreload: 'intent' })

declare module '@tanstack/react-router' { interface Register { router: typeof router } }
