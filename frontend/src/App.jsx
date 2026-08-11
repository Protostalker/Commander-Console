/**
 * App — root component for commander-console.
 *
 * Tabs: Fuel Prices | Sales Totals
 */

import { useState, useEffect, useCallback } from 'react'
import StatusBar from './components/StatusBar'
import Dashboard from './components/Dashboard'
import TotalsPanel from './components/TotalsPanel'
import { fetchStatus } from './api/client'

const STATUS_POLL_MS = 15_000

const TABS = [
  { id: 'prices', label: '⛽ Fuel Prices' },
  { id: 'totals', label: '📊 Sales Totals' },
]

export default function App() {
  const [status, setStatus] = useState(null)
  const [statusLoading, setStatusLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('prices')

  const loadStatus = useCallback(async () => {
    try {
      const data = await fetchStatus()
      setStatus(data)
    } catch (err) {
      setStatus((prev) =>
        prev ? { ...prev, connected: false, error: err.message } : null
      )
    } finally {
      setStatusLoading(false)
    }
  }, [])

  useEffect(() => {
    loadStatus()
    const timer = setInterval(loadStatus, STATUS_POLL_MS)
    return () => clearInterval(timer)
  }, [loadStatus])

  return (
    <div style={appStyles.root}>
      <StatusBar status={status} loading={statusLoading} />

      {/* Tab bar */}
      <div style={appStyles.tabBar}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            style={{
              ...appStyles.tab,
              ...(activeTab === tab.id ? appStyles.tabActive : {}),
            }}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'prices' && (
        <Dashboard status={status} onStatusRefresh={loadStatus} />
      )}
      {activeTab === 'totals' && <TotalsPanel />}
    </div>
  )
}

const appStyles = {
  root: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    background: '#0f172a',
    color: '#e2e8f0',
    fontFamily: 'system-ui, -apple-system, sans-serif',
    overflow: 'hidden',
  },
  tabBar: {
    display: 'flex',
    gap: 2,
    padding: '0 24px',
    background: '#0a0f1e',
    borderBottom: '1px solid #1e293b',
  },
  tab: {
    padding: '10px 20px',
    background: 'transparent',
    border: 'none',
    borderBottom: '2px solid transparent',
    color: '#475569',
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'system-ui, sans-serif',
    transition: 'all 0.15s',
    letterSpacing: '0.2px',
  },
  tabActive: {
    color: '#f8fafc',
    borderBottomColor: '#3b82f6',
  },
}
