import React, { useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || `${window.location.protocol}//${window.location.hostname}:8000`

export default function Chat() {
  const [messages, setMessages] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState('')

  // load available models on mount
  React.useEffect(() => {
    let mounted = true
    ;(async () => {
      try {
        const r = await fetch(`${API_BASE}/llm/models`)
        if (!r.ok) return
        const j = await r.json()
        if (!mounted) return
        setModels(j.models || [])
        if (j.models && j.models.length > 0) setSelectedModel(j.models[0])
      } catch (e) {
        console.warn('Failed to load LLM models', e)
      }
    })()
    return () => { mounted = false }
  }, [])

  const handleSend = async () => {
    if (!query.trim()) return
    const userMsg = { text: query, type: 'user' }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)
    setQuery('')

    try {
      // include selected model if present
      const url = `${API_BASE}/ask?q=${encodeURIComponent(userMsg.text)}${selectedModel ? `&model=${encodeURIComponent(selectedModel)}` : ''}`
      const resp = await fetch(url)
      if (!resp.ok) {
        const errText = await resp.text()
        // Put a friendly bot message with details toggle
        const friendly = 'LLM service unavailable. Please ensure the LLM server (Ollama) is running.'
        setMessages(prev => [...prev, { type: 'bot', answer: friendly, rawError: errText }])
        return
      }
      const data = await resp.json()

      // Bot message contains answer, sources, snippets, metadatas
      let answerText = data.answer || 'No response'
      let rawError = null
      // Detect LLM-style error payloads and show friendly message
      const llmErrPattern = /LLM|Connection refused|Failed to establish a new connection|HTTPConnectionPool|timeout|timed out/i
      if (typeof answerText === 'string' && llmErrPattern.test(answerText)) {
        rawError = answerText
        answerText = 'LLM service error. See details for raw error.'
      }

      const botMsg = {
        type: 'bot',
        answer: answerText,
        rawError,
        sources: data.sources || [],
        snippets: data.snippets || [],
        metadatas: data.metadatas || []
      }
      setMessages(prev => [...prev, botMsg])
    } catch (err) {
      console.error(err)
      const friendly = 'LLM service unavailable. Please ensure the LLM server (Ollama) is running.'
      const raw = err?.message || String(err)
      setMessages(prev => [...prev, { type: 'bot', answer: friendly, rawError: raw, sources: [], snippets: [] }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <div style={{ marginBottom: 8 }}>
        {models.length > 0 ? (
          <label>
            Model:
            <select value={selectedModel} onChange={e => setSelectedModel(e.target.value)} style={{ marginLeft: 8 }}>
              {models.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
        ) : (
          <div style={{ color: '#666' }}>LLM models unavailable</div>
        )}
      </div>
      <div className="chat-messages">
        {messages.map((m, idx) => (
          <div key={idx} className={`chat-message ${m.type}`}>
            {m.type === 'user' && <div className="user-text">{m.text}</div>}
            {m.type === 'bot' && (
              <div className="bot-block">
                <div className="bot-answer">{m.answer}</div>
                {m.rawError && (
                  <details className="error-details" style={{ marginTop: 8 }}>
                    <summary style={{ cursor: 'pointer', color: '#b94a48' }}>Show error details</summary>
                    <pre style={{ background: '#f6f6f6', padding: 8, borderRadius: 6, overflowX: 'auto' }}>{m.rawError}</pre>
                  </details>
                )}
                {m.sources && m.sources.length > 0 && (
                  <div className="bot-sources">
                    <strong>Sources:</strong>
                    <ul>
                      {m.sources.map((s, i) => (
                        <li key={i}>
                          <div className="source-id">{s}</div>
                          <div className="snippet">{m.snippets?.[i] ?? ''}</div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="chat-input">
        <input
          type="text"
          value={query}
          placeholder="Type your message..."
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
        />
        <button onClick={handleSend} disabled={loading}>
          {loading ? 'Sending...' : 'Send'}
        </button>
      </div>
    </>
  )
}
