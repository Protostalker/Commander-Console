/**
 * CredentialsPanel — rotate the Commander login this service uses, live,
 * no restart. Always collapsed behind a small toggle unless the circuit
 * breaker has tripped (status.locked_out), in which case it opens itself
 * with a clear banner — that's the moment this actually matters.
 */

import { useEffect, useState } from 'react'
import { updateCredentials } from '../api/client'

function randomPassword(length = 20) {
  // Not for cryptographic secrets elsewhere — just long/random enough that
  // there's no reason to ever reuse (or even remember) a Commander password.
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#%^&*'
  const bytes = new Uint32Array(length)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => chars[b % chars.length]).join('')
}

export default function CredentialsPanel({ status, onStatusRefresh }) {
  const lockedOut = status?.locked_out ?? false
  const [open, setOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [reveal, setReveal] = useState(false)
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState(null) // { ok, error } | null

  // Auto-open (never auto-close) once locked out, so it's impossible to miss.
  useEffect(() => { if (lockedOut) setOpen(true) }, [lockedOut])

  async function handleSubmit(e) {
    e.preventDefault()
    if (!password) return
    setSaving(true)
    setResult(null)
    try {
      const res = await updateCredentials(password, username.trim() || undefined)
      setResult({ ok: res.ok, error: res.error })
      if (res.ok) {
        setPassword('')
        onStatusRefresh?.()
      }
    } catch (err) {
      setResult({ ok: false, error: err.message })
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return (
      <div style={styles.collapsedBar}>
        <button style={styles.toggleLink} onClick={() => setOpen(true)}>
          🔑 Commander credentials
        </button>
      </div>
    )
  }

  return (
    <div style={{ ...styles.panel, ...(lockedOut ? styles.panelLocked : {}) }}>
      {lockedOut && (
        <div style={styles.lockedBanner}>
          <strong>Locked out</strong> after {status.consecutive_login_failures} consecutive failed
          logins — this service has stopped trying, on purpose, so it doesn't burn through the
          Commander unit's own remaining login attempts. This almost always means the password
          below is stale (e.g. right after rotating it on the Commander console itself). Enter the
          current one to reconnect.
        </div>
      )}

      <form onSubmit={handleSubmit} style={styles.form}>
        <div style={styles.row}>
          <label style={styles.label}>Username</label>
          <input
            style={styles.input}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder={status?.commander_host ? 'leave blank to keep current' : 'MANAGER'}
          />
        </div>
        <div style={styles.row}>
          <label style={styles.label}>New password</label>
          <div style={styles.passwordRow}>
            <input
              style={{ ...styles.input, flex: 1 }}
              type={reveal ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="current password on the Commander console"
              autoComplete="new-password"
            />
            <button type="button" style={styles.smallBtn} onClick={() => setReveal((v) => !v)}>
              {reveal ? 'Hide' : 'Show'}
            </button>
            <button
              type="button"
              style={styles.smallBtn}
              title="Fill in a fresh random password instead of reusing one you've picked before — avoids ever hitting the Commander's password-history rule"
              onClick={() => { setPassword(randomPassword()); setReveal(true) }}
            >
              Generate
            </button>
          </div>
          <div style={styles.hint}>
            Generate fills in a random password here — you still have to set it as the
            account's password on the Commander console itself, then submit the same value here.
          </div>
        </div>

        <div style={styles.actions}>
          <button type="submit" style={styles.submitBtn} disabled={saving || !password}>
            {saving ? 'Updating…' : 'Update & reconnect'}
          </button>
          {!lockedOut && (
            <button type="button" style={styles.smallBtn} onClick={() => setOpen(false)}>
              Close
            </button>
          )}
        </div>

        {result && (
          <div style={result.ok ? styles.resultOk : styles.resultError}>
            {result.ok
              ? '✓ Connected — lockout cleared.'
              : `✗ ${result.error || 'Login failed with the new credentials.'}`}
          </div>
        )}
      </form>
    </div>
  )
}

const styles = {
  collapsedBar: {
    padding: '4px 24px',
    background: '#0a0f1e',
    borderBottom: '1px solid #1e293b',
  },
  toggleLink: {
    background: 'none',
    border: 'none',
    color: '#475569',
    fontSize: 12,
    cursor: 'pointer',
    fontFamily: 'system-ui, sans-serif',
    padding: '4px 0',
  },
  panel: {
    margin: '12px 24px',
    padding: 16,
    borderRadius: 10,
    background: '#1e293b',
    border: '1px solid #334155',
    fontFamily: 'system-ui, sans-serif',
  },
  panelLocked: {
    border: '1px solid #ef4444',
  },
  lockedBanner: {
    background: '#450a0a',
    border: '1px solid #ef4444',
    borderRadius: 8,
    padding: '10px 12px',
    color: '#fca5a5',
    fontSize: 12.5,
    lineHeight: 1.5,
    marginBottom: 12,
  },
  form: { display: 'flex', flexDirection: 'column', gap: 10 },
  row: { display: 'flex', flexDirection: 'column', gap: 4 },
  label: { fontSize: 11, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.4px' },
  input: {
    background: '#0f172a', border: '1px solid #334155', borderRadius: 6,
    color: '#e2e8f0', fontSize: 13, padding: '7px 10px',
  },
  passwordRow: { display: 'flex', gap: 6 },
  hint: { fontSize: 11, color: '#475569', lineHeight: 1.4 },
  actions: { display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 },
  submitBtn: {
    padding: '8px 16px', borderRadius: 7, border: 'none',
    background: '#3b82f6', color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer',
  },
  smallBtn: {
    padding: '7px 12px', borderRadius: 6, border: '1px solid #334155',
    background: 'transparent', color: '#94a3b8', fontSize: 12, cursor: 'pointer',
  },
  resultOk: { color: '#86efac', fontSize: 12.5 },
  resultError: { color: '#fca5a5', fontSize: 12.5 },
}
