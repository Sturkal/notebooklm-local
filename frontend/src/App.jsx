import React, { useState, useEffect } from 'react'
import Chat from './components/Chat'
import './style.css'

// Determine API base URL:
// - If VITE_API_BASE_URL is set (for Docker), use it
// - Otherwise use window.location to dynamically determine (for host browser)
const API_BASE = import.meta.env.VITE_API_BASE_URL || `${window.location.protocol}//${window.location.hostname}:8000`

function Toast({ toast, onClose }) {
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => onClose(), 4000)
    return () => clearTimeout(t)
  }, [toast])

  if (!toast) return null
  return (
    <div className={`toast ${toast.type || 'info'}`}>
      {toast.text}
    </div>
  )
}

export default function App() {
  const [uploading, setUploading] = useState(false)
  const [selectedFile, setSelectedFile] = useState(null)
  const [enableOCR, setEnableOCR] = useState(false)
  const [ocrMaxPages, setOcrMaxPages] = useState(10)
  const [toast, setToast] = useState(null)
  const [documents, setDocuments] = useState([])

  const loadDocuments = async () => {
    try {
      const r = await fetch(`${API_BASE}/documents`)
      if (!r.ok) return
      const j = await r.json()
      setDocuments(j.documents || [])
    } catch (err) {
      console.error('Không thể tải tài liệu', err)
    }
  }

  useEffect(() => {
    loadDocuments()
  }, [])

  const handleUpload = async () => {
    const input = document.getElementById('fileinput')
    const f = input?.files?.[0]
    if (!f) {
      setToast({ text: 'Vui lòng chọn tệp để tải lên', type: 'error' })
      return
    }

    // Client-side validation: block empty files
    if (f.size === 0) {
      setToast({ text: 'Tệp đã chọn trống', type: 'error' })
      return
    }

    setSelectedFile(f.name)
    setUploading(true)
    try {
      if (enableOCR) {
        setToast({ text: 'Đang cố gắng OCR (có thể mất nhiều thời gian hơn)...', type: 'info' })
      }
      const fd = new FormData()
      fd.append('file', f)
      // pass OCR preferences to backend
      fd.append('enable_ocr', enableOCR ? 'true' : 'false')
      fd.append('ocr_max_pages', String(ocrMaxPages))
      const r = await fetch(`${API_BASE}/upload`, { method: 'POST', body: fd })
      if (!r.ok) {
        const errText = await r.text()
        throw new Error(errText || `HTTP ${r.status}`)
      }
      const j = await r.json()
      // Compose success message with OCR/page info if present
      let msg = `Đã tải lên: ${j.doc_id}`
      if (j.ocr_used) msg += ' (đã sử dụng OCR)'
      if (j.page_count !== undefined) msg += ` — trang: ${j.page_count}`
      if (j.ocr_truncated) msg += ' — OCR bị cắt bớt đến số trang tối đa'
      setToast({ text: msg, type: 'success' })
      // clear input
      input.value = ''
      setSelectedFile(null)
      // refresh documents list
      loadDocuments()
    } catch (err) {
      console.error(err)
      setToast({ text: `Tải lên thất bại: ${err.message}`, type: 'error' })
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="app-container">
      <Toast toast={toast} onClose={() => setToast(null)} />
      <div className="sidebar">
        <h3>Notebooks</h3>
        <div>• Default Notebook</div>
        <hr />
        <h4>Upload Document</h4>
        <input id="fileinput" type="file" />
        <div style={{ marginTop: 8 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input type="checkbox" checked={enableOCR} onChange={e => setEnableOCR(e.target.checked)} />
            Enable OCR fallback
          </label>
          {enableOCR && (
            <div style={{ marginTop: 6 }}>
              <label>
                OCR max pages: 
                <input type="number" min={1} max={100} value={ocrMaxPages} onChange={e => setOcrMaxPages(Number(e.target.value))} style={{ width: 80, marginLeft: 8 }} />
              </label>
            </div>
          )}
        </div>
        <div style={{ marginTop: 8 }}>
          <button onClick={handleUpload} disabled={uploading}>
            {uploading ? (
              enableOCR ? (
                <span className="btn-with-spinner">Đang tải lên (OCR đang tiến hành)... <span className="spinner"/></span>
              ) : (
                'Đang tải lên...'
              )
            ) : 'Tải lên tài liệu'}
          </button>
        </div>
        {selectedFile && <div className="file-selected">Selected: {selectedFile}</div>}
        <hr />
        <div className="documents-scroll">
          <h4>Uploaded Documents</h4>
          <div>
            {documents.length === 0 && <div style={{ color: '#666' }}>No documents indexed yet.</div>}
            <ul style={{ paddingLeft: 16 }}>
              {documents.map(d => (
                <li key={d.doc_id} style={{ marginBottom: 6 }}>
                  <strong>{d.doc_id}</strong> — {d.count} chunk(s)
                  {d.sample_metadata?.source_filename && (
                    <div style={{ fontSize: 12, color: '#444' }}>File: {d.sample_metadata.source_filename}</div>
                  )}
                  <div style={{ marginTop: 4 }}>
                    <button onClick={async () => {
                      if (!confirm('Xóa tài liệu và các đoạn của nó?')) return
                      try {
                        const resp = await fetch(`${API_BASE}/documents/${d.doc_id}`, { method: 'DELETE' })
                        if (!resp.ok) throw new Error(await resp.text())
                        setToast({ text: `Đã xóa ${d.doc_id}`, type: 'info' })
                        loadDocuments()
                      } catch (e) {
                        setToast({ text: `Xóa không thành công: ${e.message}`, type: 'error' })
                      }
                    }} style={{ marginRight: 8 }}>Delete</button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <div className="chat-area">
        <Chat />
      </div>
    </div>
  )
}
