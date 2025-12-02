"""
main.py - FastAPI Backend for NotebookLM RAG Demo
==================================================

This module provides the HTTP API for the NotebookLM RAG system:
- Document upload (PDF, DOCX, TXT) with optional OCR fallback
- Asynchronous document indexing and vector embedding
- Vector similarity search + RAG-based LLM querying
- Document management (list, delete)
- LLM model listing for frontend selector

Key Features:
- CORS configuration (env: ALLOWED_ORIGINS)
- Redis-backed rate limiting with in-memory fallback (env: REDIS_URL)
- Upload validation: file type whitelist, size limits, filename sanitization
- Background indexing: pre-validates chunks, tracks status, supports both
  FastAPI BackgroundTasks and thread-fallback for compatibility
- Lazy Indexer initialization: defers heavy ML imports until first use
  (helps with test performance and avoiding import-time dependencies)

Endpoints:
- POST /upload       : Upload and index a document
- GET /ask           : Query indexed documents + get LLM answer
- GET /documents     : List indexed documents
- DELETE /documents/{doc_id} : Remove a document
- GET /llm/models    : List available LLM models
- GET /index/status/{doc_id} : Check background indexing status
- GET /health        : Health check
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi import BackgroundTasks, Request
from fastapi.responses import JSONResponse
import redis
from urllib.parse import urlparse
import threading
import time
from indexer import Indexer
from extract import extract
from llm_client import llm
import uuid
import os
import sys
import traceback
import logging

logging.basicConfig(level=logging.DEBUG)

app = FastAPI()

# ============================================================================
# CORS Configuration
# ============================================================================
# Configure CORS more securely via environment variable; fallback to localhost
# origins for dev. In production, set ALLOWED_ORIGINS to a comma-separated list
# of trusted frontend origins to prevent cross-origin attacks.
# 
# Example: ALLOWED_ORIGINS="https://app.example.com,https://www.example.com"

allow_origins_env = os.environ.get("ALLOWED_ORIGINS")
if allow_origins_env:
    allow_origins = [o.strip() for o in allow_origins_env.split(",") if o.strip()]
else:
    allow_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173"]

app.add_middleware(CORSMiddleware, allow_origins=allow_origins, allow_methods=["*"], allow_headers=["*"])

# ============================================================================
# Rate Limiting Configuration
# ============================================================================
# Implements fixed-window rate limiting with per-IP per-endpoint tracking.
# Supports Redis backend (recommended for distributed deployments) with
# automatic in-memory fallback for single-process dev/test environments.
#
# Environment Variables:
#   RATE_LIMIT_WINDOW    : Time window in seconds (default 60)
#   UPLOAD_RATE_LIMIT    : Max uploads per window per IP (default 5)
#   ASK_RATE_LIMIT       : Max /ask queries per window per IP (default 20)
#   REDIS_URL            : Optional redis://... URL for distributed rate limiting
#                          If set, Redis is used; otherwise in-memory fallback
#
# Example: REDIS_URL="redis://user:pass@redis.example.com:6379/0"

RATE_LIMIT_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW", 60))
UPLOAD_RATE_LIMIT = int(os.environ.get("UPLOAD_RATE_LIMIT", 5))  # uploads per window
ASK_RATE_LIMIT = int(os.environ.get("ASK_RATE_LIMIT", 20))

# Initialize Redis client for distributed rate limiting
# Supports redis:// and rediss:// URLs with optional password auth
REDIS_URL = os.environ.get("REDIS_URL")
_redis_client = None
if REDIS_URL:
    try:
        # Parse URL to extract host, port, password, db
        parsed = urlparse(REDIS_URL)
        redis_kwargs = {}
        if parsed.password:
            redis_kwargs['password'] = parsed.password
        _redis_client = redis.Redis.from_url(REDIS_URL, **redis_kwargs)
        # Verify connection is working before proceeding
        _redis_client.ping()
        print(f"DEBUG: Connected to Redis for rate limiting: {REDIS_URL}", file=sys.stderr)
    except Exception as e:
        print(f"WARNING: Could not connect to Redis at {REDIS_URL}: {e}", file=sys.stderr)
        _redis_client = None

# In-memory fallback rate limiter for single-process deployments
# Thread-safe implementation using a lock and timestamp-based request log
_rl_lock = threading.Lock()
_requests_log: dict = {}  # Key: client IP, Value: list of (timestamp, endpoint_path) tuples

# ============================================================================
# Background Indexing Status Tracker
# ============================================================================
# Tracks the asynchronous status of document indexing operations.
# Status values: "pending" -> "indexing" -> "done" OR "failed: error_msg"
#
# This allows the frontend to poll /index/status/{doc_id} to monitor
# indexing progress without blocking the upload endpoint response.

_index_lock = threading.Lock()
_index_status: dict = {}  # Key: doc_id, Value: status string (pending|indexing|done|failed:msg)


def _run_index_background(doc_id: str, text: str, metadata: dict | None = None):
    """
    Run document indexing in background (called from BackgroundTasks or thread).
    
    Chunks the text, creates embeddings, and stores vectors in ChromaDB.
    Updates _index_status to track progress: pending -> indexing -> done|failed
    
    Args:
        doc_id: Unique document identifier
        text: Extracted text content from the uploaded file
        metadata: Optional metadata dict (e.g., {"source_filename": "doc.pdf"})
        
    Side Effects:
        - Updates _index_status[doc_id]
        - Adds chunks+embeddings to ChromaDB via self.get_indexer()
        - Prints debug/error logs to stderr
    """
    with _index_lock:
        _index_status[doc_id] = "indexing"
    try:
        get_indexer().index_document(doc_id, text, metadata=metadata)
        with _index_lock:
            _index_status[doc_id] = "done"
        print(f"DEBUG: Background indexing completed for {doc_id}", file=sys.stderr)
    except Exception as e:
        with _index_lock:
            _index_status[doc_id] = f"failed: {e}"
        print(f"ERROR: Background indexing failed for {doc_id}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


@app.middleware("http")
async def simple_rate_limiter(request: Request, call_next):
    """
    HTTP middleware: enforces rate limiting on a per-IP, per-endpoint basis.
    
    Preferred Backend: Redis (atomic, distributed-safe) via REDIS_URL env var.
    Fallback: In-memory (thread-safe but single-process only) using _requests_log dict.
    
    Implementation:
    - Redis mode: uses INCR key with expiry to track request counts in fixed windows
    - In-memory mode: stores (timestamp, path) tuples per IP, filters by window age
    
    Returns 429 (Too Many Requests) if limits are exceeded:
    - /upload: UPLOAD_RATE_LIMIT per RATE_LIMIT_WINDOW
    - /ask: ASK_RATE_LIMIT per RATE_LIMIT_WINDOW
    """
    try:
        client = request.client.host if request.client else "unknown"
    except Exception:
        client = "unknown"

    path = request.url.path
    now = int(time.time())

    # Try Redis-backed rate limiting (atomic, distributed-safe)
    if _redis_client:
        try:
            window = now // RATE_LIMIT_WINDOW
            key = f"rl:{client}:{path}:{window}"
            # INCR atomically increments the counter and set expiry to clean up old windows
            count = _redis_client.incr(key)
            _redis_client.expire(key, RATE_LIMIT_WINDOW + 1)

            if path == "/upload" and count > UPLOAD_RATE_LIMIT:
                return JSONResponse(status_code=429, content={"detail": "Too many upload requests, try later"})
            if path.startswith("/ask") and count > ASK_RATE_LIMIT:
                return JSONResponse(status_code=429, content={"detail": "Too many requests to ask endpoint, slow down"})
        except Exception as e:
            # If Redis fails at runtime, fall back to in-memory and log warning
            print(f"WARNING: Redis rate limiter error, falling back to in-memory: {e}", file=sys.stderr)

    # In-memory fallback (thread-safe but single-process only)
    with _rl_lock:
        lst = _requests_log.get(client) or []
        # Remove old entries outside the current window (cleanup)
        lst = [(ts, p) for (ts, p) in lst if now - ts <= RATE_LIMIT_WINDOW]
        # Count endpoint-specific requests in the current window
        upload_count = sum(1 for (ts, p) in lst if p == "/upload")
        ask_count = sum(1 for (ts, p) in lst if p == "/ask")

        # Check limits and return 429 if exceeded
        if path == "/upload" and upload_count >= UPLOAD_RATE_LIMIT:
            return JSONResponse(status_code=429, content={"detail": "Too many upload requests, try later"})
        if path.startswith("/ask") and ask_count >= ASK_RATE_LIMIT:
            return JSONResponse(status_code=429, content={"detail": "Too many requests to ask endpoint, slow down"})

        # Record this request and update the log
        lst.append((now, path))
        _requests_log[client] = lst

    response = await call_next(request)
    return response

# ============================================================================
# Lazy Indexer Initialization
# ============================================================================
# Defers heavy imports (SentenceTransformer, ChromaDB) until first actual use.
# This improves startup time and helps with test performance (tests can mock
# the Indexer without importing all dependencies).
#
# Environment Variable:
#   CHROMA_DB_DIR  : Path for ChromaDB persistence (default "./chroma_db")
#                    In Docker, typically set to "/data/chroma"

CHROMA_DB_DIR = os.environ.get("CHROMA_DB_DIR", "./chroma_db")
IDX = None  # Lazily initialized on first call to get_indexer()


def get_indexer() -> Indexer:
    """
    Get or initialize the Indexer singleton.
    
    On first call, instantiates Indexer which loads the SentenceTransformer
    embedding model and initializes ChromaDB. Subsequent calls return the
    cached instance.
    
    Returns:
        Indexer: The global indexer instance
        
    Raises:
        ImportError: If required dependencies (sentence-transformers, chromadb)
                     cannot be imported
    """
    global IDX
    if IDX is None:
        IDX = Indexer(db_dir=CHROMA_DB_DIR)
    return IDX

# ============================================================================
# Upload Configuration & Security
# ============================================================================
# Enforces security constraints on file uploads:
# - MAX_UPLOAD_SIZE: Max file size (default 10 MB)
# - ALLOWED_EXT: Whitelist of supported file extensions
#
# Filename Sanitization:
# - Removes directory traversal attempts (os.path.basename)
# - Prepends random UUID to avoid name collisions
# - Truncates to 240 chars to stay within most filesystems' limits

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", ".uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE", 10 * 1024 * 1024))  # 10 MB default
ALLOWED_EXT = {".pdf", ".docx", ".txt"}


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    enable_ocr: bool = Form(False),
    ocr_max_pages: int | None = Form(None),
    background_tasks: BackgroundTasks = None,
):
    """
    Upload a document and queue it for asynchronous indexing.
    
    This endpoint:
    1. Validates file type (must be .pdf, .docx, or .txt)
    2. Enforces size limits (MAX_UPLOAD_SIZE)
    3. Sanitizes filename (remove path traversal, add UUID prefix)
    4. Extracts text (with optional OCR fallback for PDFs)
    5. Pre-validates that chunks can be generated (fail early if doc is empty)
    6. Schedules background indexing and returns immediately
    
    Form Parameters:
        file (UploadFile): The document file to upload
        enable_ocr (bool): Enable OCR fallback if PDF text extraction fails
        ocr_max_pages (int): Max pages to process with OCR (if enabled)
        
    Returns:
        {
            "status": "ok",
            "doc_id": "<hex-id>",
            "ocr_used": bool,
            "page_count": int,
            "ocr_truncated": bool,
            "indexing": "pending"  // Background task scheduled
        }
        
    Raises:
        HTTPException 400: Invalid file type or size
        HTTPException 500: Unexpected error
        
    Notes:
        - Upload returns immediately; indexing happens in background
        - Poll /index/status/{doc_id} to monitor indexing progress
        - Temp files are cleaned up on error
    """
    # ========================================================================
    # Step 1: Validate and Sanitize Filename
    # ========================================================================
    orig_name = os.path.basename(file.filename or "")
    _, ext = os.path.splitext(orig_name)
    ext = ext.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    # Generate a unique safe filename (UUID + original name, truncated to 240 chars)
    filename = f"{uuid.uuid4().hex}_{orig_name}"[:240]
    path = os.path.join(UPLOAD_DIR, filename)
    print(f"DEBUG: Uploading file: {filename} to {path}", file=sys.stderr)

    # ========================================================================
    # Step 2: Read and Validate File Size
    # ========================================================================
    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"Uploaded file exceeds maximum allowed size of {MAX_UPLOAD_SIZE} bytes")

    # ========================================================================
    # Step 3: Save File and Extract Text
    # ========================================================================
    with open(path, "wb") as f:
        f.write(data)
    
    try:
        print(f"DEBUG: Extracting text from {path}", file=sys.stderr)
        # Log saved file size for diagnostics
        try:
            fsize = os.path.getsize(path)
            print(f"DEBUG: Saved file size: {fsize}", file=sys.stderr)
        except Exception:
            pass

        res = extract(path, ocr_enabled=enable_ocr, ocr_max_pages=ocr_max_pages)
        if res is None:
            raise ValueError("Unsupported file type or extraction failed")
        _, text, ocr_used, page_count, ocr_truncated = res
        
        # Log a short preview of the extracted text to help diagnose extractor failures
        preview = (text[:200] + '...') if len(text) > 200 else text
        print(f"DEBUG: Extracted text length: {len(text)}", file=sys.stderr)
        print(f"DEBUG: Extract preview: {repr(preview)}", file=sys.stderr)
        print(f"DEBUG: OCR requested={enable_ocr}, OCR used={ocr_used}, ocr_max_pages={ocr_max_pages}, page_count={page_count}, ocr_truncated={ocr_truncated}", file=sys.stderr)

        # ====================================================================
        # Step 4: Pre-validate Indexing (Fail Early)
        # ====================================================================
        # Before scheduling background task, ensure the text can be chunked.
        # This catches empty documents early and avoids queuing impossible tasks.
        doc_id = uuid.uuid4().hex
        print(f"DEBUG: Scheduling background indexing for doc_id={doc_id}", file=sys.stderr)

        try:
            chunks = get_indexer().chunk_document(text)
            if not chunks:
                raise ValueError("No text chunks generated for indexing (empty document or extraction failure)")
        except Exception as e:
            print(f"DEBUG: Index pre-validation failed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            if isinstance(e, ValueError):
                raise HTTPException(status_code=400, detail=f"Indexing error: {e}")
            else:
                raise HTTPException(status_code=500, detail=f"Index validation error: {e}")

        # ====================================================================
        # Step 5: Schedule Background Indexing
        # ====================================================================
        # Mark status as pending and schedule the indexing task.
        # If BackgroundTasks is available, use it; otherwise fallback to threading.
        with _index_lock:
            _index_status[doc_id] = "pending"

        if background_tasks is None:
            # Fallback: run indexing in a new thread if BackgroundTasks not provided
            t = threading.Thread(target=_run_index_background, args=(doc_id, text, {"source_filename": file.filename}), daemon=True)
            t.start()
        else:
            background_tasks.add_task(_run_index_background, doc_id, text, {"source_filename": file.filename})

        print(f"DEBUG: Upload queued for doc_id={doc_id}", file=sys.stderr)
        return {"status": "ok", "doc_id": doc_id, "ocr_used": bool(ocr_used), "page_count": page_count, "ocr_truncated": bool(ocr_truncated), "indexing": "pending"}
    
    except HTTPException:
        # Re-raise FastAPI HTTP errors (already have proper status codes)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        raise
    
    except Exception as e:
        # Cleanup temp file on unexpected errors
        print(f"DEBUG: Unexpected error in upload: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/ask")
def ask(q: str, top_k: int = 5, model: str | None = None):
    """
    Query indexed documents and ask the LLM using Retrieval-Augmented Generation.
    
    This endpoint implements the RAG pattern:
    1. Search the vector database for chunks most similar to the query
    2. Build a prompt with the retrieved context and user question
    3. Send the prompt to the LLM (Ollama or configured backend)
    4. Return the answer along with source chunks and metadata
    
    Query Parameters:
        q (str): The user's question
        top_k (int): Number of document chunks to retrieve (default 5)
        model (str): Optional LLM model name (passed to backend, e.g., Ollama)
                     If omitted, uses LLM_BACKEND default
        
    Returns:
        {
            "answer": str,           # LLM's response
            "sources": [str],        # IDs of retrieved chunks
            "snippets": [str],       # Text of retrieved chunks
            "metadatas": [dict]      # Metadata for each chunk
        }
        
    Raises:
        HTTPException 500: Vector DB query or LLM service error
        
    Notes:
        - The RAG prompt instructs the LLM to:
          * Use ONLY the provided context (not external knowledge)
          * Cite sources for factual claims
          * Say "I don't know" if context is insufficient
        - Retrieved chunks are limited to top_k by similarity score
        - If the LLM is unavailable, the error will be propagated
    """
    # ========================================================================
    # Step 1: Retrieve Similar Chunks from Vector DB
    # ========================================================================
    try:
        res = get_indexer().query(q, top_k)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Index query error: {e}")

    # Extract the retrieved chunks, IDs, and metadata
    # (normalize for different ChromaDB response shapes)
    docs = res.get("documents", [[]])[0]
    ids = res.get("ids", [[]])[0]
    metadatas = res.get("metadatas", [[]])[0]

    # ========================================================================
    # Step 2: Build RAG Context String
    # ========================================================================
    # Format chunks with their IDs for source tracking
    context = "\n\n---\n\n".join([f"[{ids[i]}] {docs[i]}" for i in range(len(docs))])

    # ========================================================================
    # Step 3: Build the Prompt
    # ========================================================================
    # The prompt is carefully designed to:
    # - Emphasize use of provided context only (avoid hallucination)
    # - Request source citations
    # - Provide fallback for unanswerable questions
    prompt = (
        "You are a helpful assistant. Answer the user's QUESTION using ONLY the provided CONTEXT. "
        "Do NOT use external knowledge or make assumptions beyond the CONTEXT.\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION: {q}\n\n"
        "INSTRUCTIONS:\n"
        "- If the answer is present in the CONTEXT, answer concisely (1-4 sentences).\n"
        "- For any factual claims, include short source references (the chunk ids) in square brackets, e.g. [docid_0].\n"
        "- When quoting or paraphrasing from CONTEXT, keep quotes short and cite the source id.\n"
        "- If the CONTEXT does not contain enough information to answer, reply exactly: 'I don't know based on the provided context.'\n"
        "- If sources conflict, say so and list the source ids.\n\n"
        "Provide the answer, then a short 'Sources:' line with the ids."
    )

    # ========================================================================
    # Step 4: Query the LLM
    # ========================================================================
    try:
        ans = llm.chat(prompt, model=model)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM service error: {e}")

    # ========================================================================
    # Step 5: Return Response
    # ========================================================================
    return {"answer": ans, "sources": ids, "snippets": docs, "metadatas": metadatas}


@app.get("/health")
def health():
    """
    Health check endpoint.
    
    Returns:
        {"ok": True} if service is operational
        
    Notes:
        - This is a simple liveness check; does not verify database or LLM connectivity
        - For deep health checks, consider adding database/LLM status
    """
    return {"ok": True}


@app.get("/documents")
def list_documents():
    """
    List all indexed documents with metadata.
    
    Returns:
        {
            "documents": [
                {
                    "doc_id": str,              # Unique document identifier
                    "count": int,               # Number of chunks indexed
                    "sample_metadata": dict     # Sample metadata from first chunk
                },
                ...
            ]
        }
        
    Raises:
        HTTPException 500: Database query error
        
    Notes:
        - Each document may have multiple chunks (see count)
        - sample_metadata is from the first chunk; others may have different metadata
    """
    try:
        docs = get_indexer().list_documents()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {e}")
    return {"documents": docs}


@app.get("/llm/models")
def list_llm_models():
    """
    List available LLM models from the configured backend.
    
    Returns:
        {
            "models": [str]  # List of model names (e.g., ["llama3.1", "mistral", ...])
        }
        
    Notes:
        - Returns empty list if LLM backend is not available or doesn't support model listing
        - For Ollama, queries the /models endpoint
        - This enables the frontend model selector
    """
    try:
        models = llm.list_models()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list LLM models: {e}")
    return {"models": models}


@app.get("/index/status/{doc_id}")
def index_status(doc_id: str):
    """
    Check the background indexing status of a document.
    
    Path Parameters:
        doc_id (str): The document ID returned from /upload
        
    Returns:
        {
            "doc_id": str,                  # Echo of the doc_id
            "status": str                   # One of: unknown, pending, indexing, done, failed:error_msg
        }
        
    Notes:
        - Frontend can poll this endpoint to show indexing progress
        - Status values:
          * "unknown" : doc_id not found (may not have been uploaded)
          * "pending" : document queued but indexing not started
          * "indexing" : chunks are being embedded and stored
          * "done" : indexing completed successfully
          * "failed: ..." : indexing failed with error message
    """
    with _index_lock:
        status = _index_status.get(doc_id, "unknown")
    return {"doc_id": doc_id, "status": status}


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    """
    Delete a document and all its chunks from the index.
    
    Path Parameters:
        doc_id (str): The document ID to delete
        
    Returns:
        {"deleted": doc_id}  # Confirms deletion
        
    Raises:
        HTTPException 404: Document not found
        HTTPException 500: Database deletion error
        
    Notes:
        - Removes all chunks (doc_id_0, doc_id_1, ...) from ChromaDB
        - This is irreversible; consider warning users or implementing soft delete
        - Does not delete the file from UPLOAD_DIR (may want to add cleanup)
    """
    try:
        ok = get_indexer().delete_document(doc_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {e}")
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": doc_id}