/**
 * Dashboard — main view of commander-console.
 *
 * Orchestrates the price board, editor, push modal, and history panel.
 * Manages all application state: grade data, pending edits, push confirmation.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import PriceBoard from './PriceBoard'
import PriceEditor from './PriceEditor'
import PushConfirmModal from './PushConfirmModal'
import {
  fetchPrices,
  fetchPricesLive,
  updatePrices,
  pushPrices,
  fetchHistory,
} from '../api/client'

const POLL_INTERVAL_MS = 30_000  // refresh status/prices every 30s

export default function Dashboard({ status, onStatusRefresh }) {
  const [grades, setGrades] = useState([])
  const [pricesLoading, setPricesLoading] = useState(true)
  const [pricesError, setPricesError] = useState(null)
  const [lastSync, setLastSync] = useState(null)

  // Editing state
  const [editingGrade, setEditingGrade] = useState(null)
  const [editLoading, setEditLoading] = useState(false)
  const [editError, setEditError] = useState(null)

  // Push state
  const [showPushModal, setShowPushModal] = useState(false)
  const [pushLoading, setPushLoading] = useState(false)
  const [pushChanges, setPushChanges] = useState([])

  // Track which grades have pending/recent updates
  const [pendingPush, setPendingPush] = useState(new Set())
  const [recentUpdates, setRecentUpdates] = useState(new Set())

  // History
  const [history, setHistory] = useState([])
  const [showHistory, setShowHistory] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)

  // Toast notifications
  const [toast, setToast] = useState(null)
  const toastTimer = useRef(null)

  function showToast(message, type = 'success') {
    clearTimeout(toastTimer.current)
    setToast({ message, type })
    toastTimer.current = setTimeout(() => setToast(null), 4000)
  }

  // ------------------------------------------------------------------
  // Data fetching
  // ------------------------------------------------------------------

  const loadPrices = useCallback(async (force = false) => {
    try {
      setPricesError(null)
      const data = force ? await fetchPricesLive() : await fetchPrices()
      setGrades(data.grades || [])
      setLastSync(data.last_sync ? new Date(data.last_sync) : null)
    } catch (err) {
      setPricesError(err.message)
    } finally {
      setPricesLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    loadPrices()
  }, [loadPrices])

  // Poll for fresh prices
  useEffect(() => {
    const timer = setInterval(() => {
      loadPrices()
      onStatusRefresh?.()
    }, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [loadPrices, onStatusRefresh])

  // Clear "recently updated" badges after 30s
  useEffect(() => {
    if (recentUpdates.size === 0) return
    const timer = setTimeout(() => setRecentUpdates(new Set()), 30_000)
    return () => clearTimeout(timer)
  }, [recentUpdates])

  // ------------------------------------------------------------------
  // Save handler (from PriceEditor)
  // ------------------------------------------------------------------

  async function handleSaveGrade(update, pushNow) {
    setEditLoading(true)
    setEditError(null)
    try {
      await updatePrices([update], pushNow)
      setEditingGrade(null)

      // Mark grade as pending (if not pushing now) or recently updated
      if (pushNow) {
        setRecentUpdates((prev) => new Set([...prev, update.id]))
        setPendingPush((prev) => {
          const next = new Set(prev)
          next.delete(update.id)
          return next
        })
        showToast(`${update.name} prices updated and pushed to dispensers`)
      } else {
        setPendingPush((prev) => new Set([...prev, update.id]))
        showToast(`${update.name} prices saved — remember to push to dispensers`, 'warning')
      }

      // Refresh price data
      await loadPrices(true)
      onStatusRefresh?.()
    } catch (err) {
      setEditError(err.message)
    } finally {
      setEditLoading(false)
    }
  }

  // ------------------------------------------------------------------
  // Push to dispensers
  // ------------------------------------------------------------------

  function handlePushClick() {
    // Build change summary from pending grades
    const pendingGrades = grades.filter((g) => pendingPush.has(g.id))
    const changes = pendingGrades.flatMap((g) =>
      Object.entries(g.prices).map(([tier, price]) => ({
        gradeName: g.name,
        tier,
        oldPrice: price,   // we show current prices — exact "was" values are in history
        newPrice: price,   // the values in Commander DB are what get pushed
      }))
    )
    setPushChanges(changes)
    setShowPushModal(true)
  }

  async function handlePushConfirm() {
    setPushLoading(true)
    try {
      await pushPrices()
      setShowPushModal(false)
      setPendingPush(new Set())
      setRecentUpdates(
        new Set([...grades.map((g) => g.id)])
      )
      showToast('Prices pushed to dispensers successfully')
      await loadPrices(true)
      onStatusRefresh?.()
    } catch (err) {
      showToast(`Push failed: ${err.message}`, 'error')
    } finally {
      setPushLoading(false)
    }
  }

  // ------------------------------------------------------------------
  // History panel
  // ------------------------------------------------------------------

  async function toggleHistory() {
    if (!showHistory) {
      setHistoryLoading(true)
      try {
        const data = await fetchHistory(50)
        setHistory(data)
      } catch {
        setHistory([])
      } finally {
        setHistoryLoading(false)
      }
    }
    setShowHistory((v) => !v)
  }

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  return (
    <div style={styles.container}>
      {/* Toolbar */}
      <div style={styles.toolbar}>
        <div style={styles.toolbarLeft}>
          <span style={styles.sectionTitle}>Fuel Prices</span>
          {lastSync && (
            <span style={styles.syncNote}>
              synced {formatRelative(lastSync)}
            </span>
          )}
          {pricesError && (
            <span style={styles.errorNote}>⚠ {pricesError}</span>
          )}
        </div>
        <div style={styles.toolbarRight}>
          {pendingPush.size > 0 && (
            <button style={styles.pushBtn} onClick={handlePushClick}>
              ⛽ Push to Dispensers ({pendingPush.size})
            </button>
          )}
          <button
            style={styles.refreshBtn}
            onClick={() => loadPrices(true)}
            disabled={pricesLoading}
          >
            {pricesLoading ? '…' : '↺'} Refresh
          </button>
          <button
            style={{
              ...styles.historyBtn,
              background: showHistory ? '#1e3a5f' : 'transparent',
            }}
            onClick={toggleHistory}
          >
            History
          </button>
        </div>
      </div>

      {/* Price board */}
      <PriceBoard
        grades={grades}
        pendingPush={pendingPush}
        recentUpdates={recentUpdates}
        onEditGrade={setEditingGrade}
        loading={pricesLoading}
      />

      {/* History panel */}
      {showHistory && (
        <HistoryPanel records={history} loading={historyLoading} />
      )}

      {/* Price editor modal */}
      {editingGrade && (
        <PriceEditor
          grade={editingGrade}
          onSave={handleSaveGrade}
          onClose={() => { setEditingGrade(null); setEditError(null) }}
          loading={editLoading}
          error={editError}
        />
      )}

      {/* Push confirm modal */}
      {showPushModal && (
        <PushConfirmModal
          changes={pushChanges}
          onConfirm={handlePushConfirm}
          onCancel={() => setShowPushModal(false)}
          loading={pushLoading}
        />
      )}

      {/* Toast */}
      {toast && <Toast message={toast.message} type={toast.type} />}
    </div>
  )
}

// ------------------------------------------------------------------
// Sub-components
// ------------------------------------------------------------------

function HistoryPanel({ records, loading }) {
  if (loading) {
    return <div style={histStyles.panel}><span style={histStyles.dim}>Loading history…</span></div>
  }
  if (records.length === 0) {
    return <div style={histStyles.panel}><span style={histStyles.dim}>No price changes recorded yet.</span></div>
  }
  return (
    <div style={histStyles.panel}>
      <div style={histStyles.title}>Price Change History</div>
      <table style={histStyles.table}>
        <thead>
          <tr>
            {['Time', 'Grade', 'Tier', 'Old Price', 'New Price', 'Pushed'].map((h) => (
              <th key={h} style={histStyles.th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <tr key={r.id} style={histStyles.row}>
              <td style={histStyles.td}>{formatTimestamp(r.timestamp)}</td>
              <td style={histStyles.td}>{r.grade_name}</td>
              <td style={{ ...histStyles.td, textTransform: 'capitalize' }}>{r.tier}</td>
              <td style={{ ...histStyles.td, color: '#64748b' }}>
                {r.old_price != null ? `$${r.old_price.toFixed(3)}` : '—'}
              </td>
              <td style={{ ...histStyles.td, fontWeight: 700, color: '#e2e8f0' }}>
                ${r.new_price.toFixed(3)}
              </td>
              <td style={{ ...histStyles.td, color: r.pushed_to_dispensers ? '#22c55e' : '#ca8a04' }}>
                {r.pushed_to_dispensers ? '✓' : 'pending'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Toast({ message, type }) {
  const bg = type === 'error' ? '#7f1d1d' : type === 'warning' ? '#713f12' : '#14532d'
  const border = type === 'error' ? '#991b1b' : type === 'warning' ? '#854d0e' : '#166534'
  return (
    <div style={{ ...toastStyles.toast, background: bg, border: `1px solid ${border}` }}>
      {message}
    </div>
  )
}

// ------------------------------------------------------------------
// Utilities
// ------------------------------------------------------------------

function formatRelative(date) {
  const secs = (Date.now() - date.getTime()) / 1000
  if (secs < 5) return 'just now'
  if (secs < 60) return `${Math.round(secs)}s ago`
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`
  return date.toLocaleTimeString()
}

function formatTimestamp(iso) {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

// ------------------------------------------------------------------
// Styles
// ------------------------------------------------------------------

const styles = {
  container: {
    flex: 1,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
  },
  toolbar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '14px 24px',
    borderBottom: '1px solid #1e293b',
    background: '#0f172a',
  },
  toolbarLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
  },
  toolbarRight: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: '#f8fafc',
    fontFamily: 'system-ui, sans-serif',
  },
  syncNote: {
    fontSize: 12,
    color: '#475569',
    fontFamily: 'system-ui, sans-serif',
  },
  errorNote: {
    fontSize: 12,
    color: '#f87171',
    fontFamily: 'system-ui, sans-serif',
  },
  refreshBtn: {
    padding: '7px 14px',
    borderRadius: 7,
    border: '1px solid #334155',
    background: 'transparent',
    color: '#94a3b8',
    fontSize: 13,
    cursor: 'pointer',
    fontFamily: 'system-ui, sans-serif',
  },
  historyBtn: {
    padding: '7px 14px',
    borderRadius: 7,
    border: '1px solid #334155',
    color: '#94a3b8',
    fontSize: 13,
    cursor: 'pointer',
    fontFamily: 'system-ui, sans-serif',
  },
  pushBtn: {
    padding: '7px 16px',
    borderRadius: 7,
    border: 'none',
    background: '#b45309',
    color: '#fef3c7',
    fontSize: 13,
    fontWeight: 700,
    cursor: 'pointer',
    fontFamily: 'system-ui, sans-serif',
    animation: 'pulse 2s infinite',
  },
}

const histStyles = {
  panel: {
    margin: '0 24px 24px',
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 12,
    padding: 20,
    fontFamily: 'system-ui, sans-serif',
  },
  title: {
    fontSize: 13,
    fontWeight: 700,
    color: '#94a3b8',
    marginBottom: 12,
    letterSpacing: '0.3px',
    textTransform: 'uppercase',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 13,
  },
  th: {
    textAlign: 'left',
    padding: '6px 10px',
    color: '#475569',
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: '0.5px',
    textTransform: 'uppercase',
    borderBottom: '1px solid #334155',
  },
  td: {
    padding: '8px 10px',
    color: '#94a3b8',
    fontFamily: 'monospace',
    fontSize: 13,
    borderBottom: '1px solid #1e293b',
  },
  row: {},
  dim: {
    color: '#475569',
    fontSize: 13,
  },
}

const toastStyles = {
  toast: {
    position: 'fixed',
    bottom: 24,
    right: 24,
    borderRadius: 10,
    padding: '12px 20px',
    color: '#f8fafc',
    fontSize: 14,
    fontFamily: 'system-ui, sans-serif',
    fontWeight: 500,
    zIndex: 2000,
    maxWidth: 400,
    lineHeight: 1.4,
    boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
  },
}
