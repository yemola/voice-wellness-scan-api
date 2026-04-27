"""
analysis/baseline.py
---------------------
Adaptive baseline calibration for per-user voice analysis.

Design
------
* In-memory store (dict).  Restart = fresh slate.  Swap for Redis/DB later
  by replacing `_store` operations — all other code stays the same.
* Median is used instead of mean: robust to outlier recordings.
* Requires at least MIN_SAMPLES readings before a baseline is applied.
* Applying the baseline returns *absolute deviations* from the user's
  personal median, so scores reflect "how different are you from your norm"
  rather than a fixed population reference.

Public API
----------
    add_to_history(user_id, features, context=None) -> None
    compute_baseline(history)                       -> dict | None
    apply_baseline(current_features, baseline)      -> dict
    get_or_compute_baseline(user_id, context=None)  -> dict | None
"""

import math
from collections import defaultdict
from threading import Lock

from .logger import get_logger

_log = get_logger("baseline")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MIN_SAMPLES: int = 5          # minimum readings before baseline is trusted
MAX_HISTORY: int = 100        # rolling window per user (oldest dropped first)

# Keys we track for baseline purposes (camelCase — matches extract_features output)
BASELINE_KEYS = (
    "jitter",
    "shimmer",
    "hnr",
    "spectralCentroid",
    "speechRate",
    "rms",
    "f0Mean",
    "f0Std",
)

# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

# { user_id (str) -> [feature_dict, ...] }
_store: dict[str, list[dict]] = defaultdict(list)
_lock = Lock()


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _safe_float(value) -> float | None:
    """Return a clean float or None for missing/None/NaN/Inf values."""
    try:
        v = float(value)
        return None if (math.isnan(v) or math.isinf(v)) else v
    except (TypeError, ValueError):
        return None


def _median(values: list[float]) -> float:
    """Pure-Python median — no external dependencies."""
    clean = sorted(v for v in values if v is not None)
    n = len(clean)
    if n == 0:
        return 0.0
    mid = n // 2
    return clean[mid] if n % 2 else (clean[mid - 1] + clean[mid]) / 2.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_to_history(user_id: str, features: dict, context: str | None = None) -> None:
    """
    Append a feature dict to the user's history, optionally tagged with context.
    Enforces the MAX_HISTORY rolling window (oldest entry dropped).
    Thread-safe.
    """
    record = dict(features)
    if context:
        record["_context"] = context

    with _lock:
        history = _store[user_id]
        history.append(record)
        if len(history) > MAX_HISTORY:
            history.pop(0)
    _log.debug(
        "[baseline] user=%r  context=%r  history_len=%d",
        user_id, context, len(_store[user_id]),
    )


def compute_baseline(history: list[dict]) -> dict | None:
    """
    Compute a per-key median baseline from a list of feature dicts.

    Returns None if fewer than MIN_SAMPLES valid readings exist for
    any tracked key (so the caller can skip baseline adjustment entirely).

    Parameters
    ----------
    history : list of feature dicts (output of extract_features)

    Returns
    -------
    dict mapping each BASELINE_KEY -> median float, or None.
    """
    if len(history) < MIN_SAMPLES:
        _log.debug(
            "[baseline] insufficient history (%d < %d) — skipping",
            len(history), MIN_SAMPLES,
        )
        return None

    baseline = {}
    for key in BASELINE_KEYS:
        values = [_safe_float(sample.get(key)) for sample in history]
        clean_values = [v for v in values if v is not None]
        if len(clean_values) < MIN_SAMPLES:
            _log.debug(
                "[baseline] key=%r has only %d valid values — skipping baseline",
                key, len(clean_values),
            )
            return None   # all keys must meet the threshold
        baseline[key] = _median(clean_values)

    _log.debug("[baseline] computed baseline: %s", baseline)
    return baseline


def apply_baseline(current_features: dict, baseline: dict) -> dict:
    """
    Return a *deviation* feature dict:  abs(current - baseline_median).

    Keys that exist in current_features but not in baseline are passed
    through unchanged (e.g. durationSec, sampleRate, voicedRatio).

    Parameters
    ----------
    current_features : dict output of extract_features
    baseline         : dict output of compute_baseline (must not be None)

    Returns
    -------
    New dict — current_features is not mutated.
    """
    adjusted = dict(current_features)          # shallow copy; all values are scalars
    for key in BASELINE_KEYS:
        if key not in baseline:
            continue
        raw = _safe_float(current_features.get(key))
        if raw is None:
            continue
        adjusted[key] = abs(raw - baseline[key])

    _log.debug("[baseline] adjusted features: %s", {
        k: adjusted[k] for k in BASELINE_KEYS if k in adjusted
    })
    return adjusted


def get_or_compute_baseline(user_id: str, context: str | None = None) -> tuple[dict | None, str]:
    """
    Retrieves this user's history and returns a computed baseline.
    
    Logic:
    1. If context provided, try computing from matching records.
    2. If that fails (or no context), compute from global records.
    
    Returns
    -------
    (baseline_dict or None, source_label ("context", "global", or "none"))
    """
    with _lock:
        history = list(_store.get(user_id, []))
    
    if not history:
        return None, "none"

    # Try context-specific first
    if context:
        context_history = [r for r in history if r.get("_context") == context]
        baseline = compute_baseline(context_history)
        if baseline:
            return baseline, "context"
        _log.debug("[baseline] insufficient context-specific data for %r — falling back", context)

    # Fallback to global
    baseline = compute_baseline(history)
    return baseline, ("global" if baseline else "none")


def history_length(user_id: str, context: str | None = None) -> int:
    """Return how many readings are stored for this user (total or per context)."""
    with _lock:
        history = list(_store.get(user_id, []))
    if context:
        return len([r for r in history if r.get("_context") == context])
    return len(history)
