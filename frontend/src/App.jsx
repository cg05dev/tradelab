import { useState, useEffect } from 'react'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import WelcomeScreen from './components/WelcomeScreen'
import { getPortfolio } from './api/portfolio'

function App() {
  const [showWelcome, setShowWelcome] = useState(false)
  const [checkingPortfolio, setCheckingPortfolio] = useState(true)

  useEffect(() => {
    checkPortfolio()
  }, [])

  const checkPortfolio = async () => {
    try {
      const res = await getPortfolio()
      const portfolioSize = res.data?.portfolio_size || 0
      setShowWelcome(portfolioSize === 0 || !portfolioSize)
    } catch (error) {
      console.error('Error checking portfolio:', error)
      setShowWelcome(true)
    } finally {
      setCheckingPortfolio(false)
    }
  }

  const handleWelcomeComplete = () => {
    setShowWelcome(false)
  }

  if (checkingPortfolio) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-green-500"></div>
      </div>
    )
  }

  if (showWelcome) {
    return <WelcomeScreen onComplete={handleWelcomeComplete} />
  }

  return (
    <Layout>
      <Dashboard />
    </Layout>
  )
}

export default App
