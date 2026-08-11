/**
 * PushConfirmModal — confirmation dialog before pushing prices to dispensers.
 *
 * This is a safety gate. Pushing prices changes what customers see and pay
 * at the fuel pump — we want explicit confirmation.
 *
 * Shows a summary of what's about to change (old price → new price per grade/tier).
 *
 * Props:
 *   changes   - array of { gradeName, tier, oldPrice, newPrice }
 *   onConfirm - callback when user confirms the push
 *   onCancel  - callback when user cancels
 *   loading   - bool — true while push is in flight
 */

export default function PushConfirmModal({ changes = [], onConfirm, onCancel, loading }) {
  return (
    <div style={styles.overlay} onClick={(e) => e.target === e.currentTarget && onCancel()}>
      <div style={styles.modal}>
        {/* Header */}
        <div style={styles.header}>
          <span style={styles.warningIcon}>⚠️</span>
          <div>
            <div style={styles.title}>Push prices to dispensers?</div>
            <div style={styles.subtitle}>
              This will change the prices customers see and pay at the pump.
            </div>
          </div>
        </div>

        {/* Change summary */}
        {changes.length > 0 ? (
          <div style={styles.changesSection}>
            <div style={styles.changesLabel}>Price changes:</div>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Grade</th>
                  <th style={styles.th}>Tier</th>
                  <th style={styles.th}>Current</th>
                  <th style={styles.th}>→</th>
                  <th style={styles.th}>New</th>
                </tr>
              </thead>
              <tbody>
                {changes.map((ch, i) => {
                  const isIncrease =
                    ch.oldPrice != null && ch.newPrice > ch.oldPrice
                  const isDecrease =
                    ch.oldPrice != null && ch.newPrice < ch.oldPrice
                  return (
                    <tr key={i} style={i % 2 === 0 ? styles.rowEven : styles.rowOdd}>
                      <td style={styles.td}>{ch.gradeName}</td>
                      <td style={{ ...styles.td, textTransform: 'capitalize' }}>
                        {ch.tier}
                      </td>
                      <td style={{ ...styles.td, ...styles.oldPrice }}>
                        {ch.oldPrice != null ? `$${ch.oldPrice.toFixed(3)}` : '—'}
                      </td>
                      <td style={{ ...styles.td, color: '#475569' }}>→</td>
                      <td
                        style={{
                          ...styles.td,
                          fontWeight: 700,
                          color: isIncrease
                            ? '#f87171'
                            : isDecrease
                            ? '#4ade80'
                            : '#e2e8f0',
                        }}
                      >
                        ${ch.newPrice.toFixed(3)}
                        {isIncrease && ' ↑'}
                        {isDecrease && ' ↓'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={styles.noChanges}>
            Prices in Commander DB will be pushed to all dispensers.
          </div>
        )}

        {/* Actions */}
        <div style={styles.actions}>
          <button
            style={styles.cancelBtn}
            onClick={onCancel}
            disabled={loading}
          >
            Cancel
          </button>
          <button
            style={{
              ...styles.confirmBtn,
              opacity: loading ? 0.6 : 1,
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? 'Pushing…' : '⛽ Push to Pumps'}
          </button>
        </div>
      </div>
    </div>
  )
}

const styles = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.7)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    backdropFilter: 'blur(2px)',
  },
  modal: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 16,
    padding: 32,
    maxWidth: 520,
    width: '100%',
    margin: '0 16px',
    fontFamily: 'system-ui, sans-serif',
    boxShadow: '0 25px 50px rgba(0,0,0,0.5)',
  },
  header: {
    display: 'flex',
    gap: 16,
    alignItems: 'flex-start',
    marginBottom: 24,
  },
  warningIcon: {
    fontSize: 32,
    flexShrink: 0,
  },
  title: {
    fontSize: 20,
    fontWeight: 700,
    color: '#f8fafc',
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 14,
    color: '#94a3b8',
    lineHeight: 1.5,
  },
  changesSection: {
    marginBottom: 24,
  },
  changesLabel: {
    fontSize: 12,
    fontWeight: 600,
    color: '#64748b',
    letterSpacing: '0.5px',
    textTransform: 'uppercase',
    marginBottom: 10,
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 14,
  },
  th: {
    textAlign: 'left',
    padding: '6px 10px',
    color: '#64748b',
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: '0.5px',
    textTransform: 'uppercase',
    borderBottom: '1px solid #334155',
  },
  td: {
    padding: '8px 10px',
    color: '#e2e8f0',
    fontFamily: 'monospace',
    fontSize: 14,
  },
  oldPrice: {
    color: '#64748b',
    textDecoration: 'line-through',
  },
  rowEven: {
    background: 'transparent',
  },
  rowOdd: {
    background: 'rgba(255,255,255,0.03)',
  },
  noChanges: {
    color: '#94a3b8',
    fontSize: 14,
    marginBottom: 24,
    padding: '12px 16px',
    background: '#0f172a',
    borderRadius: 8,
    border: '1px solid #334155',
  },
  actions: {
    display: 'flex',
    justifyContent: 'flex-end',
    gap: 12,
  },
  cancelBtn: {
    padding: '10px 20px',
    borderRadius: 8,
    border: '1px solid #334155',
    background: 'transparent',
    color: '#94a3b8',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  confirmBtn: {
    padding: '10px 24px',
    borderRadius: 8,
    border: 'none',
    background: '#dc2626',
    color: '#fff',
    fontSize: 14,
    fontWeight: 700,
    fontFamily: 'inherit',
    letterSpacing: '0.2px',
  },
}
