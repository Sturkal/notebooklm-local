# Documentation Updates Summary

**Date:** December 20, 2025

## Overview
Comprehensive update to `DOCUMENTATION.md` with detailed step-by-step function processing descriptions for all major components.

---

## Updates Made

### 1. Backend API (`backend/api/main.py`)

Added detailed processing flows for:

#### 1.1 `POST /upload` Function
- 7-step detailed process from file submission to response
- Covers: filename validation, size checking, extraction, pre-validation, metadata prep, background scheduling, response formatting
- Includes error handling and purpose explanations

#### 1.2 `_run_index_background()` Function
- 5-step background indexing process
- Covers: status updates, chunking, embedding, storage, error handling
- Thread-safe implementation details

#### 1.3 `GET /ask` Function  
- 8-step RAG query pipeline
- Covers: validation, embedding, similarity search, context building, LLM prompt construction, querying, parsing, response formatting
- Example prompt templates included

#### 1.4 `simple_rate_limiter()` Middleware
- 6-step rate limiting process
- Redis-backed and in-memory implementations
- Fixed-window strategy explanation

#### 1.5 `GET /documents` Function
- 4-step document listing
- Chunk ID parsing and statistics aggregation

#### 1.6 `DELETE /documents/{doc_id}` Function
- Chunk pattern matching and bulk deletion

#### 1.7 `GET /llm/models` Function
- Model listing and response formatting

#### 1.8 `GET /index/status/{doc_id}` Function
- Status lookup and response

---

### 2. Document Indexer (`backend/indexer.py`)

Added detailed processing flows for:

#### 2.1 `__init__()` Initialization
- 6-step setup process
- Database directory management
- Lazy import strategy
- Model loading and ChromaDB initialization

#### 2.2 `chunk_document()` Function
- 6-step chunking algorithm
- Paragraph-first strategy with word-level fallback
- Overlap handling and heuristic calculations

#### 2.3 `index_document()` Function
- 8-step complete indexing pipeline
- Chunking, embedding generation, validation
- ChromaDB storage and persistence

#### 2.4 `query()` Function
- 4-step vector similarity search
- Multiple ChromaDB response format handling

#### 2.5 `list_documents()` Function
- Document aggregation and statistics

#### 2.6 `delete_document()` Function
- Chunk identification and bulk deletion

---

### 3. Document Extraction (`backend/extract.py`)

Added detailed processing flows for:

#### 3.1 `extract_pdf()` Function
- 8-step PDF processing with OCR fallback
- PyMuPDF fast extraction strategy
- Tesseract OCR with page limiting
- Error handling and graceful fallback
- Time complexity analysis

#### 3.2 `extract_docx()` Function
- Paragraph extraction from Word documents
- Time complexity analysis

#### 3.3 `extract_txt()` Function
- Plain text file reading
- Time complexity analysis

#### 3.4 `extract()` Dispatcher Function
- File type detection and routing
- Error handling explanation

---

### 4. LLM Client (`backend/llm_client.py`)

Added detailed processing flows for:

#### 4.1 `chat()` Function
- Backend routing logic
- Return value specification

#### 4.2 `_ollama_chat()` Function
- 5-step main process with retry loop details
- Model selection
- Endpoint URL construction
- Retry logic with exponential backoff (1s, 2s, 4s pattern)
- Response parsing with tolerant multi-format handling
- Timeout handling with detailed fallback strategy
- Example flows: successful response, timeout with retry, all retries failed

#### 4.3 `list_models()` Function
- Backend checking
- Models endpoint query
- Tolerant response parsing for multiple formats
- Error handling and graceful fallback

#### 4.4 `_local_stub()` Function
- Placeholder implementation

---

### 5. Frontend (`frontend/src/`)

Added comprehensive detailed function processing flows for:

#### 5.1 Upload File Flow
- 8-step process from file selection through success confirmation
- Form data preparation
- Status polling for async indexing
- Success toast display
- Document list refresh
- Error handling

#### 5.2 Document List Loading Flow
- Initialization and data fetching
- Response parsing
- List rendering with metadata
- Delete button interaction
- Error handling

#### 5.3 Chat Query Flow
- 9-step RAG query process
- Query input handling
- Model selection
- Request construction
- Response parsing
- Answer display
- Source display with expandable chunks
- Error handling with user-friendly messages
- Loading state feedback

#### 5.4 Model Selector Flow
- Models endpoint fetching
- Response parsing
- Dropdown rendering
- Default selection
- Error handling

#### 5.5 Toast Notification System
- Toast types (success, error, info)
- Implementation details
- Animation and timing

---

## Document Statistics

- **Total Lines:** 1,681 (expanded from original)
- **Major Sections:** 5 (API, Indexer, Extraction, LLMClient, Frontend)
- **Sub-sections:** 23 detailed function flows
- **Code Examples:** 50+
- **Flow Diagrams:** 15+ process overviews

---

## Key Additions

1. **Process Overview Diagrams** - ASCII flow diagrams for each major function
2. **Step-by-Step Breakdowns** - 4-10 steps per function with clear purposes
3. **Code Examples** - JSON responses, Python snippets, example outputs
4. **Error Handling Explanations** - How errors are caught and handled
5. **Time Complexity Analysis** - Performance characteristics where relevant
6. **Configuration Details** - Environment variables and setup for each component
7. **Example Flows** - Real-world scenarios (e.g., successful response, timeout with retry)
8. **Return Value Specifications** - Exact data structures returned by functions

---

## Usage

Reference this updated documentation for:
- **Understanding function behavior** - Each function has a detailed flow
- **Debugging issues** - See exactly what should happen at each step
- **Extending functionality** - Know the current implementation details
- **Onboarding developers** - Complete process documentation
- **API integration** - Full endpoint specifications and examples

---

## Next Steps

Consider:
1. Review API endpoint examples for accuracy
2. Add similar detail to other helper functions
3. Create visual architecture diagrams
4. Add deployment topology documentation
5. Document database schema and ChromaDB structure
