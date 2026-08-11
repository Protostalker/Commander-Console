/**
 * PriceBoard — grid of grade cards showing In-Effect and Pending prices.
 *
 * Each card shows:
 *   Top row   — In-Effect (live at pump) prices, large
 *   Bottom row — Pending prices (staged, not yet pushed), smaller
 *
 * Border color:
 *   Yellow — pending push (updated but not yet pushed to dispensers)
 *   Green  — recently pushed/updated
 *   Default — synced
 */

export default function PriceBoard({
  grades = [],
  pendingPush = new Set(),
  recentUpdates = new Set(),
  onEditGrade,
  loading,
}) {
  if (loading && grades.length === 0) {
    return (
      <div style={styles.placeholder}>
        <span style={styles.placeholderText}>Loading prices…</span>
      </div>
    )
  }

  if (!loading && grades.length === 0) {
    return (
      <div style={styles.placeholder}>
        <span style={styles.placeholderText}>No fuel grades available</span>
      </div>
    )
  }

  return (
    <div style={styles.grid}>
      {grades.map((grade) => {
        const isPending = pendingPush.has(grade.id)
        const isRecent  = recentUpdates.has(grade.id)

        let borderColor = '#1e293b'
        if (isPending)      borderColor = '#ca8a04'
        else if (isRecent)  borderColor = '#16a34a'

        // In-Effect prices (Tier 1 — what customers pay now)
        const liveCash   = grade.prices?.cash
        const liveCredit = grade.prices?.credit

        // Pending prices (Tier 2 — staged, pushed via cfuelprices)
        const pendCash   = grade.pending_prices?.cash
        const pendCredit = grade.pending_prices?.credit

        // Show Pending row only if there are staged values
        const hasPending = pendCash != null || pendCredit != null

        // Check if pending differs from live
        const pendCashDiffers   = pendCash   != null && pendCash   !== liveCash
        const pendCreditDiffers = pendCredit != null && pendCredit !== liveCredit
        const pendingDiffers    = pendCashDiffers || pendCreditDiffers

        return (
          <div
            key={grade.id}
            style={{
              ...styles.card,
              borderColor,
              cursor: onEditGrade ? 'pointer' : 'default',
            }}
            onClick={() => onEditGrade?.(grade)}
            title="Click to edit pending prices"
          >
            {/* Header */}
            <div style={styles.cardHeader}>
              <span style={styles.gradeName}>{grade.name}</span>
              {isPending && <span style={styles.badge.pending}>⏳ Unpushed</span>}
              {isRecent && !isPending && <span style={styles.badge.recent}>✓ Pushed</span>}
            </div>

            {/* In-Effect row */}
            <div style={styles.tierSection}>
              <div style={styles.tierHeading}>IN EFFECT</div>
              <div style={styles.pricesRow}>
                <PriceCell label="CASH"   value={liveCash}   size="large" />
                <div style={styles.divider} />
                <PriceCell label="CREDIT" value={liveCredit} size="large" />
              </div>
            </div>

            {/* Pending row */}
            {hasPending && (
              <div style={{ ...styles.tierSection, marginTop: 10 }}>
                <div style={{
                  ...styles.tierHeading,
                  color: pendingDiffers ? '#fbbf24' : '#475569',
                }}>
                  PENDING {pendingDiffers ? '(differs)' : ''}
                </div>
                <div style={styles.pricesRow}>
                  <PriceCell
                    label="CASH"
                    value={pendCash}
                    size="small"
                    highlight={pendCashDiffers}
                  />
                  <div style={styles.divider} />
                  <PriceCell
                    label="CREDIT"
                    value={pendCredit}
                    size="small"
                    highlight={pendCreditDiffers}
                  />
                </div>
              </div>
            )}

            {onEditGrade && (
              <div style={styles.editHint}>click to edit pending</div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function PriceCell({ label, value, size = 'large', highlight = false }) {
  return (
    <div style={cellStyles.container}>
      <div style={cellStyles.label}>{label}</div>
      <div style={{
        ...cellStyles.value,
        fontSize: size === 'large' ? 26 : 18,
        color: highlight ? '#fbbf24' : '#e2e8f0',
        fontWeight: size === 'large' ? 800 : 600,
      }}>
        {value != null ? `$${value.toFixed(3)}` : '—'}
      </div>
    </div>
  )
}

const styles = {
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
    gap: 16,
    padding: 24,
  },
  card: {
    background: '#1e293b',
    border: '2px solid',
    borderRadius: 12,
    padding: '18px 22px',
    transition: 'border-color 0.2s',
    userSelect: 'none',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  gradeName: {
    fontSize: 18,
    fontWeight: 700,
    color: '#f8fafc',
    fontFamily: 'system-ui, sans-serif',
  },
  badge: {
    pending: {
      fontSize: 11,
      fontWeight: 600,
      color: '#fef08a',
      background: '#713f12',
      borderRadius: 4,
      padding: '2px 8px',
    },
    recent: {
      fontSize: 11,
      fontWeight: 600,
      color: '#bbf7d0',
      background: '#14532d',
      borderRadius: 4,
      padding: '2px 8px',
    },
  },
  tierSection: {
    background: '#0f172a',
    borderRadius: 8,
    padding: '8px 12px',
  },
  tierHeading: {
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: '1.2px',
    color: '#475569',
    marginBottom: 6,
    fontFamily: 'system-ui, sans-serif',
  },
  pricesRow: {
    display: 'flex',
    alignItems: 'center',
  },
  divider: {
    width: 1,
    height: 40,
    background: '#1e293b',
    margin: '0 8px',
  },
  editHint: {
    marginTop: 10,
    fontSize: 11,
    color: '#334155',
    textAlign: 'center',
    fontFamily: 'system-ui, sans-serif',
  },
  placeholder: {
    padding: 48,
    textAlign: 'center',
  },
  placeholderText: {
    color: '#475569',
    fontFamily: 'system-ui, sans-serif',
    fontSize: 16,
  },
}

const cellStyles = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
  },
  label: {
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: '1px',
    color: '#64748b',
    marginBottom: 2,
    fontFamily: 'system-ui, sans-serif',
  },
  value: {
    fontFamily: 'monospace',
    letterSpacing: '-0.5px',
  },
}
