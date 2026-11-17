/**
 * StatusBar — top bar showing Commander connection, sync time, and session age.
 */

export default function StatusBar({ status, loading }) {
  const connected  = status?.connected  ?? false
  const mockMode   = status?.mock_mode  ?? false
  const ageSeconds = status?.last_sync_age_seconds
  const tokenAge   = status?.session_token_age_seconds
  const authed     = status?.session_authenticated ?? false
  const lockedOut  = status?.locked_out ?? false

  function formatAge(seconds) {
    if (seconds == null) return 'never'
    if (seconds < 5)    return 'just now'
    if (seconds < 60)   return `${Math.round(seconds)}s ago`
    if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
    return `${Math.round(seconds / 3600)}h ago`
  }

  function formatTokenAge(seconds) {
    if (seconds == null) return null
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    return h > 0 ? `${h}h ${m}m` : `${m}m`
  }

  return (
    <div style={styles.bar}>
      <div style={styles.left}>
        <span style={styles.title}>⛽ commander-console</span>
        {mockMode && <span style={styles.mockBadge}>MOCK</span>}
      </div>

      <div style={styles.right}>
        {loading ? (
          <span style={styles.dim}>checking…</span>
        ) : (
          <>
            {/* Connection indicator */}
            <span style={{
              ...styles.dot,
              background: connected ? '#22c55e' : '#ef4444',
              boxShadow: connected ? '0 0 6px #22c55e' : '0 0 6px #ef4444',
            }} />
            <span style={connected ? styles.connectedText : styles.errorText}>
              {connected ? 'Connected' : 'Disconnected'}
            </span>

            {lockedOut && (
              <>
                <span style={styles.sep}>·</span>
                <span style={styles.lockedBadge}>🔒 LOCKED OUT</span>
              </>
            )}

            {!connected && status?.error && (
              <span style={styles.errorDetail} title={status.error}>
                — {status.error.length > 50
                  ? status.error.slice(0, 47) + '…'
                  : status.error}
              </span>
            )}

            <span style={styles.sep}>·</span>
            <span style={styles.dim}>synced {formatAge(ageSeconds)}</span>

            {/* Session token age */}
            {!mockMode && authed && tokenAge != null && (
              <>
                <span style={styles.sep}>·</span>
                <span style={styles.dim} title="Session token age (refreshes daily)">
                  🔑 {formatTokenAge(tokenAge)}
                </span>
              </>
            )}
            {!mockMode && !authed && (
              <>
                <span style={styles.sep}>·</span>
                <span style={{...styles.dim, color: '#f87171'}}>No session</span>
              </>
            )}

            {status?.commander_host && (
              <>
                <span style={styles.sep}>·</span>
                <span style={styles.dim}>{status.commander_host}</span>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

const styles = {
  bar: {
    display: 'flex', alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 20px', height: 48,
    background: '#0f172a',
    borderBottom: '1px solid #1e293b',
    fontFamily: 'system-ui, sans-serif',
    fontSize: 13, color: '#94a3b8', flexShrink: 0,
  },
  left:  { display: 'flex', alignItems: 'center', gap: 10 },
  right: { display: 'flex', alignItems: 'center', gap: 8  },
  title: { fontWeight: 700, fontSize: 15, color: '#f8fafc', letterSpacing: '-0.2px' },
  mockBadge: {
    background: '#854d0e', color: '#fef08a',
    fontSize: 10, fontWeight: 700,
    padding: '2px 7px', borderRadius: 4, letterSpacing: '0.5px',
  },
  dot: { width: 8, height: 8, borderRadius: '50%', display: 'inline-block', flexShrink: 0 },
  connectedText: { color: '#22c55e', fontWeight: 600 },
  errorText:     { color: '#ef4444', fontWeight: 600 },
  errorDetail:   { color: '#f87171', fontSize: 12 },
  lockedBadge: {
    background: '#450a0a', color: '#fca5a5', border: '1px solid #ef4444',
    fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 4, letterSpacing: '0.5px',
  },
  sep:           { color: '#334155', fontSize: 16 },
  dim:           { color: '#64748b' },
}
