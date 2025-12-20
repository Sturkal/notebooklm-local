# NotebookLM Function Processing - Quick Reference Guide

## Backend API Functions

### POST /upload
**Flow:** File Validation → Save → Extract → Pre-validate → Queue Background Indexing → Response

**Key Steps:**
1. Validate file extension (pdf, docx, txt)
2. Check file size ≤ 10 MB
3. Sanitize filename (UUID prefix + basename)
4. Extract text with optional OCR
5. Pre-validate chunks not empty
6. Queue background indexing
7. Return doc_id + metadata

**Error Codes:** 400 (bad file type), 413 (file too large), 500 (extraction failure)

---

### GET /ask?q=...&top_k=5&model=...
**Flow:** Embed Query → Vector Search → Build Context → Call LLM → Parse Response → Format Answer

**Key Steps:**
1. Validate query parameter
2. Embed query (384-D vector)
3. Search ChromaDB (top-k cosine similarity)
4. Build RAG prompt with context
5. Call LLM with retry logic (3 attempts, exponential backoff)
6. Parse tolerant response format
7. Return answer + sources

**Return:** {answer, sources, retrieved_chunks}

---

### GET /documents
**Flow:** Query All Chunks → Parse doc_ids → Group by doc_id → Aggregate Stats

**Return:** [{doc_id, count, sample_metadata}, ...]

---

### DELETE /documents/{doc_id}
**Flow:** Find Chunks matching {doc_id}_* → Delete from ChromaDB

**Return:** status: "deleted"

---

### GET /llm/models
**Flow:** Query Ollama → Parse Models → Return List

**Return:** {models: [list of model names]}

---

### GET /index/status/{doc_id}
**Flow:** Lookup _index_status[doc_id]

**Possible Values:** "pending" → "indexing" → "done" or "failed: error"

---

## Document Indexer

### __init__()
**Flow:** Setup db_dir → Lazy imports → Load SentenceTransformer → Init ChromaDB → Create collection

**Model:** all-MiniLM-L6-v2 (384-D embeddings)

---

### chunk_document(text)
**Flow:** Split by paragraphs → Keep short as-is → Split long with word chunks → Fallback to entire text

**Strategy:** Paragraph-first (preserve structure) → Word-level (respect size limits)

---

### index_document(doc_id, text)
**Flow:** Chunk → Embed (batch 64) → Validate → Generate IDs → Store in ChromaDB

**Chunk IDs:** {doc_id}_0, {doc_id}_1, etc.

---

### query(query_text, top_k=5)
**Flow:** Embed query → ChromaDB similarity search → Parse results → Return top-k chunks

**Search Metric:** Cosine similarity

---

### delete_document(doc_id)
**Flow:** Find {doc_id}_* chunks → Delete from ChromaDB

---

## Document Extraction

### extract_pdf()
**Flow:** Try PyMuPDF → If empty and OCR enabled → Convert to images → Tesseract OCR → Return results

**Returns:** (filename, text, ocr_used, page_count, ocr_truncated)

**Speed:** PyMuPDF ~1-5ms/page, OCR ~1-2 sec/page

---

### extract_docx()
**Flow:** Open DOCX → Extract paragraphs → Return

---

### extract_txt()
**Flow:** Open file → Read UTF-8 → Return

---

### extract()
**Flow:** Detect extension → Route to handler → Return results or None

---

## LLM Client

### chat(prompt, model=None)
**Flow:** Route to backend (Ollama or local) → Return response or error message

**Never raises exceptions** - returns error strings instead

---

### _ollama_chat(prompt, model=None)
**Flow:** 
```
Select model → Prepare payload → 
Retry loop (3 attempts):
  - POST request → Parse response → Extract content
  - On timeout: backoff (1s, 2s, 4s) → retry
  - On error: backoff → retry
→ Return response or error message
```

**Tolerant Parsing:** Handles multiple Ollama response formats

---

### list_models()
**Flow:** Query /models endpoint → Parse → Return model list or empty

**Error Handling:** Returns [] on any error (no exceptions)

---

## Frontend Functions

### Upload File
**Flow:** 
```
File input → FormData → POST /upload → Parse response → 
Poll status (optional) → Refresh docs list → Show toast
```

---

### Load Documents List
**Flow:** GET /documents → Parse → Render with delete buttons

---

### Chat Query
**Flow:**
```
Validate query → Select model → GET /ask → 
Parse response → Display answer + sources → Show loading state
```

---

### Model Selector
**Flow:** GET /llm/models → Parse → Populate dropdown

---

## Rate Limiting

### Middleware Function
**Flow:** Extract IP → Get endpoint → Calculate window → Check Redis/in-memory → Return 429 or allow

**Limits:** 5 uploads/min, 20 /ask queries/min per IP

**Backends:**
- Redis (atomic, distributed)
- In-memory (thread-safe, single-process)

---

## Error Handling Patterns

### Backend API
- Returns JSON error objects with `detail` field
- HTTP status codes: 400, 413, 429, 500
- Never exposes stack traces to frontend

### LLM Integration
- Catches all exceptions internally
- Returns error strings like `"[LLM timeout after 3 attempts]"`
- Frontend displays friendly message + collapsible raw error

### Frontend
- Validates user input before submission
- Shows toast notifications for errors
- Handles missing model list gracefully
- Graceful degradation on network errors

---

## Configuration Reference

### Environment Variables (Backend)
```
CORS: ALLOWED_ORIGINS
Database: CHROMA_DB_DIR, UPLOAD_DIR
Upload: MAX_UPLOAD_SIZE
Rate Limit: RATE_LIMIT_WINDOW, UPLOAD_RATE_LIMIT, ASK_RATE_LIMIT, REDIS_URL
LLM: LLM_BACKEND, OLLAMA_URL, OLLAMA_MODEL
```

### Environment Variables (Frontend)
```
VITE_API_BASE_URL (base URL for backend)
```

---

## Performance Characteristics

| Operation | Time | Notes |
|-----------|------|-------|
| PDF extraction (PyMuPDF) | 1-5 ms/page | Fast, embedded text only |
| PDF extraction (OCR) | 1-2 sec/page | Slow, scanned PDFs |
| Embedding 64 chunks | 50-100 ms | Batch processing |
| ChromaDB similarity search | 10-50 ms | Depends on collection size |
| LLM query (Ollama) | 1-10 sec | Depends on model and prompt |
| DOCX extraction | <100 ms | Fast |
| TXT extraction | <10 ms | Very fast |

---

## Status Values

### Indexing Status
- `"pending"` - Queued, not yet started
- `"indexing"` - Currently processing
- `"done"` - Successfully completed
- `"failed: error message"` - Failed with error

---

## Response Formats

### Upload Response
```json
{
  "status": "ok",
  "doc_id": "hex_string",
  "ocr_used": false,
  "page_count": 5,
  "ocr_truncated": false
}
```

### Documents Response
```json
{
  "documents": [
    {
      "doc_id": "abc123",
      "count": 12,
      "sample_metadata": {"source_filename": "report.pdf"}
    }
  ]
}
```

### Ask Response
```json
{
  "answer": "Answer text",
  "sources": ["doc123_5", "doc456_12"],
  "top_k": 5,
  "retrieved_chunks": [...]
}
```

### Models Response
```json
{
  "models": ["llama2:latest", "mistral:latest"]
}
```

---

## Common Scenarios

### User uploads large PDF with OCR enabled
1. File validation passes
2. PyMuPDF extraction returns empty (scanned PDF)
3. OCR fallback triggered
4. First N pages converted to images (respecting ocr_max_pages)
5. Tesseract processes each image
6. Background indexing queues with status="pending"
7. Frontend polls until status="done"
8. Toast shows ocr_used=true, page_count=50, ocr_truncated=true

### User asks question with no relevant context
1. Query embedded (384-D)
2. ChromaDB searches for similar chunks
3. Retrieved chunks don't contain relevant info
4. LLM instructed to return "I don't know" if answer not in context
5. LLM returns: "I don't know based on the provided documents"
6. Frontend displays answer + shows which docs were searched

### LLM server is unavailable
1. Chat query submitted
2. LLM client attempts request → timeout
3. Retry 1: waits 1s → timeout
4. Retry 2: waits 2s → timeout
5. Retry 3: waits 4s → fails
6. Returns error: `"[LLM timeout after 3 attempts]"`
7. Frontend shows: "Unable to connect to AI model" + collapsible raw error

---
