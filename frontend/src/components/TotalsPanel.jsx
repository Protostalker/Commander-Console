/**
 * TotalsPanel — fuel sales totals (volume + revenue) by period.
 *
 * Fetches from GET /api/totals?period=N and displays a per-grade breakdown.
 * Period selector: Shift / Day / Month / Year
 */

import { useState, useEffect, useCallback } from 'react'
import { fetchTotals } from '../api/client'

const PERIODS = [
  { value: 1, label: 'Shift' },
  { value: 2, label: 'Day' },
  { value: 3, label: 'Month' },
  { value: 4, label: 'Year' },
]

// Grade name → accent color
const GRADE_COLORS = {
  REGULAR: '#3b82f6',
  PLUS:    '#8b5cf6',
  SUPER:   '#f59e0b',
  'DIESEL#2': '#22c55e',
  DEFAULT: '#64748b',
}

function gradeColor(name) {
  return GRADE_COLORS[name] || GRADE_COLORS.DEFAULT
}

export default function TotalsPanel() {
  const [period, setPeriod] = useState(2)        // default: Day
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async (p) => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchTotals(p)
      setData(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(period)
  }, [period, load])

  function handlePeriodChange(p) {
    setPeriod(p)
  }

  const totals = data?.totals
  const maxRevenue = totals
    ? Math.max(...totals.grades.map((g) => g.revenue_usd), 1)
    : 1

  return (
    <div style={styles.container}>
      {/* Toolbar */}
      <div style={styles.toolbar}>
        <div style={styles.toolbarLeft}>
          <span style={styles.title}>Sales Totals</span>
          {totals?.period_begin && (
            <span style={styles.periodNote}>
              since {formatDate(totals.period_begin)}
            </span>
          )}
        </div>
        <div style={styles.periodSelector}>
          {PERIODS.map((p) => (
            <button
              key={p.value}
              style={{
                ...styles.periodBtn,
                ...(period === p.value ? styles.periodBtnActive : {}),
              }}
              onClick={() => handlePeriodChange(p.value)}
            >
              {p.label}
            </button>
          ))}
          <button
            style={styles.refreshBtn}
            onClick={() => load(period)}
            disabled={loading}
          >
            {loading ? '…' : '↺'}
          </button>
        </div>
      </div>

      {/* Content */}
      <div style={styles.content}>
        {error && (
          <div style={styles.errorBox}>⚠ {error}</div>
        )}

        {loading && !data && (
          <div style={styles.loadingBox}>Loading totals…</div>
        )}

        {totals && (
          <>
            {/* Summary cards */}
            <div style={styles.summaryRow}>
              <SummaryCard
                label="Total Volume"
                value={formatGallons(totals.total_volume_gallons)}
                sub="gallons"
              />
              <SummaryCard
                label="Total Revenue"
                value={formatMoney(totals.total_revenue_usd)}
                sub="USD"
                accent
              />
              {totals.period_seq_num != null && (
                <SummaryCard
                  label="Period #"
                  value={totals.period_seq_num}
                  sub={totals.period_label}
                />
              )}
            </div>

            {/* Per-grade bars */}
            <div style={styles.gradesSection}>
              <div style={styles.sectionLabel}>By Grade</div>
              <div style={styles.gradeList}>
                {totals.grades.map((g) => (
                  <GradeRow
                    key={g.name}
                    grade={g}
                    maxRevenue={maxRevenue}
                    color={gradeColor(g.name)}
                  />
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------
// Sub-components
// ------------------------------------------------------------------

function SummaryCard({ label, value, sub, accent }) {
  return (
    <div style={{ ...cardStyles.card, ...(accent ? cardStyles.accent : {}) }}>
      <div style={cardStyles.label}>{label}</div>
      <div style={cardStyles.value}>{value}</div>
      <div style={cardStyles.sub}>{sub}</div>
    </div>
  )
}

function GradeRow({ grade, maxRevenue, color }) {
  const pct = maxRevenue > 0 ? (grade.revenue_usd / maxRevenue) * 100 : 0

  return (
    <div style={rowStyles.row}>
      <div style={rowStyles.nameCol}>
        <span style={{ ...rowStyles.dot, background: color }} />
        <span style={rowStyles.name}>{grade.name}</span>
      </div>

      {/* Revenue bar */}
      <div style={rowStyles.barTrack}>
        <div style={{ ...rowStyles.barFill, width: `${pct}%`, background: color }} />
      </div>

      {/* Stats */}
      <div style={rowStyles.stats}>
        <span style={rowStyles.statMoney}>{formatMoney(grade.revenue_usd)}</span>
        <span style={rowStyles.statSep}>·</span>
        <span style={rowStyles.statVol}>{formatGallons(grade.volume_gallons)} gal</span>
        {grade.avg_price_per_gallon != null && (
          <>
            <span style={rowStyles.statSep}>·</span>
            <span style={rowStyles.statAvg}>avg ${grade.avg_price_per_gallon.toFixed(3)}</span>
          </>
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------
// Formatters
// ------------------------------------------------------------------

function formatMoney(n) {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}K`
  return `$${n.toFixed(2)}`
}

function formatGallons(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toFixed(1)
}

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
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
  title: {
    fontSize: 15,
    fontWeight: 700,
    color: '#f8fafc',
    fontFamily: 'system-ui, sans-serif',
  },
  periodNote: {
    fontSize: 12,
    color: '#475569',
    fontFamily: 'system-ui, sans-serif',
  },
  periodSelector: {
    display: 'flex',
    gap: 6,
    alignItems: 'center',
  },
  periodBtn: {
    padding: '6px 14px',
    borderRadius: 7,
    border: '1px solid #334155',
    background: 'transparent',
    color: '#64748b',
    fontSize: 13,
    cursor: 'pointer',
    fontFamily: 'system-ui, sans-serif',
    transition: 'all 0.15s',
  },
  periodBtnActive: {
    background: '#1e3a5f',
    borderColor: '#3b82f6',
    color: '#93c5fd',
    fontWeight: 600,
  },
  refreshBtn: {
    padding: '6px 12px',
    borderRadius: 7,
    border: '1px solid #334155',
    background: 'transparent',
    color: '#475569',
    fontSize: 13,
    cursor: 'pointer',
    fontFamily: 'system-ui, sans-serif',
  },
  content: {
    padding: '24px',
    display: 'flex',
    flexDirection: 'column',
    gap: 24,
  },
  errorBox: {
    background: '#450a0a',
    border: '1px solid #7f1d1d',
    borderRadius: 10,
    padding: '14px 18px',
    color: '#fca5a5',
    fontSize: 14,
    fontFamily: 'system-ui, sans-serif',
  },
  loadingBox: {
    color: '#475569',
    fontSize: 14,
    fontFamily: 'system-ui, sans-serif',
    padding: '24px 0',
    textAlign: 'center',
  },
  summaryRow: {
    display: 'flex',
    gap: 16,
    flexWrap: 'wrap',
  },
  gradesSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
  },
  sectionLabel: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.8px',
    textTransform: 'uppercase',
    color: '#475569',
    fontFamily: 'system-ui, sans-serif',
  },
  gradeList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
}

const cardStyles = {
  card: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 12,
    padding: '16px 22px',
    minWidth: 140,
    fontFamily: 'system-ui, sans-serif',
  },
  accent: {
    background: '#0f2740',
    borderColor: '#1e4d7b',
  },
  label: {
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: '0.6px',
    textTransform: 'uppercase',
    color: '#64748b',
    marginBottom: 6,
  },
  value: {
    fontSize: 26,
    fontWeight: 800,
    color: '#f8fafc',
    lineHeight: 1.1,
    fontVariantNumeric: 'tabular-nums',
  },
  sub: {
    fontSize: 12,
    color: '#475569',
    marginTop: 4,
  },
}

const rowStyles = {
  row: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 10,
    padding: '14px 18px',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    fontFamily: 'system-ui, sans-serif',
  },
  nameCol: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: '50%',
    flexShrink: 0,
  },
  name: {
    fontSize: 13,
    fontWeight: 700,
    color: '#cbd5e1',
    letterSpacing: '0.3px',
  },
  barTrack: {
    height: 6,
    background: '#0f172a',
    borderRadius: 3,
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    borderRadius: 3,
    transition: 'width 0.5s ease',
    opacity: 0.85,
  },
  stats: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    flexWrap: 'wrap',
  },
  statMoney: {
    fontSize: 14,
    fontWeight: 700,
    color: '#e2e8f0',
    fontVariantNumeric: 'tabular-nums',
  },
  statSep: {
    color: '#334155',
    fontSize: 13,
  },
  statVol: {
    fontSize: 13,
    color: '#64748b',
    fontVariantNumeric: 'tabular-nums',
  },
  statAvg: {
    fontSize: 13,
    color: '#94a3b8',
    fontFamily: 'monospace',
  },
}
