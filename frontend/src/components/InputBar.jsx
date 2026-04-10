// components/InputBar.jsx
// Bottom input bar — text field, send button, clear chat

import { useState, useRef, useEffect } from 'react'

export default function InputBar({ onAsk, onClear, loading, hasMessages }) {
  const [value, setValue]   = useState('')
  const textareaRef         = useRef(null)

  // Auto-resize textarea as user types
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }, [value])

  function handleSubmit() {
    if (!value.trim() || loading) return
    onAsk(value.trim())
    setValue('')
    // Reset textarea height
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  function handleKeyDown(e) {
    // Enter submits, Shift+Enter adds newline
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <footer style={{
      padding:    '16px 24px 20px',
      background: 'var(--bg-primary)',
      flexShrink: 0,
    }}>
      <div style={{ maxWidth: 760, margin: '0 auto' }}>

        {/* Input container */}
        <div style={{
          display:      'flex',
          alignItems:   'flex-end',
          gap:          10,
          background:   'var(--bg-input)',
          border:       '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          padding:      '10px 14px',
          transition:   'border-color var(--transition)',
        }}
          onFocus={() => {}}
        >
          {/* Textarea */}
          <textarea
            ref         = {textareaRef}
            value       = {value}
            onChange    = {e => setValue(e.target.value)}
            onKeyDown   = {handleKeyDown}
            placeholder = "Ask about your claims data... (Enter to send, Shift+Enter for new line)"
            disabled    = {loading}
            rows        = {1}
            style={{
              flex:       1,
              background: 'none',
              border:     'none',
              outline:    'none',
              color:      'var(--text-primary)',
              fontSize:   15,
              lineHeight: 1.6,
              resize:     'none',
              fontFamily: 'inherit',
              maxHeight:  160,
              overflowY:  'auto',
              padding:    '2px 0',
            }}
          />

          {/* Send button */}
          <button
            onClick  = {handleSubmit}
            disabled = {!value.trim() || loading}
            style={{
              background:   (value.trim() && !loading) ? 'var(--accent)' : 'var(--bg-hover)',
              border:       'none',
              borderRadius: 8,
              width:        34,
              height:       34,
              display:      'flex',
              alignItems:   'center',
              justifyContent:'center',
              cursor:       (value.trim() && !loading) ? 'pointer' : 'not-allowed',
              flexShrink:   0,
              transition:   'background var(--transition)',
              fontSize:     16,
              color:        (value.trim() && !loading) ? '#fff' : 'var(--text-muted)',
            }}
            title="Send (Enter)"
          >
            {loading ? '⟳' : '↑'}
          </button>
        </div>

        {/* Bottom controls row */}
        <div style={{
          display:        'flex',
          justifyContent: 'space-between',
          alignItems:     'center',
          marginTop:      8,
          paddingLeft:    4,
        }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            {loading ? '🤔 Thinking...' : 'Enter ↵ to send · Shift+Enter for new line'}
          </span>
          {hasMessages && (
            <button
              onClick={onClear}
              style={{
                background: 'none',
                border:     'none',
                color:      'var(--text-muted)',
                fontSize:   12,
                cursor:     'pointer',
                padding:    '2px 6px',
                borderRadius: 4,
                transition: 'color var(--transition)',
              }}
              onMouseEnter={e => e.currentTarget.style.color = 'var(--danger)'}
              onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
            >
              🗑 Clear chat
            </button>
          )}
        </div>
      </div>
    </footer>
  )
}
