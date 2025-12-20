# NotebookLM Data Flow Diagrams

## Complete End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER INTERACTIONS                           │
└────────┬──────────────────────────┬──────────────────────┬──────┘
         │                          │                      │
         ▼                          ▼                      ▼
    UPLOAD FILE              CHAT QUERY            DELETE DOCUMENT
         │                          │                      │
         │◄─────────────────────────┘                      │
         │
    ┌────▼─────────────────────────────────────────────────┘
    │
    │  ┌──────────────────── FRONTEND (React + Vite) ────────────────┐
    │  │                                                              │
    │  │  1. Form validation           1. Query validation           │
    │  │  2. FormData creation        2. Model selection            │
    │  │  3. POST /upload             3. GET /ask                   │
    │  │  4. Status polling           4. Response parsing           │
    │  │  5. Toast notification       5. Answer + sources display   │
    │  │  6. Document list refresh    6. Error handling             │
    │  │                                                              │
    └──┼──────────────────────────────────────────────────────────────┘
       │
       │ HTTP
       │ (FormData, JSON)
       │
    ┌──▼──────────────────── BACKEND (FastAPI) ────────────────────┐
    │                                                               │
    │  ┌─────────────────────────────────────────────────────────┐ │
    │  │ MIDDLEWARE: Rate Limiter (Redis or In-Memory)          │ │
    │  │ - Checks IP-based request count in time window         │ │
    │  │ - Returns 429 if limit exceeded                         │ │
    │  └─────────────────────────────────────────────────────────┘ │
    │                          │
    │  ┌──────────────────────▼──────────────────────────────────┐ │
    │  │ ENDPOINT HANDLER                                        │ │
    │  │                                                          │ │
    │  │ upload() ─────────────┬────────────────────────────────┐ │
    │  │                       │                                │ │
    │  │                ┌──────▼──────────────────────────────┐ │ │
    │  │                │ 1. Validate filename & type         │ │ │
    │  │                │ 2. Check file size                  │ │ │
    │  │                │ 3. Sanitize filename                │ │ │
    │  │                │ 4. Save to disk                     │ │ │
    │  │                │ 5. Extract text (extract module)    │ │ │
    │  │                │    - PDF: PyMuPDF or OCR            │ │ │
    │  │                │    - DOCX: paragraph extraction     │ │ │
    │  │                │    - TXT: plain read                │ │ │
    │  │                │ 6. Pre-validate chunks              │ │ │
    │  │                │ 7. Queue background indexing        │ │ │
    │  │                │ 8. Return doc_id response           │ │ │
    │  │                └──────────────────────────────────────┘ │ │
    │  │                                                          │ │
    │  │  ask() ───────────────┬──────────────────────────────┐   │ │
    │  │                       │                              │   │ │
    │  │                ┌──────▼──────────────────────────────┐   │ │
    │  │                │ 1. Get query & model params         │   │ │
    │  │                │ 2. Embed query                      │   │ │
    │  │                │ 3. Search ChromaDB (top-k)          │   │ │
    │  │                │ 4. Build RAG prompt                 │   │ │
    │  │                │ 5. Call LLM (with retries)          │   │ │
    │  │                │ 6. Parse response                   │   │ │
    │  │                │ 7. Format answer + sources          │   │ │
    │  │                │ 8. Return response                  │   │ │
    │  │                └──────────────────────────────────────┘   │ │
    │  │                                                          │ │
    │  │  delete() ────────────┬──────────────────────────────┐   │ │
    │  │                       │                              │   │ │
    │  │                ┌──────▼──────────────────────────────┐   │ │
    │  │                │ 1. Find chunks {doc_id}_*           │   │ │
    │  │                │ 2. Delete from ChromaDB             │   │ │
    │  │                │ 3. Return success                   │   │ │
    │  │                └──────────────────────────────────────┘   │ │
    │  │                                                          │ │
    │  └──────────────────────────────────────────────────────────┘ │
    │                          │
    │  ┌──────────────────────▼──────────────────────────────────┐ │
    │  │ BACKGROUND TASK (if uploading)                         │ │
    │  │                                                          │ │
    │  │  _run_index_background(doc_id, text, metadata)         │ │
    │  │  1. Set status = "indexing"                            │ │
    │  │  2. Chunk text (paragraph-first strategy)              │ │
    │  │  3. Generate embeddings (batch 64)                     │ │
    │  │  4. Validate non-empty                                 │ │
    │  │  5. Store in ChromaDB with metadata                    │ │
    │  │  6. Set status = "done" or "failed"                    │ │
    │  │                                                          │ │
    │  └──────────────────────────────────────────────────────────┘ │
    │                                                               │
    │  ┌─────────────────────────────────────────────────────────┐ │
    │  │ CORE MODULES                                            │ │
    │  │                                                          │ │
    │  │  extract.py: Extract text from PDF/DOCX/TXT            │ │
    │  │  ├─ extract_pdf()   : PyMuPDF + OCR fallback           │ │
    │  │  ├─ extract_docx()  : python-docx paragraphs           │ │
    │  │  ├─ extract_txt()   : UTF-8 file read                  │ │
    │  │  └─ extract()       : dispatcher                        │ │
    │  │                                                          │ │
    │  │  indexer.py: Chunk, embed, store                       │ │
    │  │  ├─ chunk_document()  : paragraph-first chunking       │ │
    │  │  ├─ index_document()  : embed + store in ChromaDB      │ │
    │  │  ├─ query()           : semantic search                │ │
    │  │  ├─ list_documents()  : aggregate by doc_id            │ │
    │  │  └─ delete_document() : bulk delete chunks             │ │
    │  │                                                          │ │
    │  │  llm_client.py: LLM interface                          │ │
    │  │  ├─ chat()          : route to backend                 │ │
    │  │  ├─ _ollama_chat()  : query Ollama with retries       │ │
    │  │  ├─ list_models()   : fetch available models          │ │
    │  │  └─ _local_stub()   : placeholder for local LLM       │ │
    │  │                                                          │ │
    │  └─────────────────────────────────────────────────────────┘ │
    │                          │
    │  ┌──────────────────────▼──────────────────────────────────┐ │
    │  │ STORAGE & SERVICES                                      │ │
    │  │                                                          │ │
    │  │  ChromaDB (SQLite)                                      │ │
    │  │  ├─ collection: "notebook_collection"                  │ │
    │  │  ├─ ids: {doc_id}_{chunk_index}                        │ │
    │  │  ├─ documents: chunk text                              │ │
    │  │  ├─ embeddings: 384-D vectors                          │ │
    │  │  └─ metadata: {source_filename, ...}                   │ │
    │  │                                                          │ │
    │  │  File System (/tmp/uploads or UPLOAD_DIR)              │ │
    │  │  └─ uploaded files stored temporarily                  │ │
    │  │                                                          │ │
    │  │  Redis (optional, for distributed rate limiting)       │ │
    │  │  └─ keys: rl:{ip}:{endpoint}:{window}                  │ │
    │  │                                                          │ │
    │  │  Ollama (external LLM server)                           │ │
    │  │  └─ /chat endpoint for inference                       │ │
    │  │                                                          │ │
    │  └─────────────────────────────────────────────────────────┘ │
    │                                                               │
    └───────────────────────────────────────────────────────────────┘
         │
         │ HTTP (JSON)
         │
         ▼
    ┌─────────────────────────────────────────────────────────────┐
    │            FRONTEND DISPLAYS RESULTS                        │
    │ - Upload: shows doc_id, ocr_used, page_count, toast        │
    │ - Query: shows answer, sources, retrieved chunks            │
    │ - Documents: lists all indexed documents with delete option │
    │ - Errors: friendly messages + collapsible raw error         │
    └─────────────────────────────────────────────────────────────┘
```

---

## Upload Flow in Detail

```
USER SELECTS FILE
       │
       ▼
   VALIDATION
   ├─ Check extension in whitelist (pdf, docx, txt)
   ├─ Check file size ≤ MAX_UPLOAD_SIZE (10 MB)
   └─ Sanitize filename (UUID + basename)
       │
       ├─ FAIL ──────────────────┐
       │                          │
       ▼                          │
   SAVE FILE TO DISK              │
       │                          │
       ▼                          │
   EXTRACT TEXT                   │
   ├─ PDF: try PyMuPDF            │
   │   ├─ success: proceed        │
   │   └─ empty & OCR enabled     │
   │       ├─ Convert to images   │
   │       ├─ Run Tesseract       │
   │       └─ Return with flags   │
   ├─ DOCX: extract paragraphs    │
   └─ TXT: read file              │
       │                          │
       ▼                          │
   PRE-VALIDATE CHUNKS            │
   ├─ Attempt to chunk text       │
   └─ Ensure non-empty            │
       │                          │
       ├─ SUCCESS ◄───────────────┘
       │
       ▼
   METADATA PREPARATION
   └─ Create {source_filename: ...}
       │
       ▼
   QUEUE BACKGROUND TASK
   ├─ Generate doc_id (UUID hex)
   ├─ Set status = "pending"
   └─ Schedule _run_index_background()
       │
       ▼
   RETURN RESPONSE
   ├─ status: "ok"
   ├─ doc_id
   ├─ ocr_used
   ├─ page_count
   └─ ocr_truncated
       │
       ▼
   FRONTEND UPDATES
   ├─ Poll /index/status/{doc_id}
   ├─ Show "pending" ─► "indexing" ─► "done"
   ├─ Refresh document list
   └─ Show success toast with metadata

BACKGROUND (Parallel):
   _run_index_background()
   ├─ Set status = "indexing"
   ├─ chunk_document(text)
   │  ├─ Split by paragraphs
   │  ├─ Keep short as-is
   │  └─ Split long with word chunks
   ├─ Generate embeddings (batch 64)
   ├─ Validate embeddings
   ├─ Create chunk IDs: {doc_id}_0, {doc_id}_1, ...
   ├─ Store in ChromaDB
   └─ Set status = "done" or "failed"
```

---

## Query Flow in Detail

```
USER ASKS QUESTION
       │
       ▼
   INPUT VALIDATION
   ├─ Ensure query non-empty
   ├─ Extract top_k (default 5)
   └─ Extract model name
       │
       ├─ FAIL ──────────────────┐
       │                          │
       ▼                          │
   EMBED QUERY                    │
   └─ SentenceTransformer         │
       └─ "What is..." ─► 384-D   │
       │                          │
       ▼                          │
   VECTOR SIMILARITY SEARCH       │
   └─ ChromaDB query()            │
       ├─ Cosine distance calc    │
       └─ Return top-k chunks     │
       │                          │
       ▼                          │
   BUILD RAG PROMPT               │
   ├─ Instructions to LLM         │
   ├─ Context (retrieved chunks)  │
   ├─ Question                    │
   └─ "Answer only from context"  │
       │                          │
       ▼                          │
   CALL LLM (with retries)        │
   ├─ POST to Ollama /chat        │
   ├─ Timeout: 30s                │
   ├─ Retry logic:                │
   │  ├─ Attempt 1: immediate     │
   │  ├─ Attempt 2: +1s backoff   │
   │  ├─ Attempt 3: +2s backoff   │
   │  └─ Attempt 4: +4s backoff   │
   └─ On success: extract content │
       │                          │
       ├─ FAIL ──────────────────┘
       │
       ▼
   PARSE RESPONSE
   ├─ Try multiple formats
   ├─ {message: {content: ...}}
   ├─ {choices: [{message: ...}]}
   ├─ {response: "..."}
   └─ Return text or error string
       │
       ▼
   FORMAT ANSWER
   ├─ answer: LLM response
   ├─ sources: [chunk IDs]
   ├─ retrieved_chunks: [{id, text, metadata}, ...]
   └─ top_k: number of chunks
       │
       ▼
   RETURN TO FRONTEND
       │
       ▼
   FRONTEND DISPLAYS
   ├─ Answer text
   ├─ Source citations with links
   ├─ Retrieved chunks expandable
   └─ Error handling (if LLM failed)
```

---

## Document Deletion Flow

```
USER CLICKS DELETE
       │
       ▼
   CONFIRM DELETION
       │
       ├─ CANCEL ─────────────┐
       │                      │
       ▼                      │
   DELETE /documents/{doc_id} │
       │                      │
       ▼                      │
   FIND CHUNKS                │
   └─ Query ChromaDB for      │
      {doc_id}_0, _1, _2, ... │
       │                      │
       ▼                      │
   DELETE FROM CHROMADB       │
   ├─ Remove text             │
   ├─ Remove embeddings       │
   ├─ Remove metadata         │
   └─ Confirm deletion        │
       │                      │
       ▼                      │
   REFRESH DOCUMENTS LIST     │
   └─ GET /documents          │
       │                      │
       ▼                      │
   SHOW SUCCESS TOAST         │
       │◄──────────────────────┘
       │
       ▼
   UI UPDATED
   └─ Document removed from list
```

---

## Rate Limiting Flow

```
HTTP REQUEST ARRIVES
       │
       ▼
   EXTRACT CLIENT IP
   └─ request.client.host
       │
       ▼
   EXTRACT ENDPOINT PATH
   ├─ /upload
   ├─ /ask
   └─ other
       │
       ▼
   CALCULATE TIME WINDOW
   ├─ current_time // RATE_LIMIT_WINDOW
   └─ Example: 60-second windows
       │
       ▼
   CHECK REDIS (if available)
   ├─ Key: rl:{ip}:{endpoint}:{window}
   ├─ INCR counter
   ├─ SET expiry
   └─ Check limit
       │
       ├─ SUCCESS ◄──────────────┐
       │                         │
       ├─ EXCEEDED ──────────────┤
       │    │                    │
       │    ▼                    │
       │  Return 429            │
       │                         │
       ├─ REDIS UNAVAILABLE ────┤
       │    │                    │
       │    ▼                    │
       │  Use In-Memory Fallback │
       │                         │
       ├─ Check in-memory dict  │
       ├─ {ip: [(ts, path), ...]}
       ├─ Filter old entries    │
       ├─ Count endpoint reqs   │
       └─ Check limit
            │
            ├─ WITHIN LIMIT ────┘
            │
            ├─ EXCEEDED
            │  │
            │  ▼
            │ Return 429
            │
            └─ WITHIN LIMIT
                │
                ▼
            ALLOW REQUEST
                │
                ▼
            CALL NEXT HANDLER
                │
                ▼
            RETURN RESPONSE
```

---

## Embedding & Storage Pipeline

```
EXTRACTED TEXT
       │
       ▼
   CHUNKING
   ├─ Split by \n\n (paragraphs)
   ├─ For each paragraph:
   │  ├─ If short (≤512 chars): keep as-is
   │  └─ If long: split into word chunks (overlap)
   └─ Fallback: entire text if no chunks
       │
       ▼
   EMBEDDING GENERATION
   ├─ Load SentenceTransformer
   │  └─ all-MiniLM-L6-v2
   ├─ Batch encode (batch_size=64)
   │  └─ Each chunk → 384-D vector
   └─ Validate non-empty
       │
       ▼
   ID ASSIGNMENT
   ├─ Chunks: {doc_id}_0, {doc_id}_1, ...
   └─ Purpose: Enable later doc_id extraction
       │
       ▼
   CHROMADB STORAGE
   ├─ Collection: "notebook_collection"
   ├─ Store:
   │  ├─ ids: [{doc_id}_i, ...]
   │  ├─ documents: [chunk_text, ...]
   │  ├─ embeddings: [[384-D vector], ...]
   │  └─ metadatas: [{source_filename: ...}, ...]
   └─ Persist to SQLite
       │
       ▼
   READY FOR SEARCH
   └─ Can query by similarity
       │
       ▼
   LATER QUERIES
   ├─ Embed query
   ├─ Calculate cosine distance
   ├─ Return top-k similar chunks
   └─ Use for RAG context
```

---

## Error Handling Flows

### Upload Error
```
UPLOAD FAILS
    │
    ├─ Bad file type → 400 error
    ├─ File too large → 413 error
    ├─ Extraction failure → 400 error
    ├─ No chunks → 400 error
    └─ Server error → 500 error
         │
         ▼
    FRONTEND DISPLAYS
    ├─ Toast: "Upload failed: [reason]"
    └─ User can retry
```

### LLM Timeout
```
LLM REQUEST
    │
    ├─ Attempt 1: timeout ──┐
    │                        ├─ Sleep 1s
    ├─ Attempt 2: timeout ──┤
    │                        ├─ Sleep 2s
    ├─ Attempt 3: timeout ──┤
    │                        ├─ Sleep 4s
    ├─ Attempt 4: timeout ──┤
    │                        └─ Give up
    │
    ▼
    Return "[LLM timeout after 3 attempts]"
    │
    ▼
    FRONTEND SHOWS
    ├─ User-friendly: "Unable to connect to AI model"
    └─ Collapsible raw error for debugging
```

### Rate Limit Exceeded
```
TOO MANY REQUESTS (same IP, same endpoint)
    │
    ▼
    MIDDLEWARE DETECTS
    └─ Request count > limit in window
    │
    ▼
    Return 429 (Too Many Requests)
    │
    ▼
    FRONTEND SHOWS
    └─ "Too many requests, try later"
```

---

