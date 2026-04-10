import { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar.jsx'
import ChatWindow from './components/ChatWindow.jsx'
import InputBar from './components/InputBar.jsx'

const API = '/api'

export default function App() {
  const [messages, setMessages]           = useState([])
  const [summary, setSummary]             = useState(null)
  const [suggestions, setSuggestions]     = useState([])
  const [loading, setLoading]             = useState(false)
  const [llmStatus, setLlmStatus]         = useState(null)
  const [refreshing, setRefreshing]       = useState(false)
  const [sidebarOpen, setSidebarOpen]     = useState(true)

  // ── Load summary stats and suggestions on mount ──────────────────
  useEffect(() => {
    fetchSummary()
    fetchSuggestions()
    checkHealth()
  }, [])

  async function fetchSummary() {
    try {
      const res  = await fetch(`${API}/summary`)
      const data = await res.json()
      setSummary(data)
    } catch (e) {
      console.error('Failed to load summary', e)
    }
  }

  async function fetchSuggestions() {
    try {
      const res  = await fetch(`${API}/suggested-questions`)
      const data = await res.json()
      setSuggestions(data.questions || [])
    } catch (e) {
      console.error('Failed to load suggestions', e)
    }
  }

  async function checkHealth() {
    try {
      const res  = await fetch(`${API}/health`)
      const data = await res.json()
      setLlmStatus(data.llm)
    } catch (e) {
      setLlmStatus(false)
    }
  }

  // ── Ask a question ────────────────────────────────────────────────
  async function handleAsk(question) {
    if (!question.trim() || loading) return

    const userMsg = { role: 'user', content: question, id: Date.now() }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)

    try {
      const res  = await fetch(`${API}/ask`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ question }),
      })
      const data = await res.json()

      const botMsg = {
        role:         'assistant',
        content:      data.answer,
        sources:      data.sources      || [],
        questionType: data.question_type,
        elapsed:      data.elapsed,
        id:           Date.now() + 1,
      }
      setMessages(prev => [...prev, botMsg])
    } catch (e) {
      setMessages(prev => [...prev, {
        role:    'assistant',
        content: '⚠️ Could not reach the API. Make sure `uvicorn api.server:app --reload` is running.',
        sources: [],
        id:      Date.now() + 1,
      }])
    } finally {
      setLoading(false)
    }
  }

  // ── Refresh data ──────────────────────────────────────────────────
  async function handleRefresh() {
    setRefreshing(true)
    try {
      await fetch(`${API}/refresh`, { method: 'POST' })
      await fetchSummary()
    } catch (e) {
      console.error('Refresh failed', e)
    } finally {
      setRefreshing(false)
    }
  }

  // ── Clear chat ────────────────────────────────────────────────────
  function handleClear() {
    setMessages([])
  }

  // ── Suggestion click ──────────────────────────────────────────────
  function handleSuggestion(q) {
    handleAsk(q)
  }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>

      {/* Sidebar */}
      <Sidebar
        summary      = {summary}
        suggestions  = {suggestions}
        llmStatus    = {llmStatus}
        refreshing   = {refreshing}
        open         = {sidebarOpen}
        onRefresh    = {handleRefresh}
        onSuggestion = {handleSuggestion}
        onToggle     = {() => setSidebarOpen(o => !o)}
      />

      {/* Main chat area */}
      <div style={{
        flex:       1,
        display:    'flex',
        flexDirection: 'column',
        overflow:   'hidden',
        background: 'var(--bg-primary)',
      }}>
        {/* Header */}
        <header style={{
          padding:      '14px 24px',
          borderBottom: '1px solid var(--border)',
          display:      'flex',
          alignItems:   'center',
          gap:          12,
          background:   'var(--bg-primary)',
          flexShrink:   0,
        }}>
          <button
            onClick={() => setSidebarOpen(o => !o)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--text-secondary)', fontSize: 20, padding: '2px 6px',
              borderRadius: 6,
            }}
            title="Toggle sidebar"
          >☰</button>
          <span style={{ fontSize: 18, fontWeight: 600 }}>📋 Claims Assistant</span>
          {llmStatus === false && (
            <span style={{
              marginLeft: 'auto', fontSize: 12, color: 'var(--warning)',
              background: 'rgba(245,158,11,0.1)', padding: '3px 10px',
              borderRadius: 'var(--radius-full)',
            }}>
              ⚠️ Ollama offline — run: ollama serve
            </span>
          )}
          {llmStatus === true && (
            <span style={{
              marginLeft: 'auto', fontSize: 12, color: 'var(--accent)',
              background: 'var(--accent-light)', padding: '3px 10px',
              borderRadius: 'var(--radius-full)',
            }}>
              ● AI ready
            </span>
          )}
        </header>

        {/* Chat messages */}
        <ChatWindow
          messages = {messages}
          loading  = {loading}
        />

        {/* Input bar */}
        <InputBar
          onAsk    = {handleAsk}
          onClear  = {handleClear}
          loading  = {loading}
          hasMessages = {messages.length > 0}
        />
      </div>
    </div>
  )
}
