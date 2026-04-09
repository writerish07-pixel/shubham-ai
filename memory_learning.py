"""
memory_learning.py — Vector database memory system for self-learning agent.

🔥 SELF-LEARNING ADDED: Complete vector DB implementation using FAISS for:
- Storing conversation learnings as embeddings
- Storing document content (PDFs, images, offers) as embeddings
- RAG retrieval: fetch relevant past knowledge before generating responses
- Semantic search across all stored knowledge

Architecture:
- Uses sentence-transformers for text → embedding conversion
- Uses FAISS for fast similarity search (in-memory, ~5-20ms per query)
- Persists index + metadata to disk for durability across restarts
- Thread-safe with file locking for concurrent access
"""
import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np

import config

log = logging.getLogger("shubham-ai.memory")

# ── Lazy-loaded globals ───────────────────────────────────────────────────────
_faiss_index = None
_embedding_model = None
_metadata_store: list[dict] = []
# 🔥 FIX: Use RLock (re-entrant) — store/retrieve acquire _lock then call
# _get_faiss_index() which also acquires _lock. A plain Lock would deadlock.
_lock = threading.RLock()

# Storage paths
_INDEX_PATH = config.VECTOR_DB_DIR / "faiss_index.bin"
_METADATA_PATH = config.VECTOR_DB_DIR / "metadata.json"


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Embedding model loader (lazy, loads on first use)
# ══════════════════════════════════════════════════════════════════════════════

def _get_embedding_model():
    """
    Lazy-load the sentence-transformer model.
    Uses all-MiniLM-L6-v2 (~80MB, 384-dim, fast inference).
    First call takes ~2-3s, subsequent calls are instant.
    """
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            log.info("Loading embedding model: %s", config.EMBEDDING_MODEL)
            _embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
            log.info("Embedding model loaded successfully")
        except ImportError:
            log.error("sentence-transformers not installed. Run: pip install sentence-transformers")
            raise
    return _embedding_model


def embed_text(text: str) -> np.ndarray:
    """
    Convert text to embedding vector.
    🔥 SELF-LEARNING ADDED: Returns normalized 384-dim float32 vector.
    """
    model = _get_embedding_model()
    embedding = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
    return np.array(embedding, dtype=np.float32)


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Batch embed multiple texts at once (faster than individual calls).
    🔥 SELF-LEARNING ADDED: Returns (N, 384) float32 matrix.
    """
    if not texts:
        return np.array([], dtype=np.float32).reshape(0, config.EMBEDDING_DIMENSION)
    model = _get_embedding_model()
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False,
                              batch_size=32)
    return np.array(embeddings, dtype=np.float32)


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: FAISS index management
# ══════════════════════════════════════════════════════════════════════════════

def _get_faiss_index():
    """Get or create the FAISS index. Thread-safe, lazy-loaded."""
    global _faiss_index, _metadata_store
    if _faiss_index is not None:
        return _faiss_index

    with _lock:
        if _faiss_index is not None:
            return _faiss_index

        import faiss

        # Try loading existing index from disk
        if _INDEX_PATH.exists() and _METADATA_PATH.exists():
            try:
                _faiss_index = faiss.read_index(str(_INDEX_PATH))
                _metadata_store = json.loads(_METADATA_PATH.read_text(encoding="utf-8"))
                log.info("Loaded FAISS index: %d vectors, %d metadata entries",
                         _faiss_index.ntotal, len(_metadata_store))
                return _faiss_index
            except Exception as e:
                log.warning("Failed to load existing index: %s — creating new", e)

        # Create new index (Inner Product for cosine similarity with normalized vectors)
        _faiss_index = faiss.IndexFlatIP(config.EMBEDDING_DIMENSION)
        _metadata_store = []
        log.info("Created new FAISS index (dim=%d)", config.EMBEDDING_DIMENSION)
        return _faiss_index


def _save_index():
    """Persist FAISS index and metadata to disk. Must be called under _lock."""
    import faiss
    if _faiss_index is not None:
        faiss.write_index(_faiss_index, str(_INDEX_PATH))
        _METADATA_PATH.write_text(
            json.dumps(_metadata_store, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Store and retrieve knowledge
# ══════════════════════════════════════════════════════════════════════════════

def store_learning(text: str, metadata: dict) -> bool:
    """
    Store a learning (text + metadata) in the vector DB.

    Args:
        text: The text content to store (will be embedded)
        metadata: Dict with keys like:
            - type: "conversation" | "objection" | "document" | "offer" | "pricing"
            - source: "call_<sid>" | "pdf_<filename>" | "manual"
            - timestamp: ISO datetime string
            - extra fields depending on type

    Returns:
        True if stored successfully, False otherwise.
    """
    if not text or not text.strip():
        return False

    try:
        embedding = embed_text(text)
        embedding = embedding.reshape(1, -1)

        with _lock:
            index = _get_faiss_index()
            idx = index.ntotal  # current count = new item's index
            index.add(embedding)
            _metadata_store.append({
                "id": idx,
                "text": text[:2000],  # cap stored text at 2000 chars
                "metadata": metadata,
                "stored_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            _save_index()

        log.info("Stored learning #%d (type=%s): %.80s...",
                 idx, metadata.get("type", "unknown"), text)
        return True
    except Exception as e:
        log.error("Failed to store learning: %s", e)
        return False


def store_learnings_batch(items: list[dict]) -> int:
    """
    Batch store multiple learnings at once (more efficient).

    Args:
        items: List of dicts with keys "text" and "metadata"

    Returns:
        Number of items successfully stored.
    """
    if not items:
        return 0

    texts = [item["text"] for item in items if item.get("text", "").strip()]
    if not texts:
        return 0

    try:
        embeddings = embed_texts(texts)

        with _lock:
            index = _get_faiss_index()
            start_idx = index.ntotal
            index.add(embeddings)

            for i, item in enumerate(items):
                if not item.get("text", "").strip():
                    continue
                _metadata_store.append({
                    "id": start_idx + i,
                    "text": item["text"][:2000],
                    "metadata": item.get("metadata", {}),
                    "stored_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
            _save_index()

        log.info("Batch stored %d learnings", len(texts))
        return len(texts)
    except Exception as e:
        log.error("Batch store failed: %s", e)
        return 0


def retrieve_relevant(query: str, top_k: int = None,
                      min_similarity: float = None,
                      filter_type: Optional[str] = None) -> list[dict]:
    """
    🔥 SELF-LEARNING ADDED: RAG retrieval — find most relevant past learnings.

    Args:
        query: The search query (customer's question, topic, etc.)
        top_k: Number of results to return (default: RAG_TOP_K from config)
        min_similarity: Minimum cosine similarity threshold (default: RAG_MIN_SIMILARITY)
        filter_type: Optional filter by metadata type ("conversation", "document", etc.)

    Returns:
        List of dicts: [{"text": "...", "score": 0.85, "metadata": {...}}, ...]
        Sorted by relevance (highest score first).
    """
    if top_k is None:
        top_k = config.RAG_TOP_K
    if min_similarity is None:
        min_similarity = config.RAG_MIN_SIMILARITY

    try:
        # 🔥 FIX: Acquire lock to prevent race condition with concurrent store operations
        with _lock:
            index = _get_faiss_index()
            if index.ntotal == 0:
                return []

            query_embedding = embed_text(query).reshape(1, -1)

            # Search more than needed if filtering by type
            search_k = min(top_k * 3 if filter_type else top_k, index.ntotal)
            scores, indices = index.search(query_embedding, search_k)

            # Snapshot metadata under lock to avoid race with concurrent writes
            metadata_snapshot = list(_metadata_store)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(metadata_snapshot):
                continue
            if score < min_similarity:
                continue

            entry = metadata_snapshot[idx]
            if filter_type and entry.get("metadata", {}).get("type") != filter_type:
                continue

            results.append({
                "text": entry["text"],
                "score": float(score),
                "metadata": entry.get("metadata", {}),
            })

            if len(results) >= top_k:
                break

        return results
    except Exception as e:
        log.error("RAG retrieval failed: %s", e)
        return []


def get_relevant_context(query: str, max_chars: int = 800) -> str:
    """
    🔥 SELF-LEARNING ADDED: Get formatted context string for RAG injection.

    Retrieves relevant past learnings and formats them as a compact string
    that can be injected into the system prompt before generating a response.

    Args:
        query: The customer's current message
        max_chars: Maximum total characters for the context block

    Returns:
        Formatted string like:
        "[Past Learning] Customer asked about Splendor price → ₹74K-78K ex-showroom"
        "[Past Learning] Objection: price too high → Offered EMI ₹1800/month"
    """
    results = retrieve_relevant(query)
    if not results:
        return ""

    lines = []
    total_chars = 0
    for r in results:
        entry_type = r["metadata"].get("type", "learning")
        text = r["text"].strip()
        # Truncate individual entries if too long
        if len(text) > 200:
            text = text[:197] + "..."
        line = f"[{entry_type}] {text}"
        if total_chars + len(line) > max_chars:
            break
        lines.append(line)
        total_chars += len(line)

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Utility functions
# ══════════════════════════════════════════════════════════════════════════════

def get_stats() -> dict:
    """Return vector DB statistics."""
    try:
        index = _get_faiss_index()
        type_counts: dict[str, int] = {}
        for entry in _metadata_store:
            t = entry.get("metadata", {}).get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        return {
            "total_vectors": index.ntotal,
            "total_metadata": len(_metadata_store),
            "type_counts": type_counts,
            "index_path": str(_INDEX_PATH),
        }
    except Exception as e:
        return {"error": str(e)}


def clear_all():
    """Clear all stored data. Use with caution!"""
    global _faiss_index, _metadata_store
    import faiss
    with _lock:
        _faiss_index = faiss.IndexFlatIP(config.EMBEDDING_DIMENSION)
        _metadata_store = []
        _save_index()
    log.warning("Vector DB cleared — all learnings deleted")
