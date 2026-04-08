"""
document_learning.py — PDF, JPEG, and Excel document learning system.

🔥 SELF-LEARNING ADDED: Ingests documents into the vector DB so the agent can:
- Answer price queries from uploaded price lists
- Reference current offers/schemes from PDFs
- Use information from brochures and posters (JPEG/PNG via OCR)

Pipeline:
1. Upload PDF/JPEG/Excel → extract text (using existing scraper.py parsers)
2. Chunk text into segments (500 chars with 50 char overlap)
3. Embed each chunk → store in FAISS vector DB
4. During calls, RAG retrieves relevant chunks to answer queries

Reuses scraper.py's parse_offer_file() for extraction — no duplicate parsers.
"""
import json
import logging
import time
from pathlib import Path
from typing import Optional

import config_learning as config

log = logging.getLogger("shubham-ai.document-learning")


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Document ingestion pipeline
# ══════════════════════════════════════════════════════════════════════════════

def ingest_document(filepath: str, doc_type: str = "auto",
                    doc_name: str = "") -> dict:
    """
    🔥 PDF PARSER ADDED: Ingest a document into the vector DB.

    Steps:
    1. Extract text from file (PDF, JPEG, Excel, CSV)
    2. Split into overlapping chunks
    3. Embed each chunk and store in FAISS

    Args:
        filepath: Path to the document file
        doc_type: "pdf", "image", "excel", or "auto" (detect from extension)
        doc_name: Human-readable name for this document (default: filename)

    Returns:
        {"success": True, "chunks_stored": 5, "doc_name": "..."} or
        {"success": False, "error": "..."}
    """
    path = Path(filepath)
    if not path.exists():
        return {"success": False, "error": f"File not found: {filepath}"}

    if not doc_name:
        doc_name = path.name

    # Step 1: Extract text using existing scraper.py parsers
    try:
        from scraper import parse_offer_file
        raw_text = parse_offer_file(filepath)
        if not raw_text or raw_text.startswith("Error") or raw_text.startswith("Unsupported"):
            return {"success": False, "error": f"Failed to extract text: {raw_text}"}
    except Exception as e:
        return {"success": False, "error": f"Extraction failed: {e}"}

    log.info("Extracted %d chars from %s", len(raw_text), doc_name)

    # Step 2: Detect document category
    category = _detect_document_category(raw_text, doc_name)

    # Step 3: Chunk text
    chunks = _chunk_text(raw_text, config.DOC_CHUNK_SIZE, config.DOC_CHUNK_OVERLAP)
    if not chunks:
        return {"success": False, "error": "No text chunks extracted"}

    log.info("Split into %d chunks (size=%d, overlap=%d)",
             len(chunks), config.DOC_CHUNK_SIZE, config.DOC_CHUNK_OVERLAP)

    # Step 4: Store in vector DB
    import memory_learning as memory

    items = []
    for i, chunk in enumerate(chunks):
        items.append({
            "text": chunk,
            "metadata": {
                "type": "document",
                "category": category,
                "doc_name": doc_name,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "source": f"doc_{path.stem}",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        })

    stored = memory.store_learnings_batch(items)

    # Step 5: Log ingestion
    _log_ingestion(doc_name, filepath, category, len(chunks), stored)

    log.info("Document '%s' ingested: %d/%d chunks stored", doc_name, stored, len(chunks))
    return {
        "success": True,
        "doc_name": doc_name,
        "category": category,
        "total_chars": len(raw_text),
        "chunks_created": len(chunks),
        "chunks_stored": stored,
    }


def ingest_text_directly(text: str, doc_name: str, category: str = "manual") -> dict:
    """
    🔥 SELF-LEARNING ADDED: Ingest raw text directly (no file needed).

    Useful for:
    - Manual knowledge entry from admin dashboard
    - Pasting offer details
    - Adding FAQ answers

    Args:
        text: Raw text content
        doc_name: Name/label for this content
        category: "pricing", "offer", "faq", "manual"

    Returns:
        {"success": True, "chunks_stored": N}
    """
    if not text or not text.strip():
        return {"success": False, "error": "Empty text"}

    chunks = _chunk_text(text, config.DOC_CHUNK_SIZE, config.DOC_CHUNK_OVERLAP)
    if not chunks:
        return {"success": False, "error": "No chunks generated"}

    import memory_learning as memory

    items = []
    for i, chunk in enumerate(chunks):
        items.append({
            "text": chunk,
            "metadata": {
                "type": "document",
                "category": category,
                "doc_name": doc_name,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "source": "manual_entry",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        })

    stored = memory.store_learnings_batch(items)
    return {"success": True, "chunks_stored": stored}


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Text chunking
# ══════════════════════════════════════════════════════════════════════════════

def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    Split text into overlapping chunks for embedding.

    Uses sentence-aware splitting: tries to break at sentence boundaries
    (periods, question marks, newlines) to keep chunks semantically coherent.

    Args:
        text: Full text to chunk
        chunk_size: Target size per chunk (chars)
        overlap: Overlap between consecutive chunks (chars)

    Returns:
        List of text chunks
    """
    text = text.strip()
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    # Split on sentence boundaries
    import re
    sentences = re.split(r'(?<=[.!?\n।])\s+', text)

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(current_chunk) + len(sentence) + 1 <= chunk_size:
            current_chunk = (current_chunk + " " + sentence).strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)
                # Keep overlap from end of current chunk
                if overlap > 0 and len(current_chunk) > overlap:
                    current_chunk = current_chunk[-overlap:] + " " + sentence
                else:
                    current_chunk = sentence
            else:
                # Single sentence longer than chunk_size — force split
                while len(sentence) > chunk_size:
                    chunks.append(sentence[:chunk_size])
                    sentence = sentence[chunk_size - overlap:] if overlap else sentence[chunk_size:]
                current_chunk = sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Document category detection
# ══════════════════════════════════════════════════════════════════════════════

def _detect_document_category(text: str, filename: str) -> str:
    """
    Auto-detect document category from content and filename.

    Categories: "pricing", "offer", "brochure", "scheme", "general"
    """
    text_lower = text.lower()
    filename_lower = filename.lower()

    # Check filename first
    if any(kw in filename_lower for kw in ["price", "pricing", "rate", "daam"]):
        return "pricing"
    if any(kw in filename_lower for kw in ["offer", "scheme", "discount", "cashback"]):
        return "offer"
    if any(kw in filename_lower for kw in ["brochure", "catalog", "spec"]):
        return "brochure"

    # Check content
    price_keywords = ["price", "₹", "rs.", "rs ", "mrp", "ex-showroom", "on-road",
                      "कीमत", "दाम", "रुपये"]
    offer_keywords = ["offer", "discount", "cashback", "scheme", "exchange",
                      "ऑफर", "छूट", "कैशबैक"]

    price_count = sum(1 for kw in price_keywords if kw in text_lower)
    offer_count = sum(1 for kw in offer_keywords if kw in text_lower)

    if price_count >= 3:
        return "pricing"
    if offer_count >= 2:
        return "offer"

    return "general"


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Ingestion logging
# ══════════════════════════════════════════════════════════════════════════════

_INGESTION_LOG = config.DOCUMENTS_DIR / "ingestion_log.json"


def _log_ingestion(doc_name: str, filepath: str, category: str,
                   total_chunks: int, stored_chunks: int):
    """Log document ingestion for tracking."""
    entry = {
        "doc_name": doc_name,
        "filepath": str(filepath),
        "category": category,
        "total_chunks": total_chunks,
        "stored_chunks": stored_chunks,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    data = []
    if _INGESTION_LOG.exists():
        try:
            data = json.loads(_INGESTION_LOG.read_text(encoding="utf-8"))
        except Exception:
            data = []
    data.append(entry)
    _INGESTION_LOG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_ingested_documents() -> list[dict]:
    """Return list of all ingested documents."""
    if not _INGESTION_LOG.exists():
        return []
    try:
        return json.loads(_INGESTION_LOG.read_text(encoding="utf-8"))
    except Exception:
        return []
