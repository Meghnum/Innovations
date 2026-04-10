// components/Sidebar.jsx
// Left sidebar — data summary stats, suggested questions, controls

export default function Sidebar({
  summary, suggestions, llmStatus, refreshing,
  open, onRefresh, onSuggestion, onToggle
}) {
  if (!open) return null

  const fmt = (n) => n?.toLocaleString('en-GB', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) ?? '—'
  const fmtM = (n) => n ? `£${(n / 1_000_000).toFixed(1)}M` : '—'
  const fmtK = (n) => n ? `£${fmt(n)}` : '—'

  const statusColors = {
    'Open':         '#10a37f',
    'Closed':       '#6e6e6e',
    'Pending':      '#f59e0b',
    'Rejected':     '#ef4444',
    'Under Review': '#3b82f6',
  }

  return (
    <aside style={{
      width:        '280px',
      flexShrink:   0,
      background:   'var(--bg-sidebar)',
      borderRight:  '1px solid var(--border)',
      display:      'flex',
      flexDirection:'column',
      overflow:     'hidden',
    }}>

      {/* Logo */}
      <div style={{
        padding:      '20px 20px 16px',
        borderBottom: '1px solid var(--border)',
        display:      'flex',
        alignItems:   'center',
        justifyContent: 'space-between',
      }}>
        <span style={{ fontWeight: 700, fontSize: 16, color: 'var(--text-primary)' }}>
          Claims Assistant
        </span>
        <button onClick={onToggle} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--text-muted)', fontSize: 18,
        }}>✕</button>
      </div>

      <div style={{ overflowY: 'auto', flex: 1, padding: '16px' }}>

        {/* Refresh button */}
        <button
          onClick={onRefresh}
          disabled={refreshing}
          style={{
            width:        '100%',
            padding:      '10px',
            background:   refreshing ? 'var(--bg-hover)' : 'var(--accent)',
            color:        '#fff',
            border:       'none',
            borderRadius: 'var(--radius-sm)',
            cursor:       refreshing ? 'not-allowed' : 'pointer',
            fontWeight:   600,
            fontSize:     14,
            marginBottom: 20,
            transition:   'var(--transition)',
          }}
        >
          {refreshing ? '⟳ Refreshing...' : '↻ Refresh Data'}
        </button>

        {/* Summary Stats */}
        {summary && (
          <section style={{ marginBottom: 24 }}>
            <h3 style={{
              fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
              textTransform: 'uppercase', color: 'var(--text-muted)',
              marginBottom: 12,
            }}>Data Summary</h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
              {[
                { label: 'Total Claims',   value: fmt(summary.total_claims) },
                { label: 'Total Value',    value: fmtM(summary.total_claim_amount) },
                { label: 'Avg Claim',      value: fmtK(summary.avg_claim_amount) },
                { label: 'Avg Days Open',  value: `${summary.avg_days_open}d` },
              ].map(({ label, value }) => (
                <div key={label} style={{
                  background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)',
                  padding: '10px 12px',
                }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{label}</div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{value}</div>
                </div>
              ))}
            </div>

            {/* Status breakdown */}
            <h4 style={{
              fontSize: 11, fontWeight: 700, letterSpacing: '0.06em',
              textTransform: 'uppercase', color: 'var(--text-muted)',
              marginBottom: 8,
            }}>By Status</h4>
            {Object.entries(summary.status_counts || {}).map(([status, count]) => {
              const pct = (count / summary.total_claims * 100).toFixed(0)
              return (
                <div key={status} style={{ marginBottom: 6 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{status}</span>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{fmt(count)} ({pct}%)</span>
                  </div>
                  <div style={{ height: 4, background: 'var(--bg-hover)', borderRadius: 2 }}>
                    <div style={{
                      height: '100%', width: `${pct}%`,
                      background: statusColors[status] || 'var(--accent)',
                      borderRadius: 2, transition: 'width 0.6s ease',
                    }} />
                  </div>
                </div>
              )
            })}

            {/* Date range */}
            <div style={{
              marginTop: 12, fontSize: 11, color: 'var(--text-muted)',
              borderTop: '1px solid var(--border)', paddingTop: 10,
            }}>
              <div>📅 {summary.date_range_start} → {summary.date_range_end}</div>
              <div style={{ marginTop: 3 }}>🕐 Loaded: {summary.data_loaded_at}</div>
            </div>
          </section>
        )}

        {/* Suggested questions */}
        {suggestions.length > 0 && (
          <section>
            <h3 style={{
              fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
              textTransform: 'uppercase', color: 'var(--text-muted)',
              marginBottom: 10,
            }}>Try Asking</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {suggestions.map((q) => (
                <button
                  key={q}
                  onClick={() => onSuggestion(q)}
                  style={{
                    background:   'none',
                    border:       '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    color:        'var(--text-secondary)',
                    fontSize:     12,
                    padding:      '7px 10px',
                    textAlign:    'left',
                    cursor:       'pointer',
                    transition:   'var(--transition)',
                    lineHeight:   1.4,
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = 'var(--bg-hover)'
                    e.currentTarget.style.color = 'var(--text-primary)'
                    e.currentTarget.style.borderColor = 'var(--accent)'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = 'none'
                    e.currentTarget.style.color = 'var(--text-secondary)'
                    e.currentTarget.style.borderColor = 'var(--border)'
                  }}
                >
                  {q}
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </aside>
  )
}
