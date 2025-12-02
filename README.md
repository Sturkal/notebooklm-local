**NotebookLM (local)**

Short description:
- NotebookLM is a minimal local RAG (retrieval-augmented generation) demo: upload documents, index them with embeddings (ChromaDB + sentence-transformers), and ask questions through a chat UI that forwards context to a local LLM (default: Ollama).

**Repository layout**
- `docker-compose.yml` — orchestrates two services: `backend` (FastAPI) and `frontend` (Vite React).
- `README.md` — this file.
- `DEPENDENCY_UPGRADE_PLAN.md` — proposed conservative dependency upgrades and instructions.

- `backend/` — Python backend service
	- `Dockerfile` — Docker image for backend
	# NotebookLM (local)

	A minimal local Retrieval-Augmented Generation (RAG) demo. Upload documents (PDF/DOCX/TXT), index them locally (ChromaDB + sentence-transformers), and ask questions in a chat UI that builds a RAG prompt and queries a local LLM (default integration: Ollama).

	This README documents the current state of the project, how to run it (Docker or local), the available features (including OCR fallback and model selection), and troubleshooting tips.

	**Repository layout**
	- `docker-compose.yml` — orchestrates services: `backend` (FastAPI) and `frontend` (Vite React).
	- `backend/` — Python backend service
		- `Dockerfile` — builds backend container (installs Tesseract, poppler, system libs required by PDF/image extraction)
		- `requirements.txt` — Python dependencies (pinned where required)
		- `api/main.py` — FastAPI app and endpoints (`/upload`, `/ask`, `/health`, `/documents`, `/llm/models`)
		- `extract.py` — extract text from PDF/DOCX/TXT; optional OCR fallback (pytesseract + pdf2image)
		- `indexer.py` — Indexer: chunks text, creates embeddings (SentenceTransformer), stores vectors in ChromaDB
		- `llm_client.py` — wrapper around LLM backend (Ollama by default) with retries, timeouts, tolerant parsing and a `list_models()` helper
		- `chroma_db/` — (optional) local sqlite/Chroma store when running without an external volume
	- `frontend/` — React + Vite frontend
		- `src/App.jsx` — main UI (upload + sidebar + documents list)
		- `src/components/Chat.jsx` — chat component (model selector, send queries, display answers, sources and error details)
		- `src/style.css` — UI styles (toasts, spinner, scrollable areas)

	Status / Key features
	- Upload files (PDF/DOCX/TXT), extract text, index into ChromaDB.
	- Optional OCR fallback for PDFs (Tesseract + pdf2image). You can enable OCR per-upload from the frontend and set an OCR max page limit.
	- Frontend shows upload progress, OCR status, and a success toast containing `ocr_used`, `page_count` and `ocr_truncated` when applicable.
	- Documents list in the sidebar (with delete) — scrollable when long.
	- Chat UI: sends RAG-based prompt to LLM and displays answer, sources and snippets.
	- Model selection: frontend fetches available models from the backend (`GET /llm/models`) and lets user pick a model to use for `/ask` requests.
	- Friendly LLM error handling in the chat UI: if the backend returns a low-level connection error (e.g., Ollama not running), the UI shows a friendly message and a collapsible raw-error block for diagnostics.

	Important endpoints (backend)
	- `POST /upload` — multipart/form-data with `file` and optional form fields `enable_ocr` (`true|false`) and `ocr_max_pages` (int). Response example (success):

		{
			"status": "ok",
			"doc_id": "<hex-id>",
			"ocr_used": true,
			"page_count": 7,
			"ocr_truncated": false
		}

	- `GET /ask?q=...&top_k=5&model=<modelname>` — performs retrieval, builds the RAG prompt and forwards it to the configured LLM. The optional `model` query param is passed to the LLM client (Ollama `?model=`).

	- `GET /documents` — returns a JSON array of indexed documents: `{ documents: [ { doc_id, count, sample_metadata }, ... ] }`.

	- `DELETE /documents/{doc_id}` — deletes all chunks for the doc id.

	- `GET /health` — basic health check.

	- `GET /llm/models` — queries the configured LLM backend (Ollama) for available models and returns `{ models: [ ... ] }`. If the LLM backend is not available or doesn't support model listing, an empty array is returned.

	Environment variables (common)
	- `CHROMA_DB_DIR` — path for ChromaDB persistence inside backend (docker-compose sets `/data/chroma`).
	- `UPLOAD_DIR` — where uploaded files are stored (default: `.uploads`).
	- `LLM_BACKEND` — which backend to use (`ollama` or `local`).
	- `OLLAMA_URL` — base URL for Ollama (default `http://localhost:11434`).
	- `OLLAMA_MODEL` — default model name used when no `model` param is supplied.
	- `VITE_API_BASE_URL` — used by the frontend container to call the backend service (set in `docker-compose.yml`). In dev, the frontend script falls back to `http://localhost:8000`.

	Run with Docker (recommended)
	1. From repository root (PowerShell):

	```powershell
	cd d:/projects/notebooklm-local
	docker compose build
	docker compose up -d
	```

	2. Open the frontend in your browser. When using the Docker Compose defaults:
	- Frontend: http://localhost:3000
	- Backend: http://localhost:8000

	Run locally (no Docker)

	Backend (PowerShell):

	```powershell
	cd d:/projects/notebooklm-local/backend
	python -m venv .venv
	.\.venv\Scripts\Activate.ps1
	pip install -r requirements.txt
	uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
	```

	Notes for Windows users: some packages used by `chromadb` or `onnxruntime` may not provide wheels for all Windows/Python combinations. If you encounter pip errors related to `onnxruntime`, try using Python 3.10 or 3.11 where wheels are widely available, or run in Docker where the image's environment is controlled.

	Frontend (dev)

	```powershell
	cd d:/projects/notebooklm-local/frontend
	npm install
	npm run dev
	```

	Useful developer commands

	- Tail backend logs (Docker Compose):

	```powershell
	docker compose logs -f backend
	```

	- Rebuild backend image after code changes (Docker):

	```powershell
	docker compose build backend
	docker compose up -d
	```

	Uploading and using OCR

	- From the frontend upload panel you can enable the OCR fallback and set `OCR max pages`. If the extractor finds no text in the PDF and OCR is enabled, the backend will run page-by-page OCR (up to the configured max pages) and return `ocr_used`, `page_count`, and `ocr_truncated` in the upload response.

	- Backend OCR requirements (Docker image includes these):
		- `tesseract-ocr` (system package), Python packages: `pytesseract`, `pdf2image`.
		- On non-Docker hosts, `poppler` is required for `pdf2image` to render pages. Install `poppler` (e.g., via `choco install poppler` on Windows or `apt-get install poppler-utils` on Debian/Ubuntu).

	Frontend UX notes

	- The sidebar Uploaded Documents list is scrollable when it grows long.
	- Upload button shows an OCR-specific spinner/message when OCR is enabled.
	- Chat UI:
		- Fetches available LLM models from `/llm/models` and displays a selector.
		- Sends the selected model (if any) via `&model=...` to `/ask`.
		- On LLM transport errors (e.g., connection refused to Ollama), the chat shows a friendly message and a collapsible raw error detail for debugging.

	Troubleshooting

	- Ollama (LLM) connection refused:
		- Symptom: chat responses show a friendly LLM-unavailable message and the raw error details contain text like:

			```
			HTTPConnectionPool(host='localhost', port=11434): Max retries exceeded with url: /chat?model=... (Caused by NewConnectionError(...): Failed to establish a new connection: [Errno 111] Connection refused)
			```

		- Fix: ensure the local Ollama server is running and listening on `OLLAMA_URL` (default `http://localhost:11434`). If you don't have Ollama, consider configuring `LLM_BACKEND=local` and implement a local LLM backend, or point `OLLAMA_URL` to another compatible LLM HTTP API.

	- OCR failures on host runs:
		- Symptom: backend raises PDF/image conversion errors or `pdf2image` cannot find `pdftoppm`.
		- Fix: install `poppler` (host system). On Windows: install `poppler` via Chocolatey or download binaries and add to PATH.

	- `chromadb` / `onnxruntime` install issues:
		- Symptom: pip install fails for `onnxruntime` on Windows.
		- Fix: use Docker or switch to a Python version that has wheels for `onnxruntime` (commonly 3.10 or 3.11). Alternatively, pin `chromadb` to a tested version in `backend/requirements.txt`.

	Testing / quick examples

	- Upload a file with curl (PowerShell):

	```powershell
	curl -X POST "http://localhost:8000/upload" -F "file=@C:/path/to/doc.pdf" -F "enable_ocr=true" -F "ocr_max_pages=10"
	```

	- Ask a question:

	```powershell
	curl "http://localhost:8000/ask?q=Summarize+the+document&top_k=5"
	```

	- List models from LLM backend:

	```powershell
	curl "http://localhost:8000/llm/models"
	```

	Development ideas / next steps

	- Persist the selected LLM model in `localStorage` so the user choice survives reloads (easy frontend change).
	- Store OCR `page_count` and `ocr_truncated` in document metadata during indexing so the documents list can display per-document OCR stats.
	- Add integration tests that run in a controlled environment (Docker) to upload a sample document and run `/ask`.

	If you want, I can:
	- add the `localStorage` persistence for the selected model,
	- persist OCR metadata into Chroma document metadata and surface it in the documents list,
	- add an automated smoke test and CI step that runs upload + query against an in-container Chromadb and a stub LLM.

	---

	If you'd like a specific part of this README expanded (for example, a developer quickstart script, a CONTRIBUTING section, or a detailed dependency matrix), tell me which section and I'll add it.
