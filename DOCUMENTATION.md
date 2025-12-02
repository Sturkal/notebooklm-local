# NotebookLM RAG Project - Complete Documentation

**Last Updated:** After comprehensive code review and commenting

This document summarizes the complete NotebookLM RAG (Retrieval-Augmented Generation) project, including all components, architecture, and detailed code documentation.

## Project Overview

NotebookLM is a minimal local RAG demo that allows users to:
1. **Upload documents** (PDF, DOCX, TXT) with optional OCR for scanned PDFs
2. **Index documents** into a vector database (ChromaDB) with semantic embeddings (SentenceTransformer)
3. **Query documents** using similarity search and get answers from a local LLM (Ollama)
4. **Manage documents** with a user-friendly web interface (React + Vite)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend (React + Vite)                    │
│  - Upload documents with OCR options                            │
│  - View indexed documents                                       │
│  - Chat interface with model selector                           │
│  - Real-time indexing status tracking                           │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────────────┐
│                    Backend (FastAPI)                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Security & Performance Layer                            │   │
│  │  - CORS configuration (configurable origins)             │   │
│  │  - Rate limiting (Redis-backed or in-memory)             │   │
│  │  - Upload validation (whitelist, size limits)            │   │
│  │  - Filename sanitization                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Core Services                                           │   │
│  │  - Document extraction (PDF/DOCX/TXT + OCR)              │   │
│  │  - Text chunking (paragraph-first strategy)              │   │
│  │  - Vector embedding (SentenceTransformer batch)          │   │
│  │  - ChromaDB storage & retrieval                          │   │
│  │  - Background indexing with status tracking              │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  LLM Integration                                         │   │
│  │  - Ollama client with retries & timeouts                 │   │
│  │  - Tolerant response parsing                             │   │
│  │  - Model listing for frontend selector                   │   │
│  │  - RAG prompt building                                   │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────┬──────────────────────────────────────┬─────┘
                     │                                      │
        ┌────────────▼───────────┐            ┌────────────▼──────────┐
        │   ChromaDB + SQLite    │            │   Ollama LLM Server   │
        │   (Vector Database)    │            │   (Local Models)      │
        └────────────────────────┘            └───────────────────────┘
        
Optional:
        ┌──────────────────────────────────────────────────────────┐
        │   Redis (Rate Limiting)                                  │
        │   Distributed counter-based rate limiting                │
        └──────────────────────────────────────────────────────────┘
```

## Detailed Component Documentation

### 1. Backend API (`backend/api/main.py`)

**Purpose:** FastAPI web server providing RAG endpoints

**Key Endpoints:**
- `POST /upload` — Upload & queue document for indexing
- `GET /ask?q=...` — Query indexed documents + get LLM answer
- `GET /documents` — List all indexed documents
- `DELETE /documents/{doc_id}` — Remove a document
- `GET /llm/models` — List available LLM models
- `GET /index/status/{doc_id}` — Check background indexing progress
- `GET /health` — Health check

**Key Features:**

1. **CORS Configuration**
   - Configurable via `ALLOWED_ORIGINS` environment variable
   - Prevents unauthorized cross-origin requests
   - Fallback to localhost origins for development

2. **Rate Limiting (per-IP, per-endpoint)**
   - **Backend:** Redis-backed atomic counters (distributed) or in-memory (single-process)
   - **Strategy:** Fixed-window counters (60-second windows)
   - **Limits:** 5 uploads/min, 20 /ask queries/min
   - **Graceful Fallback:** In-memory fallback if Redis unavailable

3. **Upload Validation**
   - File type whitelist: `.pdf`, `.docx`, `.txt`
   - Size limit: 10 MB default (configurable)
   - Filename sanitization: UUID prefix + basename extraction (prevents path traversal)
   - Pre-indexing validation: Ensures document produces non-empty chunks before queuing

4. **Background Indexing**
   - Asynchronous: Returns immediately to client, indexes in background
   - Status tracking: `pending` → `indexing` → `done|failed`
   - Frontend can poll `/index/status/{doc_id}` to monitor progress
   - Thread-fallback: Works with or without FastAPI BackgroundTasks

5. **RAG Query Pipeline**
   - Retrieves top-k similar chunks via vector search
   - Builds context string with chunk IDs
   - Creates prompt instructing LLM to use only provided context
   - Handles source citations and "unknown" cases

**Environment Variables:**
```
ALLOWED_ORIGINS     : Comma-separated list of allowed CORS origins
CHROMA_DB_DIR       : Path for ChromaDB persistence (default "./chroma_db")
UPLOAD_DIR          : Where uploaded files are stored (default ".uploads")
MAX_UPLOAD_SIZE     : Max file size in bytes (default 10485760)
RATE_LIMIT_WINDOW   : Rate limit window in seconds (default 60)
UPLOAD_RATE_LIMIT   : Max uploads per window (default 5)
ASK_RATE_LIMIT      : Max /ask requests per window (default 20)
REDIS_URL           : Optional Redis URL (e.g., redis://redis:6379/0)
LLM_BACKEND         : LLM backend type (default "ollama")
OLLAMA_URL          : Ollama server URL (default "http://localhost:11434")
OLLAMA_MODEL        : Default LLM model name (default "llama3.1")
```

---

### 2. Document Indexer (`backend/indexer.py`)

**Purpose:** Text chunking, embedding, and vector storage

**Class: Indexer**

**Initialization (Lazy Loading)**
- Defers importing SentenceTransformer & ChromaDB until instantiation
- Improves startup time and enables easier testing (can mock without loading models)
- Loads `all-MiniLM-L6-v2` embedding model (384-dimensional)

**Key Methods:**

1. **`chunk_document(text, chunk_size=512, chunk_overlap=50)`**
   - Strategy: Paragraph-first (split by `\n\n`), then word-level if needed
   - Respects document structure before breaking sentences
   - Fallback: Returns entire text if no chunks generated
   - Returns: `List[str]` of non-empty chunks

2. **`index_document(doc_id, text, metadata=None)`**
   - Chunks text, generates embeddings, stores in ChromaDB
   - Batch embedding (batch_size=64) for efficiency
   - Defensive: Validates non-empty chunks and embeddings
   - Stores metadata (e.g., `{"source_filename": "..."}`)
   - Returns: Nothing (raises on error)

3. **`query(query_text, top_k=5)`**
   - Embeds query using same model as documents
   - Searches ChromaDB by cosine similarity
   - Returns: `{"documents": [[chunks]], "ids": [[ids]], "metadatas": [[metadata]]}`
   - Handles variable ChromaDB response shapes

4. **`list_documents()`**
   - Aggregates chunks by doc_id (chunks named `{doc_id}_{i}`)
   - Returns: `[{"doc_id": ..., "count": ..., "sample_metadata": ...}, ...]`
   - Handles different ChromaDB response shapes

5. **`delete_document(doc_id)`**
   - Removes all chunks matching `{doc_id}_*`
   - Returns: `True` if deleted, `False` if not found
   - Irreversible operation

**Environment Variables:**
```
CHROMA_DB_DIR  : Path for ChromaDB persistence (default "./chroma_db")
               In Docker, set to "/data/chroma" for volume mount
```

---

### 3. Document Extraction (`backend/extract.py`)

**Purpose:** Extract text from PDF, DOCX, and TXT files with OCR fallback

**Key Functions:**

1. **`extract_pdf(file_path, ocr_enabled=False, ocr_max_pages=None)`**
   - **Fast Path:** PyMuPDF (fitz) text extraction
   - **Fallback:** If no text found and OCR enabled, render pages + Tesseract OCR
   - **Page Limiting:** Respect ocr_max_pages (e.g., scan first 10 pages only)
   - Returns: `(filename, text, ocr_used, page_count, ocr_truncated)`

2. **`extract_docx(file_path)`**
   - Extract paragraphs from Word document
   - Returns: `(filename, text, False, 0, False)`

3. **`extract_txt(file_path)`**
   - Read plain text file (UTF-8)
   - Returns: `(filename, text, False, 0, False)`

4. **`extract(file_path, ocr_enabled=False, ocr_max_pages=None)`**
   - Dispatcher: Determines file type and calls appropriate function
   - Returns: `(filename, text, ocr_used, page_count, ocr_truncated)` or `None`

**Return Tuple:**
- `filename`: Original filename (basename)
- `text`: Extracted text content
- `ocr_used`: Whether OCR was actually used (PDF only)
- `page_count`: Total pages in document (PDF only, 0 for others)
- `ocr_truncated`: Whether OCR hit the max_pages limit (PDF only)

**System Requirements for OCR:**
```
Linux:   apt-get install tesseract-ocr poppler-utils
macOS:   brew install tesseract poppler
Windows: choco install tesseract poppler (or download binaries)
```

**Python Packages:**
```
pytesseract, pdf2image (conditional, checked at import time)
```

---

### 4. LLM Client (`backend/llm_client.py`)

**Purpose:** Interface to Large Language Models (LLM)

**Class: LLMClient**

**Key Methods:**

1. **`chat(prompt, model=None)`**
   - Send prompt to LLM, get response
   - Routes to `_ollama_chat()` or `_local_stub()` based on backend
   - Returns: `str` (response or error message)
   - **Never raises exceptions** (returns error strings instead)

2. **`_ollama_chat(prompt, model=None)`**
   - Queries Ollama `/chat` endpoint
   - **Retry Logic:** Exponential backoff (1s, 2s, 4s) for transient failures
   - **Timeouts:** 30-second HTTP timeout prevents hanging
   - **Response Parsing (Tolerant):** Handles multiple Ollama response shapes:
     - `{"message": {"content": "..."}}`
     - `{"choices": [{"message": {"content": "..."}}]}`
     - `{"response": "..."}` / `{"output": "..."}`
   - Returns: LLM response or error message like `"[LLM timeout after 3 attempts]"`

3. **`list_models()`**
   - Queries Ollama `/models` endpoint
   - Returns: `list` of model names (e.g., `["llama3.1", "mistral", ...]`)
   - Returns: Empty list on error (no exceptions)
   - Parses multiple response shapes (list, dict with "models" key, dict of models)

4. **`_local_stub(prompt)`**
   - Placeholder for future local LLM backend
   - Returns: `"[Local LLM backend not configured]"`

**Global Instance:**
```python
llm = LLMClient()  # Singleton, used throughout backend
```

**Configuration (Environment Variables):**
```
LLM_BACKEND  : "ollama" (default) or "local"
OLLAMA_URL   : Ollama server URL (default "http://localhost:11434")
OLLAMA_MODEL : Default model name (default "llama3.1")
```

---

### 5. Frontend (`frontend/src/`)

**Files:**
- `App.jsx` — Main UI (upload, documents list)
- `components/Chat.jsx` — Chat component (model selector, queries, answers)
- `style.css` — Styles (scrollable areas, spinner, toasts, errors)
- `main.jsx` — React entry point
- `index.html` — HTML template

**Key Features:**

1. **Upload Panel**
   - File input with validation feedback
   - OCR toggle + page limit input
   - Upload spinner (shows when OCR enabled)
   - Success toast with `ocr_used`, `page_count`, `ocr_truncated`

2. **Documents List**
   - Scrollable sidebar (max-height: 400px)
   - Shows doc_id, chunk count, sample metadata
   - Delete button per document
   - Real-time updates on upload/delete

3. **Chat Interface**
   - Model dropdown (fetched from backend `/llm/models`)
   - Query input + send button
   - Display LLM response + sources + snippets
   - Friendly LLM error handling (shows user-friendly message + collapsible details)
   - Scrollable message area

4. **Responsive Design**
   - Grid layout: upload panel | documents list | chat
   - Scrollable areas for long content
   - Toast notifications (success, error)

**Environment Variables (Build Time):**
```
VITE_API_BASE_URL : Backend URL (e.g., http://localhost:8000)
               Docker sets to http://backend:8000
               Dev fallback: http://localhost:8000
```

---

## Testing

**Test Suite:** `backend/tests/test_api.py`

**Tests (5 total, all passing):**
1. `test_health` — Verify `/health` endpoint
2. `test_upload_txt_success` — Upload TXT file, verify doc_id and status
3. `test_list_documents` — List documents after upload
4. `test_delete_document` — Delete a document
5. `test_upload_too_large` — Reject file exceeding size limit

**Test Setup:**
- Uses `TestClient` from FastAPI
- `StubIndexer` test double (avoids loading ML models)
- Temporary upload directory for each test
- Cleanup via fixtures

**Running Tests:**
```bash
# In Docker
docker compose run --rm backend python -m pytest -v

# Locally (requires pytest, httpx, fastapi, starlette)
cd backend
pytest -v
pytest -v --cov  # With coverage
```

---

## Deployment

### Docker (Recommended)

**Services:**
- `backend` — FastAPI + Python 3.10 (includes Tesseract, Poppler)
- `frontend` — Node 22 + Vite React dev server
- `redis` — Optional (for distributed rate limiting)

**Quick Start:**
```bash
cd d:/projects/notebooklm-local
docker compose build
docker compose up -d

# Access:
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
```

**Environment Variables (docker-compose.yml):**
```yaml
backend:
  environment:
    CHROMA_DB_DIR: /data/chroma
    UPLOAD_DIR: /tmp/uploads
    REDIS_URL: redis://redis:6379/0
    OLLAMA_URL: http://host.docker.internal:11434
```

### Local Deployment

**Backend:**
```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
# Vite dev server at http://localhost:5173
```

**Requirements:**
- Python 3.10+
- Node.js 18+
- Ollama running (for LLM)
- Redis (optional, for distributed rate limiting)
- System packages: tesseract-ocr, poppler (for OCR)

---

## Security Considerations

1. **CORS:** Configure `ALLOWED_ORIGINS` in production
2. **Rate Limiting:** Enable Redis for distributed deployments
3. **File Upload:** Whitelist extensions, enforce size limits, sanitize filenames
4. **LLM Integration:** Timeout prevents denial-of-service via slow LLM
5. **Error Messages:** User-friendly error strings (not stack traces)

---

## Performance Optimization

1. **Lazy Initialization:** Indexer loads ML models only on first use
2. **Batch Embedding:** Processes 64 chunks at once (vs. per-chunk)
3. **Async Indexing:** Background tasks don't block upload response
4. **Chunking Strategy:** Paragraph-first reduces chunk count vs. word-only
5. **Status Tracking:** Lightweight dict (no DB overhead) for indexing progress
6. **Redis Rate Limiting:** Atomic counters vs. in-memory cleanup (faster)

---

## Troubleshooting

### Ollama Not Responding
```
Symptom: Chat shows "[LLM error: Connection refused]"
Fix: Ensure Ollama is running
     docker run -d -p 11434:11434 ollama/ollama
     ollama serve  # or use Docker
```

### OCR Failures
```
Symptom: PDF upload fails or returns no text
Fix: Ensure Tesseract and Poppler installed
     choco install tesseract poppler (Windows)
     apt-get install tesseract-ocr poppler-utils (Linux)
```

### ChromaDB Errors
```
Symptom: "No such table" or collection errors
Fix: Remove chroma_db/ directory, restart (recreates)
     docker volume prune  (if using Docker volumes)
```

### Rate Limiting (429 errors)
```
Symptom: "Too many requests"
Fix: Wait RATE_LIMIT_WINDOW seconds (default 60)
     Or enable Redis: REDIS_URL=redis://localhost:6379/0
```

---

## Future Enhancements

1. **Model Persistence:** Save selected model to localStorage
2. **OCR Metadata:** Store page_count, ocr_truncated in document metadata
3. **Soft Delete:** Archive documents instead of hard delete
4. **Advanced Retrieval:** Hybrid search (keyword + semantic)
5. **Streaming Responses:** Stream LLM output to frontend
6. **Web Scraping:** Add URL-based document sources
7. **Fine-tuning:** Adapt embeddings to domain-specific vocabulary
8. **API Authentication:** JWT or API key for external access

---

## Files Summary

```
notebooklm-local/
├── docker-compose.yml              # Multi-service orchestration
├── README.md                         # User-facing documentation
├── DOCUMENTATION.md                  # This file (technical reference)
├── backend/
│   ├── Dockerfile                    # Backend image (Python 3.10-slim + deps)
│   ├── requirements.txt              # Python dependencies
│   ├── api/
│   │   ├── main.py                   # FastAPI app (635 lines, fully commented)
│   │   └── __init__.py
│   ├── indexer.py                    # Indexer class (362 lines, fully commented)
│   ├── extract.py                    # Document extraction (213 lines, fully commented)
│   ├── llm_client.py                 # LLM client (332 lines, fully commented)
│   ├── chroma_db/                    # ChromaDB persistence (SQLite)
│   ├── .uploads/                     # Uploaded files (temporary)
│   └── tests/
│       └── test_api.py               # Pytest suite (5 tests, all passing)
└── frontend/
    ├── Dockerfile                    # Frontend image (Node 22-alpine)
    ├── package.json                  # Node dependencies + scripts
    ├── vite.config.js               # Vite build config
    ├── index.html                    # HTML template
    ├── src/
    │   ├── App.jsx                   # Main component (upload + documents + chat)
    │   ├── components/
    │   │   └── Chat.jsx              # Chat component (model selector + messages)
    │   ├── style.css                 # Styling
    │   ├── main.jsx                  # Entry point
    │   └── components/
    │       └── Toast.jsx             # Toast notification (optional)
    └── public/                        # Static assets
```

---

## Testing Checklist

- ✅ All 5 pytest tests passing
- ✅ Docker build successful (all dependencies cached)
- ✅ Services running (backend:8000, frontend:3000, redis:6379)
- ✅ Upload endpoint validates file types & sizes
- ✅ OCR fallback works for scanned PDFs
- ✅ Model selector fetches from backend
- ✅ Rate limiting enforced (429 responses)
- ✅ CORS configured (frontend can call backend)
- ✅ Background indexing tracked (status endpoint works)
- ✅ Friendly LLM error display in chat UI

---

**Project Status:** ✅ **Production Ready**

All features implemented, tested, documented, and deployed. See README.md for user-facing setup instructions.
