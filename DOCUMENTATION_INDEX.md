# NotebookLM Documentation Index

**Updated:** December 20, 2025

## 📚 Complete Documentation Files

### Core Documentation

1. **[DOCUMENTATION.md](DOCUMENTATION.md)** ⭐ PRIMARY REFERENCE
   - **Size:** 1,681 lines
   - **Content:** Complete technical documentation with detailed function processing
   - **Sections:**
     - Project Overview & Architecture
     - Detailed API Functions (1.1-1.8)
     - Detailed Indexer Functions (2.1-2.6)
     - Detailed Extraction Functions (3.1-3.4)
     - Detailed LLM Client Functions (4.1-4.4)
     - Detailed Frontend Functions (5.1-5.5)
     - Testing & Deployment
   - **Use for:** Understanding implementation details, debugging, extending features

2. **[README.md](README.md)**
   - User-facing guide
   - Setup instructions (Docker & local)
   - Feature descriptions
   - Quick start examples
   - Use for:** Getting started, basic usage

### Reference Guides

3. **[FUNCTION_PROCESSING_QUICK_REFERENCE.md](FUNCTION_PROCESSING_QUICK_REFERENCE.md)** ⚡ QUICK LOOKUP
   - **Purpose:** Quick reference for all function flows
   - **Format:** Compact bullet-point reference
   - **Includes:**
     - Function flows with step counts
     - Return values & error codes
     - Configuration reference
     - Performance characteristics
     - Response format examples
   - **Use for:** Quick lookup, understanding flow without deep dive

4. **[DATA_FLOW_DIAGRAMS.md](DATA_FLOW_DIAGRAMS.md)** 📊 VISUAL REFERENCE
   - **Purpose:** ASCII flow diagrams and visual representations
   - **Includes:**
     - Complete end-to-end flow (ASCII art)
     - Upload flow in detail
     - Query flow in detail
     - Deletion flow
     - Rate limiting flow
     - Error handling flows
   - **Use for:** Visual understanding, teaching, presentations

5. **[UPDATES_SUMMARY.md](UPDATES_SUMMARY.md)** 📝 CHANGE LOG
   - **Purpose:** Summary of recent documentation updates
   - **Includes:**
     - What was added in this update
     - Document statistics
     - Section breakdown
     - Next steps
   - **Use for:** Understanding what changed, seeing the scope of updates

### Additional Resources

6. **[DEPENDENCY_UPGRADE_PLAN.md](DEPENDENCY_UPGRADE_PLAN.md)**
   - Proposed dependency updates
   - Upgrade strategy
   - Compatibility notes

---

## 🎯 How to Use This Documentation

### For Users
1. Start with [README.md](README.md) for setup
2. Follow feature descriptions for basic usage
3. Check [FUNCTION_PROCESSING_QUICK_REFERENCE.md](FUNCTION_PROCESSING_QUICK_REFERENCE.md) for API endpoints

### For Developers
1. Read [DOCUMENTATION.md](DOCUMENTATION.md) for deep understanding
2. Use [DATA_FLOW_DIAGRAMS.md](DATA_FLOW_DIAGRAMS.md) for visual reference
3. Reference [FUNCTION_PROCESSING_QUICK_REFERENCE.md](FUNCTION_PROCESSING_QUICK_REFERENCE.md) while coding
4. Check specific sections for debugging

### For DevOps/Deployment
1. See [README.md](README.md) → "Run with Docker"
2. Check [DOCUMENTATION.md](DOCUMENTATION.md) → "Deployment" section
3. Reference environment variables in "Configuration"

### For Debugging
1. [DATA_FLOW_DIAGRAMS.md](DATA_FLOW_DIAGRAMS.md) → "Error Handling Flows"
2. [FUNCTION_PROCESSING_QUICK_REFERENCE.md](FUNCTION_PROCESSING_QUICK_REFERENCE.md) → "Error Handling Patterns"
3. [DOCUMENTATION.md](DOCUMENTATION.md) → specific function section

---

## 📋 Complete Function Reference

### API Functions
- [1.1 POST /upload](DOCUMENTATION.md#11-post-upload-function-flow)
- [1.2 Background Indexing](DOCUMENTATION.md#12-_run_index_backgroundodc_id-text-metadatanone-function-flow)
- [1.3 GET /ask](DOCUMENTATION.md#13-get-askqtopc_kamamodel-function-flow)
- [1.4 Rate Limiter](DOCUMENTATION.md#14-simple_rate_limitermiddleware-function-flow)
- [1.5 GET /documents](DOCUMENTATION.md#15-get-documents-function-flow)
- [1.6 DELETE /documents/{doc_id}](DOCUMENTATION.md#16-delete-documentsdoc_id-function-flow)
- [1.7 GET /llm/models](DOCUMENTATION.md#17-get-llm-models-function-flow)
- [1.8 GET /index/status/{doc_id}](DOCUMENTATION.md#18-get-index-statusdoc_id-function-flow)

### Indexer Functions
- [2.1 __init__](DOCUMENTATION.md#21-init-function-flow)
- [2.2 chunk_document](DOCUMENTATION.md#22-chunk_documenttext-chunk_size512-chunk_overlap50-function-flow)
- [2.3 index_document](DOCUMENTATION.md#23-index_documentdoc_id-text-metadatanone-function-flow)
- [2.4 query](DOCUMENTATION.md#24-queryquery_text-top_k5-function-flow)
- [2.5 list_documents](DOCUMENTATION.md#25-list_documents-function-flow)
- [2.6 delete_document](DOCUMENTATION.md#26-delete_documentdoc_id-function-flow)

### Extraction Functions
- [3.1 extract_pdf](DOCUMENTATION.md#31-extract_pdf-function-flow)
- [3.2 extract_docx](DOCUMENTATION.md#32-extract_docx-function-flow)
- [3.3 extract_txt](DOCUMENTATION.md#33-extract_txt-function-flow)
- [3.4 extract dispatcher](DOCUMENTATION.md#34-extract-function-flow)

### LLM Client Functions
- [4.1 chat](DOCUMENTATION.md#41-chatprompt-modelnone-function-flow)
- [4.2 _ollama_chat](DOCUMENTATION.md#42-_ollama_chatprompt-modelnone-function-flow)
- [4.3 list_models](DOCUMENTATION.md#43-list_models-function-flow)
- [4.4 _local_stub](DOCUMENTATION.md#44-_local_stubprompt-function-flow)

### Frontend Functions
- [5.1 Upload File Flow](DOCUMENTATION.md#51-upload-file-flow)
- [5.2 Document List Loading](DOCUMENTATION.md#52-document-list-loading-flow)
- [5.3 Chat Query Flow](DOCUMENTATION.md#53-chat-query-flow)
- [5.4 Model Selector](DOCUMENTATION.md#54-model-selector-flow)
- [5.5 Toast System](DOCUMENTATION.md#55-toast-notification-system)

---

## 🔑 Key Concepts

### Document Processing Pipeline
```
Upload → Extract → Chunk → Embed → Store → Search → Retrieve → LLM → Answer
```

### Vector Embeddings
- **Model:** SentenceTransformer (all-MiniLM-L6-v2)
- **Dimension:** 384-D
- **Use:** Semantic similarity search
- **Time:** ~50-100ms per batch of 64 chunks

### Document Structure
```
Document (PDF/DOCX/TXT)
  └─ Chunks (text segments)
      └─ Embeddings (384-D vectors)
      └─ Metadata (source, index)
```

### Chunk ID Format
```
{doc_id}_{chunk_index}
Example: abc123def456_0, abc123def456_1, ...
```

### RAG Pipeline
```
User Question → Embed → Search → Retrieve Top-k → Build Prompt → 
LLM Query (with Retries) → Parse Response → Return Answer + Sources
```

### Rate Limiting
```
Fixed-window counters per IP per endpoint
- /upload: 5 per minute
- /ask: 20 per minute
- Backend: Redis (distributed) or in-memory (local)
```

---

## 🛠 Configuration Reference

### Environment Variables

**Backend (api/main.py)**
```
ALLOWED_ORIGINS        : CORS origins (comma-separated)
CHROMA_DB_DIR         : ChromaDB path (default "./chroma_db")
UPLOAD_DIR            : Upload directory (default ".uploads")
MAX_UPLOAD_SIZE       : Max file size in bytes (default 10MB)
RATE_LIMIT_WINDOW     : Window in seconds (default 60)
UPLOAD_RATE_LIMIT     : Max uploads per window (default 5)
ASK_RATE_LIMIT        : Max /ask per window (default 20)
REDIS_URL             : Redis URL (optional)
LLM_BACKEND           : "ollama" or "local" (default "ollama")
OLLAMA_URL            : Ollama server URL (default http://localhost:11434)
OLLAMA_MODEL          : Default model (default "llama3.1")
```

**Frontend**
```
VITE_API_BASE_URL     : Backend URL (default http://localhost:8000)
```

---

## 📊 Project Statistics

| Aspect | Value |
|--------|-------|
| Total Documentation | 1,681 lines (DOCUMENTATION.md) |
| API Functions Documented | 8 endpoints |
| Indexer Functions Documented | 6 methods |
| Extraction Functions Documented | 4 functions |
| LLM Functions Documented | 4 methods |
| Frontend Functions Documented | 5 flows |
| Total Code Examples | 50+ |
| Flow Diagrams | 15+ |
| Configuration Variables | 15+ |

---

## ⚡ Quick Start Commands

### Docker (Recommended)
```bash
cd d:/projects/notebooklm-local
docker compose build
docker compose up -d
# Frontend: http://localhost:3000
# Backend: http://localhost:8000
```

### Local Development
```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn api.main:app --reload

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

---

## 🔗 Related Files in Repository

- `docker-compose.yml` - Docker orchestration
- `backend/` - FastAPI backend
  - `api/main.py` - Main API (reviewed in docs)
  - `extract.py` - Text extraction (reviewed in docs)
  - `indexer.py` - Vector indexing (reviewed in docs)
  - `llm_client.py` - LLM interface (reviewed in docs)
  - `requirements.txt` - Python dependencies
  - `tests/test_api.py` - Test suite
- `frontend/` - React + Vite frontend
  - `src/App.jsx` - Main UI (reviewed in docs)
  - `src/components/Chat.jsx` - Chat component (reviewed in docs)
  - `package.json` - Node dependencies

---

## 💡 Common Questions

**Q: Where do I start if I'm new?**
A: Start with [README.md](README.md), then read the relevant section in [DOCUMENTATION.md](DOCUMENTATION.md)

**Q: How do I understand a specific function?**
A: Look it up in [FUNCTION_PROCESSING_QUICK_REFERENCE.md](FUNCTION_PROCESSING_QUICK_REFERENCE.md) for quick overview, then [DOCUMENTATION.md](DOCUMENTATION.md) for details

**Q: I want to visualize how things work**
A: Check [DATA_FLOW_DIAGRAMS.md](DATA_FLOW_DIAGRAMS.md)

**Q: How do I debug an issue?**
A: Find the relevant flow in [DATA_FLOW_DIAGRAMS.md](DATA_FLOW_DIAGRAMS.md) → Error Handling Flows

**Q: Where are configuration options documented?**
A: [FUNCTION_PROCESSING_QUICK_REFERENCE.md](FUNCTION_PROCESSING_QUICK_REFERENCE.md) → Configuration Reference

**Q: What changed recently?**
A: See [UPDATES_SUMMARY.md](UPDATES_SUMMARY.md)

---

## 📞 Support & Contribution

For issues or contributions:
1. Check [DOCUMENTATION.md](DOCUMENTATION.md) for implementation details
2. Reference [DATA_FLOW_DIAGRAMS.md](DATA_FLOW_DIAGRAMS.md) to understand flows
3. Use [FUNCTION_PROCESSING_QUICK_REFERENCE.md](FUNCTION_PROCESSING_QUICK_REFERENCE.md) as quick lookup

---

**Last Updated:** December 20, 2025  
**Status:** ✅ Production Ready
