/**
 * PriceEditor — modal for editing Pending (Tier 2) prices for a single grade.
 *
 * Displays In-Effect prices as read-only reference ("live at pump").
 * Edits are applied to Pending prices, which require a separate push to
 * go live at the dispensers.
 *
 * Props:
 *   grade   — FuelGrade object with prices (in-effect) and pending_prices
 *   onSave  — async callback({ id, name, cash, credit }, pushNow: bool)
 *   onClose — dismiss callback
 *   loading — bool (save in flight)
 *   error   — string | null
 */

import { useState, useEffect } from 'react'

export default function PriceEditor({ grade, onSave, onClose, loading, error }) {
  // Start from existing Pending prices; fall back to In-Effect
  const currentCash   = grade?.pending_prices?.cash   ?? grade?.prices?.cash   ?? ''
  const currentCredit = grade?.pending_prices?.credit ?? grade?.prices?.credit ?? ''
  const liveCash      = grade?.prices?.cash
  const liveCredit    = grade?.prices?.credit

  const [cash,   setCash]   = useState(currentCash   !== '' ? Number(currentCash).toFixed(3)   : '')
  const [credit, setCredit] = useState(currentCredit !== '' ? Number(currentCredit).toFixed(3) : '')

  useEffect(() => {
    setCash  (currentCash   !== '' ? Number(currentCash).toFixed(3)   : '')
    setCredit(currentCredit !== '' ? Number(currentCredit).toFixed(3) : '')
  }, [grade?.id])

  if (!grade) return null

  const cashNum   = parseFloat(cash)
  const creditNum = parseFloat(credit)

  // A change is defined relative to existing Pending prices
  const cashChanged   = !isNaN(cashNum)   && cashNum   !== Number(currentCash)
  const creditChanged = !isNaN(creditNum) && creditNum !== Number(currentCredit)
  const hasChanges    = cashChanged || creditChanged

  const isValid =
    (cash   === '' || (!isNaN(cashNum)   && cashNum   >= 0)) &&
    (credit === '' || (!isNaN(creditNum) && creditNum >= 0))

  function buildPayload() {
    return {
      id:     grade.id,
      name:   grade.name,
      cash:   cashChanged   ? cashNum   : null,
      credit: creditChanged ? creditNum : null,
    }
  }

  function handleSave(pushNow) {
    if (!hasChanges || !isValid) return
    onSave(buildPayload(), pushNow)
  }

  return (
    <div style={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={styles.panel}>

        {/* Header */}
        <div style={styles.header}>
          <div>
            <div style={styles.title}>Edit — {grade.name}</div>
            <div style={styles.subtitle}>Grade #{grade.id} · Editing Pending prices</div>
          </div>
          <button style={styles.closeBtn} onClick={onClose} disabled={loading}>✕</button>
        </div>

        {/* Error */}
        {error && <div style={styles.errorBox}>{error}</div>}

        {/* Live-at-pump reference */}
        {(liveCash != null || liveCredit != null) && (
          <div style={styles.liveRef}>
            <div style={styles.liveRefLabel}>⛽ Currently live at pump</div>
            <div style={styles.liveRefPrices}>
              {liveCash   != null && <span>Cash: <b>${liveCash.toFixed(3)}</b></span>}
              {liveCredit != null && <span style={{marginLeft: 16}}>Credit: <b>${liveCredit.toFixed(3)}</b></span>}
            </div>
          </div>
        )}

        {/* Pending price inputs */}
        <div style={styles.fields}>
          <PriceField
            label="Pending cash"
            current={currentCash}
            value={cash}
            onChange={setCash}
            changed={cashChanged}
            disabled={loading}
          />
          <PriceField
            label="Pending credit"
            current={currentCredit}
            value={credit}
            onChange={setCredit}
            changed={creditChanged}
            disabled={loading}
          />
        </div>

        {/* Change preview */}
        {hasChanges && (
          <div style={styles.preview}>
            <div style={styles.previewLabel}>Preview</div>
            {cashChanged && (
              <div style={styles.previewRow}>
                <span style={styles.previewGrade}>{grade.name} cash (pending)</span>
                <span style={styles.previewOld}>${Number(currentCash).toFixed(3)}</span>
                <span style={styles.previewArrow}>→</span>
                <span style={styles.previewNew}>${cashNum.toFixed(3)}</span>
              </div>
            )}
            {creditChanged && (
              <div style={styles.previewRow}>
                <span style={styles.previewGrade}>{grade.name} credit (pending)</span>
                <span style={styles.previewOld}>${Number(currentCredit).toFixed(3)}</span>
                <span style={styles.previewArrow}>→</span>
                <span style={styles.previewNew}>${creditNum.toFixed(3)}</span>
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        <div style={styles.actions}>
          <button style={styles.cancelBtn} onClick={onClose} disabled={loading}>
            Cancel
          </button>
          <button
            style={{
              ...styles.updateBtn,
              opacity: (!hasChanges || !isValid || loading) ? 0.4 : 1,
              cursor:  (!hasChanges || !isValid || loading) ? 'not-allowed' : 'pointer',
            }}
            onClick={() => handleSave(false)}
            disabled={!hasChanges || !isValid || loading}
            title="Stage prices in Commander DB (requires separate push to go live at pump)"
          >
            {loading ? 'Saving…' : 'Stage Pending'}
          </button>
          <button
            style={{
              ...styles.pushBtn,
              opacity: (!hasChanges || !isValid || loading) ? 0.4 : 1,
              cursor:  (!hasChanges || !isValid || loading) ? 'not-allowed' : 'pointer',
            }}
            onClick={() => handleSave(true)}
            disabled={!hasChanges || !isValid || loading}
            title="Stage prices and immediately push to dispensers"
          >
            {loading ? 'Pushing…' : '⛽ Stage + Push Now'}
          </button>
        </div>

        <div style={styles.hint}>
          "Stage Pending" writes prices to Commander DB only.
          Use the Push button on the main screen, or "Stage + Push Now" to go live immediately.
        </div>
      </div>
    </div>
  )
}

function PriceField({ label, current, value, onChange, changed, disabled }) {
  return (
    <div style={fieldStyles.container}>
      <label style={fieldStyles.label}>{label}</label>
      <div style={{
        ...fieldStyles.inputRow,
        borderColor: changed ? '#facc15' : '#334155',
      }}>
        <span style={fieldStyles.dollar}>$</span>
        <input
          type="number"
          step="0.001"
          min="0"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          style={{
            ...fieldStyles.input,
            color: changed ? '#fef08a' : '#e2e8f0',
          }}
          placeholder="0.000"
        />
      </div>
      {changed && (
        <div style={fieldStyles.changedNote}>was ${Number(current).toFixed(3)}</div>
      )}
    </div>
  )
}

const styles = {
  overlay: {
    position: 'fixed', inset: 0,
    background: 'rgba(0,0,0,0.6)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 900, backdropFilter: 'blur(2px)',
  },
  panel: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 16,
    padding: 32,
    width: 460,
    maxWidth: '100%',
    margin: '0 16px',
    fontFamily: 'system-ui, sans-serif',
    boxShadow: '0 25px 50px rgba(0,0,0,0.5)',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 20,
  },
  title: { fontSize: 20, fontWeight: 700, color: '#f8fafc' },
  subtitle: { fontSize: 12, color: '#64748b', marginTop: 2 },
  closeBtn: {
    background: 'none', border: 'none',
    color: '#64748b', fontSize: 18, cursor: 'pointer', padding: 4,
  },
  errorBox: {
    background: '#450a0a', border: '1px solid #7f1d1d',
    borderRadius: 8, color: '#fca5a5', fontSize: 13,
    padding: '10px 14px', marginBottom: 16,
  },
  liveRef: {
    background: '#0f172a',
    border: '1px solid #1e293b',
    borderRadius: 8,
    padding: '10px 14px',
    marginBottom: 16,
  },
  liveRefLabel: {
    fontSize: 11, fontWeight: 600, color: '#475569',
    letterSpacing: '0.3px', marginBottom: 4,
  },
  liveRefPrices: {
    fontSize: 14, color: '#94a3b8', fontFamily: 'monospace',
  },
  fields: { display: 'flex', gap: 16, marginBottom: 20 },
  preview: {
    background: '#0f172a', border: '1px solid #334155',
    borderRadius: 8, padding: '12px 16px', marginBottom: 20,
  },
  previewLabel: {
    fontSize: 11, fontWeight: 600, color: '#64748b',
    letterSpacing: '0.5px', textTransform: 'uppercase', marginBottom: 10,
  },
  previewRow: {
    display: 'flex', alignItems: 'center',
    gap: 10, fontSize: 14, marginBottom: 6,
  },
  previewGrade:  { color: '#94a3b8', flex: 1 },
  previewOld:    { color: '#64748b', textDecoration: 'line-through', fontFamily: 'monospace' },
  previewArrow:  { color: '#475569' },
  previewNew:    { color: '#4ade80', fontWeight: 700, fontFamily: 'monospace' },
  actions: {
    display: 'flex', gap: 10,
    justifyContent: 'flex-end', marginBottom: 12,
  },
  cancelBtn: {
    padding: '9px 16px', borderRadius: 8,
    border: '1px solid #334155', background: 'transparent',
    color: '#94a3b8', fontSize: 13, fontWeight: 600,
    cursor: 'pointer', fontFamily: 'inherit',
  },
  updateBtn: {
    padding: '9px 16px', borderRadius: 8,
    border: '1px solid #3b82f6', background: 'transparent',
    color: '#60a5fa', fontSize: 13, fontWeight: 600,
    fontFamily: 'inherit',
  },
  pushBtn: {
    padding: '9px 16px', borderRadius: 8,
    border: 'none', background: '#2563eb',
    color: '#fff', fontSize: 13, fontWeight: 700,
    fontFamily: 'inherit',
  },
  hint: { fontSize: 11, color: '#475569', lineHeight: 1.5 },
}

const fieldStyles = {
  container: { flex: 1 },
  label: {
    display: 'block', fontSize: 12, fontWeight: 600,
    color: '#64748b', marginBottom: 6,
    letterSpacing: '0.3px', textTransform: 'uppercase',
  },
  inputRow: {
    display: 'flex', alignItems: 'center',
    background: '#0f172a', border: '1px solid',
    borderRadius: 8, padding: '0 12px',
    transition: 'border-color 0.2s',
  },
  dollar: { color: '#64748b', fontSize: 16, marginRight: 4 },
  input: {
    flex: 1, background: 'transparent',
    border: 'none', outline: 'none',
    fontSize: 20, fontWeight: 700,
    fontFamily: 'monospace', padding: '10px 0', width: '100%',
  },
  changedNote: { fontSize: 11, color: '#ca8a04', marginTop: 4 },
}
