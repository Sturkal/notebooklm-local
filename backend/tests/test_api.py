import io
import os
import json
import tempfile
import sys
from fastapi.testclient import TestClient

# Add parent directory to path so we can import api
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api import main as main_mod

client = TestClient(main_mod.app)


class StubIndexer:
    def __init__(self):
        self.docs = []

    def index_document(self, doc_id, text, metadata=None):
        self.docs.append({"doc_id": doc_id, "text": text, "metadata": metadata})

    def chunk_document(self, text: str, chunk_size: int = 512, chunk_overlap: int = 50):
        if not text:
            return []
        # naive chunk: split by whitespace into one chunk
        return [text]

    def list_documents(self):
        return [
            {"doc_id": d["doc_id"], "count": 1, "sample_metadata": d.get("metadata")}
            for d in self.docs
        ]

    def delete_document(self, doc_id):
        before = len(self.docs)
        self.docs = [d for d in self.docs if d["doc_id"] != doc_id]
        return len(self.docs) < before


def setup_module(module):
    # Replace the real indexer with a stub to avoid heavy model downloads during tests
    main_mod.IDX = StubIndexer()
    # Use a temporary upload dir
    tmp = tempfile.mkdtemp(prefix="nlm_test_")
    main_mod.UPLOAD_DIR = tmp
    os.makedirs(main_mod.UPLOAD_DIR, exist_ok=True)


def teardown_module(module):
    # cleanup upload dir
    try:
        for f in os.listdir(main_mod.UPLOAD_DIR):
            os.remove(os.path.join(main_mod.UPLOAD_DIR, f))
        os.rmdir(main_mod.UPLOAD_DIR)
    except Exception:
        pass


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_upload_txt_success():
    data = io.BytesIO(b"Hello world from test file\nThis is a test.")
    files = {"file": ("test.txt", data, "text/plain")}
    r = client.post("/upload", files=files)
    assert r.status_code == 200
    j = r.json()
    assert j.get("status") == "ok"
    assert "doc_id" in j


def test_list_documents():
    r = client.get("/documents")
    assert r.status_code == 200
    j = r.json()
    assert "documents" in j


def test_delete_document():
    # upload another file
    data = io.BytesIO(b"Another file\n")
    files = {"file": ("afile.txt", data, "text/plain")}
    r = client.post("/upload", files=files)
    assert r.status_code == 200
    doc_id = r.json().get("doc_id")

    # delete
    r2 = client.delete(f"/documents/{doc_id}")
    assert r2.status_code == 200
    assert r2.json().get("deleted") == doc_id


def test_upload_too_large():
    # create data larger than MAX_UPLOAD_SIZE
    size = main_mod.MAX_UPLOAD_SIZE + 1
    data = io.BytesIO(b"a" * size)
    files = {"file": ("big.txt", data, "text/plain")}
    r = client.post("/upload", files=files)
    assert r.status_code == 413
