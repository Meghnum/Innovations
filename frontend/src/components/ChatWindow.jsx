// components/ChatWindow.jsx
// Scrollable message list — renders user and assistant bubbles

import { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'

export default function ChatWindow({ messages, loading }) {
  const bottomRef = useRef(null)

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const typeLabel = { aggregation: '⚡', lookup: '🔍', search: '🤖' }
  const typeColor = {
    aggregation: 'var(--accent)',
    lookup:      '#3b82f6',
    search:      '#a855f7',
  }

  return (
    <main style={{
      flex:       1,
      overflowY:  'auto',
      padding:    '24px 0',
    }}>
      <div style={{ maxWidth: 760, margin: '0 auto', padding: '0 24px' }}>

        {/* Empty state */}
        {messages.length === 0 && !loading && (
          <div style={{
            display:       'flex',
            flexDirection: 'column',
            alignItems:    'center',
            justifyContent:'center',
            paddingTop:    80,
            gap:           16,
            color:         'var(--text-muted)',
            textAlign:     'center',
          }}>
            <div style={{ fontSize: 56 }}>📋</div>
            <h2 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-secondary)' }}>
              Claims Assistant
            </h2>
            <p style={{ fontSize: 15, maxWidth: 420, lineHeight: 1.6 }}>
              Ask anything about your claims data in plain English.
              Use the suggested questions on the left to get started.
            </p>
          </div>
        )}

        {/* Message list */}
        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              marginBottom:  24,
              display:       'flex',
              flexDirection: 'column',
              alignItems:    msg.role === 'user' ? 'flex-end' : 'flex-start',
            }}
          >
            {/* Role label */}
            <div style={{
              fontSize:     11,
              fontWeight:   600,
              letterSpacing:'0.05em',
              textTransform:'uppercase',
              color:        'var(--text-muted)',
              marginBottom: 6,
              paddingLeft:  msg.role === 'user' ? 0 : 4,
              paddingRight: msg.role === 'user' ? 4 : 0,
            }}>
              {msg.role === 'user' ? 'You' : '📋 Claims Assistant'}
            </div>

            {/* Bubble */}
            <div style={{
              maxWidth:     msg.role === 'user' ? '75%' : '100%',
              width:        msg.role === 'user' ? 'auto' : '100%',
              background:   msg.role === 'user' ? 'var(--bg-secondary)' : 'transparent',
              border:       msg.role === 'user' ? '1px solid var(--border)' : 'none',
              borderRadius: msg.role === 'user' ? 'var(--radius)' : 0,
              padding:      msg.role === 'user' ? '10px 16px' : '0 4px',
              color:        'var(--text-primary)',
              fontSize:     15,
              lineHeight:   1.7,
            }}>
              {msg.role === 'user' ? (
                <span>{msg.content}</span>
              ) : (
                <div className="bot-content">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              )}
            </div>

            {/* Metadata row for assistant messages */}
            {msg.role === 'assistant' && (
              <div style={{
                display:    'flex',
                alignItems: 'center',
                gap:        8,
                marginTop:  8,
                paddingLeft:4,
                flexWrap:   'wrap',
              }}>
                {/* Question type badge */}
                {msg.questionType && (
                  <span style={{
                    fontSize:     11,
                    color:        typeColor[msg.questionType] || 'var(--text-muted)',
                    background:   'rgba(255,255,255,0.05)',
                    padding:      '2px 8px',
                    borderRadius: 'var(--radius-full)',
                    fontWeight:   600,
                  }}>
                    {typeLabel[msg.questionType]} {msg.questionType}
                  </span>
                )}

                {/* Response time */}
                {msg.elapsed !== undefined && (
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    {msg.elapsed < 1 ? '⚡ instant' : `⏱ ${msg.elapsed}s`}
                  </span>
                )}

                {/* Source pills */}
                {msg.sources?.length > 0 && (
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Sources:</span>
                    {msg.sources.slice(0, 5).map(s => (
                      <span key={s} style={{
                        fontSize:     11,
                        background:   'var(--pill-bg)',
                        color:        'var(--pill-text)',
                        padding:      '1px 8px',
                        borderRadius: 'var(--radius-full)',
                        fontFamily:   'monospace',
                      }}>{s}</span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {/* Typing indicator */}
        {loading && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', marginBottom: 24 }}>
            <div style={{
              fontSize: 11, fontWeight: 600, letterSpacing: '0.05em',
              textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6,
            }}>📋 Claims Assistant</div>
            <div style={{ display: 'flex', gap: 5, padding: '12px 4px', alignItems: 'center' }}>
              {[0, 1, 2].map(i => (
                <div key={i} style={{
                  width: 8, height: 8,
                  background: 'var(--text-muted)',
                  borderRadius: '50%',
                  animation: `pulse 1.4s ease-in-out ${i * 0.2}s infinite`,
                }} />
              ))}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <style>{`
        @keyframes pulse {
          0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
          40%            { opacity: 1;   transform: scale(1); }
        }
      `}</style>
    </main>
  )
}
