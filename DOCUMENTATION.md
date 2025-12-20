# NotebookLM RAG Project - Complete Documentation

**Last Updated:** 2025-12-19 — dependency cleanup

Changelog (2025-12-19):
- Removed unused Python packages from `backend/requirements.txt`: `pandas`, `python-dotenv`, `httpx`.
- Relaxed `chromadb` pin to `chromadb>=0.5.23` to allow newer compatible releases.
- Removed unused frontend dependency `axios` from `frontend/package.json` (code uses `fetch`).
- Removed unused imports across backend Python modules and formatted code with `black`.

This document summarizes the complete NotebookLM RAG (Retrieval-Augmented Generation) project, including all components, architecture, and detailed code documentation. The changelog above notes the recent cleanup and recommended next steps to update your local environment.

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

**Detailed Function Processing:**

#### 1.1 `POST /upload` Function Flow

**Process Overview:**
```
File Submitted → Validation → File Save → Text Extraction → 
Pre-validation → Background Indexing Scheduled → Response
```

**Step-by-Step Processing:**

1. **Filename Validation & Sanitization**
   - Extract extension from uploaded filename
   - Check extension against whitelist (`.pdf`, `.docx`, `.txt`)
   - Return 400 error if invalid file type
   - Generate safe filename: `{uuid}_{original_filename}` (max 240 chars)
   - Purpose: Prevent path traversal attacks and filename collisions

2. **File Size Validation**
   - Read complete file into memory
   - Check file size against `MAX_UPLOAD_SIZE` (default 10 MB)
   - Return 413 error if file too large
   - Save file to `UPLOAD_DIR` on disk

3. **Text Extraction**
   - Route to appropriate extractor based on file extension
   - PDF: Use PyMuPDF for fast extraction, optionally fallback to OCR
   - DOCX: Extract paragraphs from Word document
   - TXT: Read as plain UTF-8 text
   - Return tuple: `(filename, text, ocr_used, page_count, ocr_truncated)`

4. **Pre-validation of Chunks**
   - Attempt to chunk extracted text (paragraph-first strategy)
   - If no non-empty chunks generated, raise error (early fail)
   - Purpose: Catch empty documents before scheduling background work
   - Log text preview for debugging

5. **Metadata Preparation**
   - Create metadata dict: `{"source_filename": orig_filename}`
   - This metadata travels with each chunk through indexing

6. **Background Indexing Scheduling**
   - Generate unique `doc_id` (UUID hex string)
   - Initialize status: `_index_status[doc_id] = "pending"`
   - Schedule `_run_index_background()` via FastAPI BackgroundTasks
   - Purpose: Return immediately to user; heavy indexing happens asynchronously

7. **Response**
   ```json
   {
     "status": "ok",
     "doc_id": "abc123def456...",
     "ocr_used": false,
     "page_count": 5,
     "ocr_truncated": false
   }
   ```

#### 1.2 `_run_index_background()` Function Flow

**Process Overview:**
```
Status = "indexing" → Chunk Text → Create Embeddings → 
Store in ChromaDB → Status = "done" (or "failed")
```

**Step-by-Step Processing:**

1. **Status Update**
   - Set `_index_status[doc_id] = "indexing"` (thread-safe with lock)
   - Signals to frontend that processing has begun

2. **Document Chunking**
   - Call `Indexer.chunk_document()` with extracted text
   - Paragraph-first strategy: split by double newlines
   - Long paragraphs split into word-based chunks (size ~512 chars)
   - Returns list of text chunks (e.g., 5-50 chunks per typical document)

3. **Embedding Generation**
   - Convert each chunk to dense vector using SentenceTransformer
   - Model: `all-MiniLM-L6-v2` (384-dimensional vectors)
   - Batch processing for efficiency: `batch_size=64`
   - Each chunk → one 384-D vector

4. **ChromaDB Storage**
   - Assign unique IDs to chunks: `{doc_id}_{chunk_index}`
   - Store in ChromaDB collection with:
     - Chunk text content
     - Embedding vector
     - Metadata (source filename, chunk index)
   - Purpose: Enable later semantic similarity search

5. **Status Update & Error Handling**
   - On success: `_index_status[doc_id] = "done"`
   - On error: `_index_status[doc_id] = "failed: error_message"`
   - Logs printed to stderr for debugging
   - Errors do NOT crash the backend (graceful failure)

#### 1.3 `GET /ask?q=...&top_k=5&model=...` Function Flow

**Process Overview:**
```
Query Received → Embed Query → Vector Search → 
Build RAG Prompt → Call LLM → Parse Response → Return Answer
```

**Step-by-Step Processing:**

1. **Input Validation**
   - Extract query parameter `q` (required)
   - Extract optional `top_k` (default 5) — number of chunks to retrieve
   - Extract optional `model` (default from env) — LLM model to use
   - Return 400 error if query missing or empty

2. **Query Embedding**
   - Convert user's question to vector using same model as documents
   - Uses `Indexer.embed_model.encode(query)` → 384-D vector
   - Purpose: Enable semantic similarity comparison with document chunks

3. **Vector Similarity Search**
   - Query ChromaDB collection with embedded query vector
   - Retrieve top-k chunks by cosine similarity
   - Returns:
     - Chunks: most similar text snippets
     - IDs: chunk identifiers (e.g., "doc123_5")
     - Distances: similarity scores (lower = more similar)
     - Metadata: source filenames

4. **RAG Context Building**
   - Concatenate retrieved chunks into single context string
   - Add source citations: include chunk IDs in context
   - Format example:
     ```
     Context from indexed documents:
     [ID: doc123_5] This is the relevant text chunk...
     [ID: doc456_12] Another related section...
     ```

5. **LLM Prompt Construction**
   - Build prompt instructing LLM to:
     - Answer user question using ONLY provided context
     - Return "I don't know" if answer not in context
     - Cite sources using chunk IDs
   - Example prompt:
     ```
     You are a helpful assistant. Answer the following question using 
     ONLY the context provided. If the answer is not in the context, 
     respond with "I don't know".
     
     Context: [concatenated chunks with IDs]
     
     Question: [user's question]
     
     Answer:
     ```

6. **LLM Query**
   - Call `llm_client.chat(prompt, model=model)`
   - Backend: Ollama (or other configured LLM)
   - Includes retry logic (up to 3 attempts with exponential backoff)
   - Timeout: 30 seconds per request

7. **Response Parsing**
   - Handle various LLM response formats (tolerant parsing)
   - Extract text content from structured responses
   - Handle timeouts and errors gracefully

8. **Response Formatting**
   ```json
   {
     "answer": "LLM's response text here",
     "sources": ["doc123_5", "doc456_12"],
     "top_k": 5,
     "retrieved_chunks": [
       {"id": "doc123_5", "text": "chunk content...", "metadata": {...}},
       ...
     ]
   }
   ```

#### 1.4 `simple_rate_limiter()` Middleware Function Flow

**Process Overview:**
```
Request Received → Extract Client IP → Determine Endpoint →
Redis/In-Memory Lookup → Count Requests in Window → 
Check Limits → Return 429 or Allow Request
```

**Step-by-Step Processing:**

1. **Client Identification**
   - Extract client IP address from request
   - Fallback to "unknown" if IP not available
   - Purpose: Track rate limits per-IP (prevent one user flooding server)

2. **Endpoint Identification**
   - Extract URL path (e.g., "/upload", "/ask")
   - Determine rate limit category:
     - `/upload` → UPLOAD_RATE_LIMIT (default 5/min)
     - `/ask*` → ASK_RATE_LIMIT (default 20/min)

3. **Time Window Calculation**
   - Current time (seconds since epoch)
   - Window key = `current_time // RATE_LIMIT_WINDOW`
   - Fixed-window strategy: 60-second windows (e.g., 00:00-00:59, 01:00-01:59)

4. **Redis-backed Rate Limiting** (if configured)
   - Check if Redis available via `REDIS_URL`
   - Generate Redis key: `rl:{client_ip}:{endpoint}:{window}`
   - Atomically increment counter: `INCR key`
   - Set expiry: Window lifetime + 1 second
   - Purpose: Distributed rate limiting (works across multiple server instances)

5. **In-Memory Fallback** (if Redis unavailable)
   - Thread-safe dictionary: `_requests_log[client_ip]`
   - Store list of `(timestamp, endpoint)` tuples
   - On each request:
     - Filter out old requests outside current window
     - Count endpoint-specific requests in window
     - Add new request tuple
   - Purpose: Single-process rate limiting (dev/test environments)

6. **Limit Enforcement**
   - Compare request count against configured limit
   - Return 429 (Too Many Requests) if limit exceeded:
     ```json
     {
       "detail": "Too many upload requests, try later"
     }
     ```
   - Otherwise allow request to proceed

#### 1.5 `GET /documents` Function Flow

**Process Overview:**
```
Query ChromaDB → Group Chunks by doc_id → 
Aggregate Statistics → Format Response
```

**Step-by-Step Processing:**

1. **Retrieve All Chunks**
   - Query ChromaDB collection without similarity filter
   - Get all documents/chunks in collection
   - Returns: document IDs, metadata, text content

2. **Parse Chunk IDs**
   - Chunk IDs follow pattern: `{doc_id}_{chunk_index}`
   - Extract doc_id by splitting on last underscore
   - Group chunks by doc_id

3. **Aggregate Statistics**
   - For each doc_id:
     - Count total chunks
     - Extract first chunk's metadata (sample_metadata)
     - Get source filename from metadata

4. **Response Formatting**
   ```json
   {
     "documents": [
       {
         "doc_id": "a1b2c3d4...",
         "count": 12,
         "sample_metadata": {
           "source_filename": "report.pdf"
         }
       },
       ...
     ]
   }
   ```

#### 1.6 `DELETE /documents/{doc_id}` Function Flow

**Process Overview:**
```
Request doc_id → Find All Chunks with doc_id → 
Delete from ChromaDB → Return Status
```

**Step-by-Step Processing:**

1. **Chunk ID Pattern Matching**
   - Retrieve all chunks from ChromaDB
   - Filter for chunks matching pattern: `{doc_id}_*`
   - Purpose: Find all chunks belonging to this document

2. **Bulk Deletion**
   - Delete all matched chunk IDs from ChromaDB
   - ChromaDB handles batch deletion efficiently
   - Metadata and vectors automatically removed

3. **Response**
   ```json
   {
     "status": "deleted",
     "doc_id": "a1b2c3d4...",
     "chunks_deleted": 12
   }
   ```

#### 1.7 `GET /llm/models` Function Flow

**Process Overview:**
```
Query Ollama → Parse Models → Format Response
```

**Step-by-Step Processing:**

1. **Ollama Endpoint Query**
   - Call `llm_client.list_models()`
   - Queries Ollama `/models` endpoint
   - Includes error handling and empty list fallback

2. **Response Formatting**
   ```json
   {
     "models": [
       "llama2:latest",
       "mistral:latest",
       "neural-chat:latest"
     ]
   }
   ```

#### 1.8 `GET /index/status/{doc_id}` Function Flow

**Process Overview:**
```
Request doc_id → Look up in Status Dict → Return Status
```

**Step-by-Step Processing:**

1. **Status Lookup**
   - Check `_index_status[doc_id]`
   - Possible values:
     - `"pending"` — queued, not yet started
     - `"indexing"` — currently processing chunks/embeddings
     - `"done"` — indexing completed successfully
     - `"failed: error message"` — indexing failed

2. **Response**
   ```json
   {
     "doc_id": "a1b2c3d4...",
     "status": "done",
     "timestamp": 1702968345
   }
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

#### 2.1 `__init__(db_dir=None)` Function Flow

**Process Overview:**
```
Validate db_dir → Create Directory → Load SentenceTransformer → 
Initialize ChromaDB → Get/Create Collection → Ready
```

**Step-by-Step Processing:**

1. **Database Directory Setup**
   - Use provided `db_dir` or fall back to `CHROMA_DB_DIR` env var
   - Default: `./chroma_db`
   - Create directory if it doesn't exist (recursive)
   - Purpose: Persistent storage location for embeddings database

2. **Lazy Imports**
   - Import `SentenceTransformer` from sentence-transformers library
   - Import `chromadb` for vector database operations
   - Deferred until instantiation (not at module load time)
   - Purpose: Faster startup; tests can mock without loading ML models

3. **Embedding Model Loading**
   - Initialize `SentenceTransformer("all-MiniLM-L6-v2")`
   - Model size: ~82 MB, downloads on first run
   - Output dimension: 384-D vectors
   - Purpose: Convert text to dense numerical embeddings for similarity search

4. **ChromaDB Initialization**
   - Create `PersistentClient` pointing to `db_dir`
   - SQLite backend: stores embeddings and metadata
   - Purpose: Durable vector database (survives server restarts)

5. **Collection Creation**
   - Get or create collection named `"notebook_collection"`
   - Collections isolate different sets of documents
   - Purpose: Store all indexed document chunks in single collection

6. **Error Handling**
   - If imports fail, raise `ImportError` immediately
   - Provides clear error message for missing dependencies
   - Purpose: Early failure with helpful error

#### 2.2 `chunk_document(text, chunk_size=512, chunk_overlap=50)` Function Flow

**Process Overview:**
```
Split by Paragraphs → Evaluate Each Paragraph → 
Split Long Paragraphs → Filter Empty → Return Chunks
```

**Step-by-Step Processing:**

1. **Input Validation**
   - Check if text is empty
   - Return empty list if no text
   - Purpose: Prevent errors on empty documents

2. **Paragraph Splitting**
   - Split text by double newlines (`\n\n`)
   - Strip whitespace from each paragraph
   - Filter out empty paragraphs
   - Purpose: Preserve document structure (paragraph-level semantics)

3. **Per-Paragraph Processing**
   - For each paragraph:
     - If length ≤ chunk_size (512 chars): keep as-is
     - If length > chunk_size: split into word-based chunks

4. **Long Paragraph Splitting**
   - Split paragraph into words
   - Heuristic word chunk size: `chunk_size / 5` (~100 words for 512 chars)
   - Create overlapping chunks: each chunk starts `(word_chunk_size - overlap_word_size)` words from previous
   - Purpose: Maintain semantic coherence while respecting chunk size limits

5. **Fallback Strategy**
   - If no chunks generated and text non-empty: return entire text as single chunk
   - Purpose: Ensure no text is ever lost, even if chunking fails

6. **Return Value**
   ```python
   [
     "Paragraph 1 content...",
     "Paragraph 2a content with overlap....",
     "Paragraph 2b continuation with overlap...",
     ...
   ]
   ```

#### 2.3 `index_document(doc_id, text, metadata=None)` Function Flow

**Process Overview:**
```
Chunk Text → Generate Embeddings → Validate Results → 
Store in ChromaDB → Persist to Disk
```

**Step-by-Step Processing:**

1. **Document Chunking**
   - Call `chunk_document(text, chunk_size=512, chunk_overlap=50)`
   - Returns list of text chunks
   - Validate: raise error if no chunks generated

2. **Embedding Generation**
   - Convert chunks to embeddings using SentenceTransformer
   - Batch processing: `encode(chunks, batch_size=64, show_progress_bar=False)`
   - Each chunk → 384-D vector
   - Fallback: for older sentence-transformers, omit `batch_size` parameter
   - Purpose: Efficient batching (reduces memory and improves speed)

3. **Embedding Validation**
   - Convert embeddings to NumPy array
   - Check array is non-empty
   - Check dimensions: shape[0] = number of chunks
   - Convert to list-of-lists format for ChromaDB
   - Purpose: Ensure embeddings are valid before storage

4. **Chunk ID Generation**
   - Assign IDs: `{doc_id}_{index}` for each chunk
   - Example: `abc123_0`, `abc123_1`, `abc123_2`, etc.
   - Purpose: Unique identification and later doc_id parsing

5. **Metadata Assignment**
   - Create metadata dict from input (e.g., `{"source_filename": "report.pdf"}`)
   - Replicate metadata to all chunks of same document
   - Purpose: Track source of each chunk for citation

6. **ChromaDB Storage**
   - Add chunks to collection with:
     - `ids`: chunk identifiers
     - `documents`: text content
     - `embeddings`: 384-D vectors
     - `metadatas`: metadata dicts
   - Purpose: Enable later semantic similarity search

7. **Persistence**
   - ChromaDB automatically persists to disk
   - SQLite database updated with embeddings
   - Purpose: Durable storage across server restarts

8. **Error Handling**
   - Raise `ValueError` if no chunks or embeddings
   - Raise exception on ChromaDB storage failure
   - Caller responsible for handling errors
   - Purpose: Fail-fast design (don't silently lose data)

#### 2.4 `query(query_text, top_k=5)` Function Flow

**Process Overview:**
```
Embed Query → Search ChromaDB → Parse Results → Return Chunks
```

**Step-by-Step Processing:**

1. **Query Embedding**
   - Convert user query to vector using same SentenceTransformer model
   - Example: "What is the capital of France?" → 384-D vector
   - Purpose: Enable cosine similarity comparison with document embeddings

2. **Vector Similarity Search**
   - Query ChromaDB collection with embedded query vector
   - Search metric: cosine similarity
   - Return top-k most similar chunks
   - Purpose: Find semantically relevant document segments

3. **Response Parsing**
   - ChromaDB returns variable response shapes across versions
   - Handle multiple formats:
     - `{"documents": [[...]], "ids": [[...]], "distances": [[...]], "metadatas": [[...]]}`
     - Normalize to consistent format
   - Purpose: Robustness across ChromaDB versions

4. **Return Value**
   ```python
   {
     "ids": [["doc123_5", "doc456_12", ...]],        # nested list
     "documents": [["chunk text 1", "chunk text 2", ...]],
     "distances": [[0.12, 0.34, ...]],               # cosine distances
     "metadatas": [[{"source_filename": "..."}, ...]]
   }
   ```

#### 2.5 `list_documents()` Function Flow

**Process Overview:**
```
Get All Chunks → Parse doc_ids → Group by doc_id → 
Aggregate Metadata → Return Summary List
```

**Step-by-Step Processing:**

1. **Retrieve All Chunks**
   - Query ChromaDB for all chunks in collection
   - Returns: all IDs, documents, and metadata

2. **Parse Document IDs**
   - Extract chunks following pattern: `{doc_id}_{chunk_index}`
   - Split ID on last underscore to get doc_id
   - Group chunks by doc_id

3. **Aggregate Statistics**
   - For each doc_id:
     - Count number of chunks
     - Extract sample metadata from first chunk
     - Example: `{"source_filename": "report.pdf"}`

4. **Return Value**
   ```python
   [
     {
       "doc_id": "a1b2c3d4e5f6...",
       "count": 12,                    # number of chunks
       "sample_metadata": {
         "source_filename": "report.pdf"
       }
     },
     ...
   ]
   ```

#### 2.6 `delete_document(doc_id)` Function Flow

**Process Overview:**
```
Find Chunks with doc_id → Delete from ChromaDB → Return Status
```

**Step-by-Step Processing:**

1. **Chunk Identification**
   - Query ChromaDB for all chunks
   - Filter for IDs matching pattern: `{doc_id}_*`
   - Example: find `abc123_0`, `abc123_1`, `abc123_2`, etc.

2. **Bulk Deletion**
   - Delete all matched chunk IDs from collection
   - ChromaDB removes:
     - Text content
     - Embedding vectors
     - Metadata
   - Purpose: Free up storage and prevent retrieval

3. **Return Value**
   ```python
   True  # if chunks were found and deleted
   False # if doc_id not found in collection
   ```

**Environment Variables:**
```
CHROMA_DB_DIR  : Path for ChromaDB persistence (default "./chroma_db")
               In Docker, set to "/data/chroma" for volume mount
```

---

### 3. Document Extraction (`backend/extract.py`)

**Purpose:** Extract text from PDF, DOCX, and TXT files with OCR fallback

**Key Functions:**

#### 3.1 `extract_pdf(file_path, ocr_enabled=False, ocr_max_pages=None)` Function Flow

**Process Overview:**
```
Open PDF → Try PyMuPDF Extraction → Check if Empty → 
(if empty & OCR enabled) Convert to Images → Run Tesseract → 
Return Results with Metadata
```

**Step-by-Step Processing:**

1. **File Opening**
   - Open PDF file using PyMuPDF (fitz) library
   - Extract total page count
   - Purpose: Prepare for text extraction

2. **Fast Text Extraction (PyMuPDF)**
   - Iterate through all pages
   - Extract text using `page.get_text()` method
   - Concatenate text from all pages
   - Purpose: Fast extraction for PDFs with embedded text (~milliseconds)

3. **Check Extraction Result**
   - If text extracted successfully (non-empty): proceed to return
   - If text is empty and OCR not enabled: return with `ocr_used=False`
   - If text is empty and OCR enabled: proceed to OCR fallback

4. **OCR Fallback (if enabled and text empty)**
   - Check if OCR dependencies available (pytesseract, pdf2image)
   - Return `ocr_used=False` if OCR not available
   - Convert PDF pages to images using `pdf2image.convert_from_path()`
   - Purpose: Create image representation for Tesseract OCR

5. **Page Limiting**
   - Check if `ocr_max_pages` specified (e.g., 10)
   - If document has more pages than limit:
     - Keep only first N images
     - Set `ocr_truncated=True`
   - Purpose: Prevent OCRing large documents (time-consuming)

6. **Tesseract OCR Processing**
   - For each image: run `pytesseract.image_to_string(image)`
   - Concatenate OCR results with newlines
   - Set `ocr_used=True`
   - Purpose: Extract text from scanned/image-based PDFs

7. **Error Handling**
   - Try-catch around entire process
   - On error: return with `ocr_used=False` (fallback gracefully)
   - Log error messages to stderr
   - Purpose: Prevent crashes on bad PDFs

8. **Return Value**
   ```python
   (
     filename,           # e.g., "report.pdf"
     text,              # extracted text content
     ocr_used,          # True if OCR fallback was used
     page_count,        # total pages in PDF
     ocr_truncated      # True if OCR hit max_pages limit
   )
   ```

**Time Complexity:**
- PyMuPDF extraction: O(n) where n = page count, ~1-5ms per page
- OCR: O(n*p) where p = image processing time, ~1-2 seconds per page (50-100x slower)

#### 3.2 `extract_docx(file_path)` Function Flow

**Process Overview:**
```
Open DOCX → Extract Paragraphs → Concatenate → Return
```

**Step-by-Step Processing:**

1. **File Opening**
   - Open DOCX file using `python-docx` library
   - Purpose: Parse Word document structure

2. **Paragraph Extraction**
   - Iterate through document paragraphs
   - Extract text from each paragraph: `para.text`
   - Concatenate with newlines
   - Purpose: Preserve paragraph structure from Word document

3. **Return Value**
   ```python
   (
     filename,           # e.g., "document.docx"
     text,              # extracted paragraph text
     False,             # ocr_used always False for DOCX
     0,                 # page_count not applicable (always 0)
     False              # ocr_truncated always False
   )
   ```

**Time Complexity:**
- O(n) where n = number of paragraphs, typically fast (<100ms)

#### 3.3 `extract_txt(file_path)` Function Flow

**Process Overview:**
```
Open File → Read Content → Return
```

**Step-by-Step Processing:**

1. **File Reading**
   - Open file in text mode (UTF-8 encoding)
   - Read entire content
   - Purpose: Simple plain-text extraction

2. **Return Value**
   ```python
   (
     filename,           # e.g., "notes.txt"
     text,              # file content
     False,             # ocr_used always False
     0,                 # page_count not applicable
     False              # ocr_truncated always False
   )
   ```

**Time Complexity:**
- O(n) where n = file size, typically very fast (<10ms for typical files)

#### 3.4 `extract(file_path, ocr_enabled=False, ocr_max_pages=None)` Function Flow

**Process Overview:**
```
Determine File Type → Route to Handler → Return Results
```

**Step-by-Step Processing:**

1. **File Type Detection**
   - Extract file extension from path
   - Convert to lowercase for case-insensitive matching
   - Purpose: Determine appropriate extraction method

2. **Routing Logic**
   - `.pdf` → call `extract_pdf(file_path, ocr_enabled, ocr_max_pages)`
   - `.docx` → call `extract_docx(file_path)`
   - `.txt` → call `extract_txt(file_path)`
   - Unknown extension → return `None` (unsupported type)

3. **Return Value**
   ```python
   (filename, text, ocr_used, page_count, ocr_truncated) or None
   ```

**Error Handling:**
- Wrapped in try-except (caller responsibility to handle exceptions)
- On error: return `None`
- Callers should check for `None` before proceeding

**Return Tuple Specification:**
- `filename` (str): Original filename (basename without directory)
- `text` (str): Extracted text content
- `ocr_used` (bool): Whether OCR fallback was used (PDF only)
- `page_count` (int): Total pages (PDF only, 0 for others)
- `ocr_truncated` (bool): Whether OCR hit max_pages limit (PDF only)

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

**Configuration (Environment Variables):**
```
LLM_BACKEND  : "ollama" (default) or "local"
OLLAMA_URL   : Ollama server URL (default "http://localhost:11434")
OLLAMA_MODEL : Default model name (default "llama3.1")
```

**Initialization:**
```python
def __init__(self, retries: int = 3, backoff: float = 1.0, timeout: int = 30):
    """
    Initialize LLMClient with retry and timeout configuration.
    
    Args:
        retries (int): Number of retry attempts for failed requests (default 3)
        backoff (float): Initial backoff multiplier for exponential backoff (default 1.0 second)
        timeout (int): HTTP request timeout in seconds (default 30)
    """
```

#### 4.1 `chat(prompt, model=None)` Function Flow

**Process Overview:**
```
Route to Backend → Call LLM → Return Response
```

**Step-by-Step Processing:**

1. **Backend Routing**
   - Check `self.backend` (from `LLM_BACKEND` env var)
   - If `"ollama"`: call `_ollama_chat()`
   - If `"local"` or other: call `_local_stub()`
   - Purpose: Support multiple LLM backends

2. **Return Value**
   - Always returns `str` (never raises exceptions)
   - LLM response text or error message like `"[LLM error: timeout]"`
   - Purpose: Graceful error handling for frontend

#### 4.2 `_ollama_chat(prompt, model=None)` Function Flow

**Process Overview:**
```
Select Model → Prepare Payload → Retry Loop:
  Make HTTP Request → Parse Response → Return Text
  or Backoff and Retry → Return Error Message
```

**Step-by-Step Processing:**

1. **Model Selection**
   - Use provided `model` parameter or fall back to `OLLAMA_MODEL` env var
   - Default: `"llama2:latest"`
   - Purpose: Allow per-request model override

2. **Endpoint URL Construction**
   - Legacy endpoint: `{OLLAMA_URL}/chat?model={model}`
   - V1 compatible endpoint: `{OLLAMA_URL}/v1/responses`
   - Purpose: Support both legacy and modern Ollama APIs

3. **Payload Preparation**
   - Legacy format: `{"messages": [{"role": "user", "content": prompt}]}`
   - V1 format: `{"model": model, "input": prompt}`
   - Purpose: Multi-API compatibility

4. **Retry Loop** (up to 3 attempts by default)
   - Attempt counter: `attempt = 0`
   - While `attempt < self.retries`:

   a. **HTTP Request**
   - POST to legacy endpoint with timeout
   - Log attempt number for debugging
   - Purpose: Query Ollama server
   
   b. **Fallback to V1 API**
   - If legacy returns 404, try V1 endpoint
   - Purpose: Automatic API fallback
   
   c. **Response Status Check**
   - Call `response.raise_for_status()`
   - On HTTPError: log warning and return error message
   - Purpose: Detect HTTP errors (5xx, 4xx)
   
   d. **JSON Parsing**
   - Parse response JSON
   - On ValueError: log warning, return raw text
   - Purpose: Robust response parsing
   
   e. **Response Extraction** (tolerant parsing)
   - Try multiple response shape patterns:
     - `response["message"]["content"]` (legacy format)
     - `response["choices"][0]["message"]["content"]` (OpenAI-compatible)
     - `response["choices"][0]["content"]` or `["text"]`
     - `response["output"][0]["content"][i]["text"]` (v1/responses format)
     - `response["response"]` (simple string format)
   - Fallback: serialize entire response as JSON string
   - Purpose: Handle variations across Ollama versions
   
   f. **Success Return**
   - Return extracted LLM response text
   - Purpose: Provide answer to user

   g. **Timeout Handling**
   - Catch `requests.exceptions.Timeout`
   - Increment attempt counter
   - If all retries exhausted: return `"[LLM timeout after N attempts]"`
   - Otherwise: sleep with exponential backoff
   - Backoff formula: `2^(attempt - 1)` seconds (1s, 2s, 4s, ...)
   - Purpose: Retry transient timeouts with increasing delays

   h. **General Exception Handling**
   - Catch `requests.exceptions.RequestException` (network errors)
   - Increment attempt counter
   - If all retries exhausted: return `"[LLM error: error_msg]"`
   - Otherwise: sleep with exponential backoff
   - Purpose: Retry transient network failures

5. **Return Value**
   - On success: `str` (LLM's response)
   - On timeout: `"[LLM timeout after N attempts]"`
   - On error: `"[LLM error: error_msg]"` or `"[LLM HTTP error: error_msg]"`
   - On non-JSON: raw response text or `"[LLM returned non-JSON response]"`

**Example Flow for Successful Response:**
```
Attempt 1: POST to /chat → 200 OK → Parse JSON → Extract "message.content" → Return "The capital of France is Paris"
```

**Example Flow for Timeout with Retry:**
```
Attempt 1: POST to /chat → Timeout → Sleep 1s
Attempt 2: POST to /chat → Timeout → Sleep 2s
Attempt 3: POST to /chat → 200 OK → Parse → Return response
```

**Example Flow for All Retries Failed:**
```
Attempt 1: POST → Timeout → Sleep 1s
Attempt 2: POST → Timeout → Sleep 2s
Attempt 3: POST → Timeout → Return "[LLM timeout after 3 attempts]"
```

#### 4.3 `list_models()` Function Flow

**Process Overview:**
```
Query Ollama Models Endpoint → Parse Responses → Return List
```

**Step-by-Step Processing:**

1. **Backend Check**
   - If backend is not `"ollama"`: log info and return empty list
   - Purpose: Model listing only supported for Ollama

2. **Ollama Models Endpoint Query**
   - POST to `{OLLAMA_URL}/models` endpoint
   - No authentication required (assumes local Ollama)
   - Timeout: 30 seconds
   - Purpose: Fetch available models from Ollama server

3. **Response Parsing** (tolerant handling)
   - Parse JSON response
   - Handle multiple response formats:
     - `{"models": [{"name": "model1"}, ...]}` (list of dicts)
     - `{"models": ["model1", "model2", ...]}` (list of strings)
     - `[{"name": "model1"}, ...]` (direct list)
     - `{"model1": {...}, "model2": {...}}` (dict of models, extract keys)
   - Purpose: Support variations across Ollama versions/endpoints

4. **Error Handling**
   - On any exception (network, parse, timeout): return empty list
   - Log warnings for debugging
   - Never raise exceptions
   - Purpose: Graceful fallback (frontend shows empty model dropdown)

5. **Return Value**
   ```python
   [
     "llama2:latest",
     "mistral:latest",
     "neural-chat:latest"
   ]
   ```
   Or empty list `[]` on error

#### 4.4 `_local_stub(prompt)` Function Flow

**Process Overview:**
```
Return Placeholder Message
```

**Step-by-Step Processing:**

1. **Placeholder Response**
   - Return: `"[Local LLM backend not configured]"`
   - Purpose: Placeholder for future local LLM implementation

**Global Instance:**
```python
llm = LLMClient()  # Singleton, used throughout backend
```

---

### 5. Frontend (`frontend/src/`)

**Files:**
- `App.jsx` — Main UI (upload, documents list)
- `components/Chat.jsx` — Chat component (model selector, queries, answers)
- `style.css` — Styles (scrollable areas, spinner, toasts, errors)
- `main.jsx` — React entry point
````

---

### 5. Frontend (`frontend/src/`)

**Purpose:** React + Vite single-page application for document upload, indexing, and RAG queries

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

**Detailed Frontend Function Processing:**

#### 5.1 Upload File Flow

**Process Overview:**
```
User Selects File → Validation → POST /upload with Metadata → 
Monitor Status → Show Progress → Display Success Toast
```

**Step-by-Step Processing:**

1. **File Input Handling**
   - User clicks file input
   - Browser file picker opens
   - User selects file (PDF, DOCX, or TXT)
   - File object passed to upload handler

2. **Form Data Preparation**
   - Create FormData object
   - Append file: `formData.append("file", file)`
   - Append OCR toggle: `formData.append("enable_ocr", enableOCR)`
   - Append OCR page limit: `formData.append("ocr_max_pages", ocrMaxPages)`
   - Purpose: Multi-part form submission

3. **Upload Request**
   - POST to `/upload` endpoint with FormData
   - No Content-Type header (browser sets correctly for multipart)
   - Purpose: Send file and metadata to backend

4. **Response Parsing**
   - Parse JSON response: `{doc_id, ocr_used, page_count, ocr_truncated}`
   - Extract doc_id for later queries
   - Purpose: Confirm successful upload

5. **Status Polling** (if async indexing enabled)
   - Poll `/index/status/{doc_id}` every 1-2 seconds
   - Check for status: "pending" → "indexing" → "done" or "failed"
   - Display progress to user
   - Purpose: Real-time feedback on background processing

6. **Success Toast**
   - Display toast notification showing:
     - "File uploaded successfully"
     - `ocr_used`: "Yes" or "No"
     - `page_count`: "5 pages"
     - `ocr_truncated`: "OCR limited to X pages"
   - Auto-dismiss after 3-5 seconds
   - Purpose: Confirmation and metadata display

7. **Document List Refresh**
   - Call `GET /documents` to fetch updated list
   - Update local state with new documents
   - Display in sidebar with new chunk counts
   - Purpose: Show immediate effect of upload

8. **Error Handling**
   - Catch HTTP errors (400, 413, 500)
   - Parse error message from response
   - Display error toast: "Upload failed: [reason]"
   - Purpose: User-friendly error feedback

#### 5.2 Document List Loading Flow

**Process Overview:**
```
Component Mount → Fetch /documents → Parse Response → 
Display List with Delete Buttons
```

**Step-by-Step Processing:**

1. **Initialization** (on component mount)
   - Call `GET /documents` endpoint
   - Purpose: Load initial document list

2. **Response Parsing**
   - Parse JSON: `{documents: [{doc_id, count, sample_metadata}, ...]}`
   - Extract doc_id, chunk count, and metadata
   - Purpose: Display summary information

3. **List Rendering**
   - For each document:
     - Display doc_id (shortened, with copy button)
     - Show chunk count: "12 chunks"
     - Display source filename from metadata
   - Purpose: Visual list of indexed documents

4. **Delete Button Interaction**
   - User clicks delete button for document
   - Call `DELETE /documents/{doc_id}`
   - Refresh document list
   - Display success toast: "Document deleted"
   - Purpose: Remove document from index

5. **Error Handling**
   - On fetch failure: show empty list or error message
   - On delete failure: show error toast
   - Purpose: Graceful handling of backend issues

#### 5.3 Chat Query Flow

**Process Overview:**
```
User Enters Query → Select Model → POST /ask → 
Receive Answer + Sources → Display with Formatting
```

**Step-by-Step Processing:**

1. **Query Input**
   - User types question in chat input field
   - User clicks "Send" or presses Enter
   - Validate: ensure query is non-empty
   - Purpose: Capture user question

2. **Model Selection**
   - User selects model from dropdown
   - Dropdown fetched from `GET /llm/models` on load
   - Default: first model or env default
   - Purpose: Allow model switching

3. **Request Construction**
   - Build query params: `?q={query}&model={selectedModel}&top_k=5`
   - Purpose: Send all parameters to backend

4. **Query Request**
   - GET `/ask?q=...&model=...&top_k=5`
   - Timeout: 60 seconds (longer for LLM responses)
   - Purpose: Send query and retrieve answer

5. **Response Parsing**
   - Parse JSON: `{answer, sources, retrieved_chunks}`
   - Extract:
     - `answer`: LLM's response text
     - `sources`: list of chunk IDs (e.g., `["doc123_5"]`)
     - `retrieved_chunks`: full chunks with metadata
   - Purpose: Retrieve answer and supporting information

6. **Display Answer**
   - Render answer text in chat UI
   - Format with markdown (if supported)
   - Scroll to show new message
   - Purpose: Show LLM response to user

7. **Source Display**
   - List source chunk IDs
   - For each source, show:
     - Chunk ID with link to full text
     - Full chunk text in expandable section
     - Source metadata (filename)
   - Purpose: Allow user to verify answer with sources

8. **Error Handling**
   - If response contains error (low-level connection error):
     - Show user-friendly message: "Unable to connect to AI model"
     - Provide collapsible raw error for debugging
     - Purpose: Better UX for backend failures

9. **Loading State**
   - Show spinner while waiting for response
   - Disable chat input during request
   - Display "Thinking..." placeholder
   - Purpose: Provide visual feedback

#### 5.4 Model Selector Flow

**Process Overview:**
```
Component Mount → Fetch /llm/models → Parse Models → 
Populate Dropdown
```

**Step-by-Step Processing:**

1. **Models Fetching** (on Chat component mount)
   - Call `GET /llm/models`
   - Purpose: Get available models from backend

2. **Response Parsing**
   - Parse JSON: `{models: ["llama2:latest", "mistral:latest", ...]}`
   - Extract model names
   - Purpose: Build dropdown options

3. **Dropdown Rendering**
   - For each model: create option element
   - Display model name (e.g., "Llama 2 Latest")
   - Purpose: User-friendly selection

4. **Default Selection**
   - Select first model as default
   - Or use backend default (OLLAMA_MODEL env)
   - Purpose: Initial model for queries

5. **Error Handling**
   - If model fetch fails: show disabled dropdown
   - Display message: "Unable to load models"
   - Purpose: Graceful degradation

**Environment Variables (Build Time):**
```
VITE_API_BASE_URL : Backend URL (e.g., http://localhost:8000)
               Docker sets to http://backend:8000
               Dev fallback: http://localhost:8000
```

---

#### 5.5 Toast Notification System

**Process Overview:**
```
Create Toast Object → Display for 3-5 seconds → Auto-dismiss
```

**Toast Types:**
- **Success:** Green background, checkmark icon
  - Example: "File uploaded successfully"
- **Error:** Red background, error icon
  - Example: "Upload failed: File too large"
- **Info:** Blue background, info icon
  - Example: "Syncing..."

**Implementation Details:**
- Toast queue: Multiple toasts can stack
- Auto-dismiss: Each toast disappears after timer
- Manual dismiss: User can click to remove
- Position: Bottom-right corner
- Animation: Slide-in from bottom

---

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

# Locally (requires pytest, fastapi, starlette)
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

## Post-cleanup: Update local environment

After the dependency cleanup performed on 2025-12-19, update your local environment with these commands to apply the changes and verify everything still works.

Python (backend):
```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1   # PowerShell on Windows
pip install --upgrade pip
pip install -r requirements.txt --upgrade
pytest -v
```

Node (frontend):
```bash
cd frontend
npm install
npm run build   # or `npm run dev` for development
```

Docker (optional):
```bash
docker compose build --no-cache backend
docker compose up -d backend
```


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
