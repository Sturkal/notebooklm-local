"""
indexer.py - Document Indexing and Vector Search
==================================================

This module provides the Indexer class which handles:
- Document chunking: splits text into semantic chunks for embedding
- Embedding: converts text chunks to vector embeddings using SentenceTransformer
- Storage: persists vectors in ChromaDB for efficient similarity search
- Retrieval: queries the vector DB to find most similar chunks to a query

Key Features:
- Lazy imports: defers heavy ML/DB dependencies until Indexer instantiation
- Batch embedding: encodes multiple chunks efficiently (batch_size=64)
- Paragraph-first chunking: respects document structure before word-level splitting
- Defensive checks: handles empty chunks, validates embedding dimensions
- ChromaDB compatibility: handles variable response shapes across versions
- Metadata tracking: stores source filenames and other chunk metadata

Environment Variables:
    CHROMA_DB_DIR  : Path for ChromaDB persistence (default "./chroma_db")
                     In Docker, set to "/data/chroma" for persistent volume mount
"""

import os
import math
from typing import List

EMBED_MODEL = "all-MiniLM-L6-v2"  # SentenceTransformer model ID


class Indexer:
    def __init__(self, db_dir: str | None = None):
        """
        Initialize the Indexer with lazy loading of heavy dependencies.

        This defers imports of SentenceTransformer and ChromaDB until instantiation,
        which improves startup time and helps with testing (tests can mock Indexer
        without loading ML models).

        Args:
            db_dir (str | None): Path for ChromaDB persistence. If None, uses CHROMA_DB_DIR env var
                                 or defaults to "./chroma_db"

        Raises:
            ImportError: If sentence-transformers or chromadb cannot be imported

        Side Effects:
            - Creates db_dir if it doesn't exist
            - Loads the embedding model (slow, ~200MB + inference time)
            - Initializes ChromaDB connection
        """
        # Allow overriding via environment so Docker and local dev use same path
        if db_dir is None:
            db_dir = os.environ.get("CHROMA_DB_DIR", "./chroma_db")
        self.db_dir = db_dir
        os.makedirs(self.db_dir, exist_ok=True)

        # Lazily import heavy ML / DB dependencies to avoid import-time costs
        try:
            from sentence_transformers import SentenceTransformer
            import chromadb
        except Exception as e:
            # Defer failure until the Indexer is actually used; re-raise to show useful message
            raise ImportError(f"Failed to import indexer dependencies: {e}")

        # Initialize the embedding model (SentenceTransformer)
        # "all-MiniLM-L6-v2" is a lightweight, fast model suitable for semantic search
        # It produces 384-dimensional embeddings
        self.embed_model = SentenceTransformer(EMBED_MODEL)

        # Initialize ChromaDB persistent client
        # Uses SQLite backend by default, stored in self.db_dir
        self.client = chromadb.PersistentClient(path=self.db_dir)

        # Get or create a collection for storing document embeddings
        # Each collection is isolated and can have different schemas
        self.collection = self.client.get_or_create_collection("notebook_collection")

    def chunk_text(self, text: str, chunk_size: int = 400, overlap: int = 50):
        """
        Deprecated: Use chunk_document() instead. This remains for backward compatibility.

        Simple word-based chunking with fixed overlap.
        """
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunk = words[i : i + chunk_size]
            chunks.append(" ".join(chunk))
            i += chunk_size - overlap
        return chunks

    def chunk_document(
        self, text: str, chunk_size: int = 512, chunk_overlap: int = 50
    ) -> List[str]:
        """
        Split a document into semantic chunks for embedding.

        Strategy:
        1. Split by double newlines to preserve paragraph structure
        2. If a paragraph is short, keep it as-is
        3. If a paragraph is long, split it into word-level chunks with overlap
        4. Fallback: if no chunks generated, return the entire text as a single chunk

        This approach balances:
        - Semantic coherence (respecting paragraphs)
        - Practical chunk size (for embedding and context windows)
        - Coverage (ensuring no text is lost)

        Args:
            text (str): The document text to chunk
            chunk_size (int): Target size in characters (rough estimate)
            chunk_overlap (int): Overlap between consecutive chunks in characters

        Returns:
            List[str]: Non-empty list of text chunks, guaranteed to contain all input text

        Notes:
            - Empty strings are filtered out
            - Very short text returns as-is (single chunk)
            - Heuristic word count estimate assumes ~5 chars per word
        """
        if not text:
            return []

        # Step 1: Split by paragraph boundaries (double newline)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: List[str] = []

        for para in paragraphs:
            # Keep short paragraphs as-is
            if len(para) <= chunk_size:
                chunks.append(para)
                continue

            # Long paragraphs: split into word-based chunks with overlap
            words = para.split()
            if not words:
                continue

            i = 0
            w_chunk_size = max(1, chunk_size // 5)  # Heuristic: ~5 chars per word
            while i < len(words):
                part = words[i : i + w_chunk_size]
                chunks.append(" ".join(part))
                i += w_chunk_size - max(1, chunk_overlap // 5)

        # Fallback: if still no chunks (very short text), return the text as-is
        if not chunks and text:
            return [text]

        return chunks

    def index_document(self, doc_id: str, text: str, metadata: dict | None = None):
        """
        Index a document: chunk it, embed chunks, and store in ChromaDB.

        Steps:
        1. Chunk the text into semantic pieces
        2. Encode chunks into dense vectors using SentenceTransformer
        3. Validate embeddings have correct dimensions
        4. Store chunks, embeddings, and metadata in ChromaDB

        Args:
            doc_id (str): Unique identifier for this document
            text (str): The document text to index
            metadata (dict | None): Optional metadata (e.g., {"source_filename": "doc.pdf"})
                                   Stored with each chunk for retrieval context

        Raises:
            ValueError: If no chunks generated or embeddings are empty
            Exception: From embedding or ChromaDB operations

        Notes:
            - Chunks are assigned IDs: {doc_id}_{i} for chunk i
            - All chunks get the same metadata dict
            - Embeddings use batch_size=64 for efficiency (falls back for older versions)
            - Results are persisted to disk immediately
        """
        # Step 1: Chunk the document
        chunks = self.chunk_document(text, chunk_size=512, chunk_overlap=50)

        if not chunks:
            raise ValueError(
                "No text chunks generated for indexing (empty document or extraction failure)"
            )

        # Step 2: Encode chunks into embeddings
        # Uses batch processing for efficiency (reduces memory and speeds up inference)
        # Fallback for older sentence-transformers versions that don't support batch_size
        try:
            embeddings = self.embed_model.encode(
                chunks, batch_size=64, show_progress_bar=False
            )
        except TypeError:
            # Older sentence-transformers versions may not accept batch_size kwarg
            embeddings = self.embed_model.encode(chunks, show_progress_bar=False)

        # Step 3: Normalize embeddings and validate
        # Embeddings may be returned as different types; normalize to list-of-lists
        try:
            import numpy as _np

            emb_arr = _np.array(embeddings)
            if emb_arr.size == 0 or emb_arr.shape[0] == 0:
                raise ValueError("Computed embeddings are empty")
            emb_list = emb_arr.tolist()
        except Exception:
            # Fallback: if embeddings is already list-like, use directly
            emb_list = embeddings if isinstance(embeddings, list) else list(embeddings)
            if not emb_list:
                raise ValueError("Computed embeddings are empty")

        # Step 4: Prepare IDs and metadata for ChromaDB
        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [metadata or {} for _ in chunks]

        # Validate consistency
        if len(emb_list) != len(chunks):
            raise ValueError(
                f"Embeddings length ({len(emb_list)}) does not match chunks ({len(chunks)})"
            )

        # Step 5: Store in ChromaDB
        self.collection.add(
            ids=ids, documents=chunks, metadatas=metadatas, embeddings=emb_list
        )

    def query(self, query_text: str, top_k: int = 5):
        """
        Find the most similar document chunks to a query using vector similarity.

        Steps:
        1. Embed the query text using the same model as documents
        2. Search ChromaDB for chunks with highest cosine similarity
        3. Return matched chunks, IDs, and metadata

        Args:
            query_text (str): The user's query or question
            top_k (int): Maximum number of results to return

        Returns:
            dict: ChromaDB query response with keys:
                - "documents": list of lists [chunk_text_1, ...]
                - "ids": list of lists [chunk_id_1, ...]
                - "metadatas": list of lists [chunk_metadata_1, ...]
                - "distances": similarity scores (not always present)

        Notes:
            - Uses cosine similarity by default in ChromaDB
            - Embeddings are compared in the same vector space as indexed documents
            - If no chunks match, returns empty results
        """
        # Embed the query using the same model as indexed documents
        q_emb = self.embed_model.encode([query_text])[0].tolist()

        # Query ChromaDB with the query embedding
        res = self.collection.query(query_embeddings=[q_emb], n_results=top_k)

        # Returns documents, metadatas, ids (and possibly distances)
        return res

    def list_documents(self):
        """
        List all indexed documents with their metadata.

        Returns a summary of each unique document currently indexed, including:
        - doc_id: The document identifier
        - count: Number of chunks from this document
        - sample_metadata: Metadata from one chunk (typically source_filename)

        Returns:
            list: [
                {"doc_id": str, "count": int, "sample_metadata": dict},
                ...
            ]

        Notes:
            - Handles different ChromaDB response shapes (nested vs flat lists)
            - Aggregates all chunks by doc_id (chunks are named {doc_id}_{i})
            - Useful for UI: shows all documents and their index status
            - sample_metadata typically contains {"source_filename": "..."}
        """
        try:
            res = self.collection.get(include=["ids", "metadatas"])
        except Exception:
            # some chromadb versions return different shapes; try without include
            res = self.collection.get()

        ids = []
        metadatas = []
        if isinstance(res, dict):
            raw_ids = res.get("ids", [])
            raw_metas = res.get("metadatas", [])

            # Chroma may return either a list-of-lists (e.g. [[id1,id2]])
            # or a flat list [id1, id2]. Normalize to a flat list.
            if isinstance(raw_ids, list) and raw_ids and isinstance(raw_ids[0], list):
                ids = raw_ids[0]
            else:
                ids = raw_ids or []

            if (
                isinstance(raw_metas, list)
                and raw_metas
                and isinstance(raw_metas[0], list)
            ):
                metadatas = raw_metas[0]
            else:
                metadatas = raw_metas or []

        # Aggregate chunks by document ID (chunks are named {doc_id}_{i})
        docs = {}
        for i, full_id in enumerate(ids):
            if not isinstance(full_id, str):
                continue
            # Extract the doc_id from the chunk ID
            doc_id = full_id.split("_")[0]
            docs.setdefault(
                doc_id, {"doc_id": doc_id, "count": 0, "sample_metadata": None}
            )
            docs[doc_id]["count"] += 1
            # Store metadata from the first chunk as a sample
            if docs[doc_id]["sample_metadata"] is None and i < len(metadatas):
                docs[doc_id]["sample_metadata"] = metadatas[i]

        return list(docs.values())

    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document and all its chunks from the index.

        Removes all chunks matching the pattern {doc_id}_* from ChromaDB,
        effectively removing the entire document.

        Args:
            doc_id (str): The document identifier to delete

        Returns:
            bool: True if at least one chunk was deleted, False if no chunks found

        Notes:
            - This is irreversible (unless you have backups)
            - Does not delete the original file from UPLOAD_DIR
            - The vector embeddings and ChromaDB entries are permanently removed
            - Frontend should refresh the documents list after delete
        """
        try:
            res = self.collection.get(include=["ids"])
        except Exception:
            res = self.collection.get()

        # Normalize returned ids shape: chroma may return nested list ([ [id1,id2] ])
        # or a flat list ([id1,id2]). Handle both cases robustly.
        ids = []
        if isinstance(res, dict):
            raw_ids = res.get("ids", [])
            if isinstance(raw_ids, list) and raw_ids and isinstance(raw_ids[0], list):
                ids = raw_ids[0]
            else:
                ids = raw_ids or []

        # Find all chunks belonging to this document (pattern: {doc_id}_*)
        to_delete = [
            i for i in ids if isinstance(i, str) and i.startswith(f"{doc_id}_")
        ]

        if not to_delete:
            return False

        # Delete all matching chunks from ChromaDB
        self.collection.delete(ids=to_delete)
        return True


# ============================================================================
# Module-level Quick Test
# ============================================================================
# This allows running the file directly to test basic Indexer functionality:
# python indexer.py
#
# Creates a test document and performs a simple query

if __name__ == "__main__":
    idx = Indexer()
    idx.index_document("testdoc", "This is a test document. " * 300)
    print(idx.query("test"))
