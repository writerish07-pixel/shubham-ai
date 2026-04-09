"""
sales_intelligence.py — Sales intelligence system for tracking competitor losses.

🔥 SELF-LEARNING ADDED: Tracks and analyzes why customers buy from:
1. Competitor BRANDS (Honda, Bajaj, TVS, etc.) — captures WHY they chose another brand
2. Competitor DEALERS (other Hero dealers) — captures WHY they went to another dealer

Stores structured data for analytics:
- Date, model interested, competitor, loss reason, loss category
- Aggregated insights (top reasons, trending competitors, win-back patterns)

Data is stored in JSON files and also embedded in vector DB for RAG retrieval.
"""
import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

import config_learning as config

log = logging.getLogger("shubham-ai.intelligence")

_file_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Competitor loss logging
# ══════════════════════════════════════════════════════════════════════════════

async def log_competitor_loss(call_sid: str, caller: str,
                               competitor_brand: str, competitor_model: str,
                               loss_reason: str, loss_category: str,
                               interested_model: str, bought_elsewhere: bool):
    """
    🔥 SALES INTELLIGENCE LOGIC: Log a competitive loss event.

    Called by learning_pipeline.py when a customer mentions buying from
    a competitor brand or dealer.

    Args:
        call_sid: Call session ID
        caller: Customer phone number
        competitor_brand: Name of competitor brand (e.g., "honda", "bajaj")
        competitor_model: Specific competitor model (e.g., "Activa 6G")
        loss_reason: Free-text reason for the loss
        loss_category: Categorized reason (price, mileage, brand_trust, etc.)
        interested_model: Hero model the customer was interested in
        bought_elsewhere: True if customer confirmed they bought from competitor
    """
    entry = {
        "call_sid": call_sid,
        "caller": caller,
        "date": time.strftime("%Y-%m-%d"),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "competitor_brand": competitor_brand.lower().strip() if competitor_brand else "unknown",
        "competitor_model": competitor_model.strip() if competitor_model else "unknown",
        "interested_model": interested_model.strip() if interested_model else "unknown",
        "loss_reason": loss_reason.strip() if loss_reason else "",
        "loss_category": loss_category.strip() if loss_category else "other",
        "bought_elsewhere": bought_elsewhere,
        "type": "brand_loss" if _is_competitor_brand(competitor_brand) else "dealer_loss",
    }

    # Save to appropriate file
    if entry["type"] == "brand_loss":
        _append_to_file(config.COMPETITOR_LOSSES_FILE, entry)
        log.info("Logged brand loss: %s → %s (reason: %s)",
                 interested_model, competitor_brand, loss_category)
    else:
        _append_to_file(config.DEALER_LOSSES_FILE, entry)
        log.info("Logged dealer loss: %s (reason: %s)",
                 interested_model, loss_category)

    # Also store in vector DB for RAG
    import memory_learning as memory
    loss_text = (
        f"Customer lost to {competitor_brand} {competitor_model}. "
        f"Was interested in Hero {interested_model}. "
        f"Reason: {loss_reason}. Category: {loss_category}."
    )
    memory.store_learning(loss_text, {
        "type": "competitor_loss",
        "competitor": competitor_brand,
        "model": interested_model,
        "category": loss_category,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    })


def _is_competitor_brand(brand: str) -> bool:
    """Check if the brand is a competitor (vs another Hero dealer)."""
    if not brand:
        return False
    brand_lower = brand.lower().strip()
    return brand_lower in config.COMPETITOR_BRANDS


def _append_to_file(filepath: Path, entry: dict):
    """Thread-safe append to JSON array file."""
    with _file_lock:
        data = []
        if filepath.exists():
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
            except Exception:
                data = []
        data.append(entry)
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Analytics and insights
# ══════════════════════════════════════════════════════════════════════════════

def get_loss_summary() -> dict:
    """
    🔥 SALES INTELLIGENCE LOGIC: Get aggregated loss analytics.

    Returns structured insights:
    - Top competitor brands
    - Top loss reasons
    - Most lost Hero models
    - Trend data
    """
    brand_losses = _load_file(config.COMPETITOR_LOSSES_FILE)
    dealer_losses = _load_file(config.DEALER_LOSSES_FILE)

    # Aggregate competitor brands
    brand_counts: dict[str, int] = {}
    for loss in brand_losses:
        brand = loss.get("competitor_brand", "unknown")
        brand_counts[brand] = brand_counts.get(brand, 0) + 1

    # Aggregate loss categories
    category_counts: dict[str, int] = {}
    for loss in brand_losses + dealer_losses:
        cat = loss.get("loss_category", "other")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Aggregate models lost
    model_counts: dict[str, int] = {}
    for loss in brand_losses + dealer_losses:
        model = loss.get("interested_model", "unknown")
        model_counts[model] = model_counts.get(model, 0) + 1

    # Sort by frequency
    top_competitors = sorted(brand_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_reasons = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_lost_models = sorted(model_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "total_brand_losses": len(brand_losses),
        "total_dealer_losses": len(dealer_losses),
        "top_competitors": [{"brand": b, "count": c} for b, c in top_competitors],
        "top_loss_reasons": [{"reason": r, "count": c} for r, c in top_reasons],
        "top_lost_models": [{"model": m, "count": c} for m, c in top_lost_models],
    }


def get_competitor_insights(brand: str) -> dict:
    """
    🔥 SALES INTELLIGENCE LOGIC: Get detailed insights for a specific competitor.

    Returns:
    - All loss reasons for this competitor
    - Which Hero models are losing to them
    - Common objections when this competitor is mentioned
    """
    brand_lower = brand.lower().strip()
    losses = _load_file(config.COMPETITOR_LOSSES_FILE)
    filtered = [l for l in losses if l.get("competitor_brand", "").lower() == brand_lower]

    if not filtered:
        return {"brand": brand, "total_losses": 0, "reasons": [], "models_lost": []}

    reasons = {}
    models = {}
    for loss in filtered:
        cat = loss.get("loss_category", "other")
        reasons[cat] = reasons.get(cat, 0) + 1
        model = loss.get("interested_model", "unknown")
        models[model] = models.get(model, 0) + 1

    return {
        "brand": brand,
        "total_losses": len(filtered),
        "reasons": sorted(reasons.items(), key=lambda x: x[1], reverse=True),
        "models_lost": sorted(models.items(), key=lambda x: x[1], reverse=True),
        "recent_losses": filtered[-5:],  # last 5 losses
    }


def _load_file(filepath: Path) -> list:
    """Load JSON array from file, return empty list on error."""
    if not filepath.exists():
        return []
    try:
        return json.loads(filepath.read_text(encoding="utf-8"))
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Real-time competitor detection for live calls
# ══════════════════════════════════════════════════════════════════════════════

# 🔥 FIX: Pre-compile word-boundary regex for each competitor brand.
# Plain substring matching caused false positives: "ola" matched "bola"
# (Hindi for "said"), "jawa" matched "jawab" (Hindi for "answer").
import re as _re
_COMPETITOR_BRAND_RE = _re.compile(
    r"\b(?:" + "|".join(_re.escape(b) for b in config.COMPETITOR_BRANDS) + r")\b",
    _re.IGNORECASE,
)


def detect_competitor_mention(text: str) -> Optional[dict]:
    """
    🔥 SALES INTELLIGENCE LOGIC: Detect competitor brand/model mentions in text.

    Uses word-boundary regex — used during live calls for real-time alerts.

    Args:
        text: Customer's spoken text

    Returns:
        {"brand": "honda", "context": "customer comparing with Honda Activa"}
        or None if no competitor detected.
    """
    m = _COMPETITOR_BRAND_RE.search(text)
    if m:
        return {
            "brand": m.group().lower(),
            "context": text[:200],
        }
    return None
