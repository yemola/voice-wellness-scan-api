import math
from .utils import clamp, lerp
from .logger import get_logger

_log = get_logger("scoring")


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _clean(value, default=0.0):
    """Convert value to a safe float: handles None, NaN, and non-numeric types."""
    try:
        v = float(value)
        return default if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError):
        return float(default)


def _resolve(f, *keys, default=0.0):
    """
    Look up the first matching key (supports camelCase and snake_case aliases).
    Returns a clean float, falling back to `default` if all keys are missing/bad.
    """
    for key in keys:
        if key in f and f[key] is not None:
            return _clean(f[key], default)
    return float(default)


def safe_div(a, b, default=0.0):
    """Division that never raises ZeroDivisionError."""
    return float(a) / float(b) if b != 0 else default


def normalize(value, low, high):
    """Map a value linearly into [0, 1], clamped at both ends."""
    if high == low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def compress(x, factor=0.7):
    """Power-law compression — reduces sensitivity at extremes."""
    x = max(0.0, x)          # guard against tiny negatives from float arithmetic
    return x ** factor


def _iclamp(value, lo, hi):
    """Return value clamped to [lo, hi] as a native Python int (not numpy)."""
    return int(max(lo, min(hi, value)))


# ---------------------------------------------------------------------------
# Global Normalization Config (p5 - p95)
# ---------------------------------------------------------------------------
GLOBAL_PERCENTILES = {
    "jitter":           (0.005, 0.05),
    "shimmer":          (0.03,  0.20),
    "hnr":              (5.0,   30.0),
    "speechRate":       (1.0,   6.0),
    "f0SemitoneStd":    (0.5,   6.0),
    "spectralCentroid": (800,   4000),
    "rms":              (0.005, 0.25),
    "spectralFlatness": (0.01,  0.20),
}

def normalize_global(value, feature_name):
    """Map a value to [0, 1] using global p5-p95 percentiles."""
    p5, p95 = GLOBAL_PERCENTILES.get(feature_name, (0.0, 1.0))
    if p95 == p5:
        return 0.0
    return max(0.0, min(1.0, (value - p5) / (p95 - p5)))


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def compute_scores_v2(f, *, request_id: str = "-"):
    """
    Compute stress / energy / stability scores from an audio feature dict.

    Accepts both camelCase and snake_case key names, and is fully defensive
    against missing, None, or NaN values.

    Parameters
    ----------
    f          : dict of audio features
    request_id : optional string used to group log lines per request

    Returns
    -------
    dict with keys: stress (int 10-90), energy (int 10-90),
                    stability (int 10-95), emotional_tone (str)
    """
    tag = f"[{request_id}]"

    # ------------------------------------------------------------------
    # 1. Safely resolve all inputs (camelCase + snake_case aliases)
    # ------------------------------------------------------------------
    jitter   = _resolve(f, "jitter",           default=0.02)
    shimmer  = _resolve(f, "shimmer",          default=0.08)
    hnr      = _resolve(f, "hnr",              default=15.0)
    centroid = _resolve(f, "spectralCentroid", "spectral_centroid", default=2000.0)
    rate     = _resolve(f, "speechRate",       "speech_rate",       default=3.0)
    rms      = _resolve(f, "rms",              default=0.05)
    f0_mean  = _resolve(f, "f0Mean",           "f0_mean",           default=1.0)
    f0_std   = _resolve(f, "f0Std",            "f0_std",            default=0.0)

    _log.debug(
        "%s ── RAW FEATURES ─────────────────────────\n"
        "%s   jitter=%.5f  shimmer=%.5f  hnr=%.2f dB\n"
        "%s   centroid=%.1f Hz  rate=%.2f syl/s  rms=%.4f\n"
        "%s   f0_mean=%.1f Hz   f0_std=%.2f Hz",
        tag, tag, jitter, shimmer, hnr,
        tag, centroid, rate, rms,
        tag, f0_mean, f0_std,
    )

    # ------------------------------------------------------------------
    # 2. Normalise into [0, 1] over realistic human-voice ranges
    # ------------------------------------------------------------------
    jitter_n    = normalize(jitter,   0.005, 0.08)
    shimmer_n   = normalize(shimmer,  0.03,  0.30)
    hnr_n       = normalize(hnr,      5.0,   35.0)
    centroid_n  = normalize(centroid, 800,   4000)
    rate_n      = normalize(rate,     1.0,   6.0)
    rms_n       = normalize(rms,      0.005, 0.25)

    pitch_cv    = safe_div(f0_std, f0_mean, default=0.1)
    pitch_var_n = normalize(pitch_cv, 0.03,  0.30)

    _log.debug(
        "%s ── NORMALISED (0-1) ──────────────────────\n"
        "%s   jitter_n=%.3f  shimmer_n=%.3f  hnr_n=%.3f\n"
        "%s   centroid_n=%.3f  rate_n=%.3f  rms_n=%.3f\n"
        "%s   pitch_cv=%.4f  pitch_var_n=%.3f",
        tag, tag, jitter_n, shimmer_n, hnr_n,
        tag, centroid_n, rate_n, rms_n,
        tag, pitch_cv, pitch_var_n,
    )

    # ------------------------------------------------------------------
    # 3. Power-law compression (prevents runaway 100s)
    # ------------------------------------------------------------------
    jitter_n    = compress(jitter_n)
    shimmer_n   = compress(shimmer_n)
    pitch_var_n = compress(pitch_var_n)

    _log.debug(
        "%s ── COMPRESSED (post power-law) ───────────\n"
        "%s   jitter_n=%.3f  shimmer_n=%.3f  pitch_var_n=%.3f",
        tag, tag, jitter_n, shimmer_n, pitch_var_n,
    )

    # ------------------------------------------------------------------
    # 4. Stress  (high jitter/shimmer/pitch-variance + low HNR → higher)
    # ------------------------------------------------------------------
    stress_raw = (
        jitter_n    * 0.30 +
        shimmer_n   * 0.20 +
        (1 - hnr_n) * 0.30 +
        pitch_var_n * 0.20
    )
    stress = _iclamp(stress_raw * 100, 10, 90)

    # ------------------------------------------------------------------
    # 5. Energy  (speech rate + spectral brightness + loudness)
    # ------------------------------------------------------------------
    energy_raw = (
        rate_n     * 0.40 +
        centroid_n * 0.30 +
        rms_n      * 0.30
    )
    energy = _iclamp(energy_raw * 100, 10, 90)

    # ------------------------------------------------------------------
    # 6. Stability  (low pitch variance → higher stability)
    # ------------------------------------------------------------------
    stability_raw = 1.0 - pitch_var_n
    stability = _iclamp(stability_raw * 100, 10, 95)

    # ------------------------------------------------------------------
    # 7. Emotional tone label
    # ------------------------------------------------------------------
    if stress > 75:
        tone = "tense"
    elif stress > 55:
        tone = "slightly tense"
    elif stress < 35 and energy > 60:
        tone = "engaged"
    elif stress < 35 and energy < 45:
        tone = "calm"
    elif energy < 40:
        tone = "low energy"
    else:
        tone = "balanced"

    _log.debug(
        "%s ── FINAL SCORES ──────────────────────────\n"
        "%s   stress=%d  energy=%d  stability=%d\n"
        "%s   stress_raw=%.4f  energy_raw=%.4f  stability_raw=%.4f\n"
        "%s   emotional_tone=%r",
        tag, tag, stress, energy, stability,
        tag, stress_raw, energy_raw, stability_raw,
        tag, tone,
    )

    return {
        "stress":         stress,
        "energy":         energy,
        "stability":      stability,
        "emotional_tone": tone,
    }


def compute_scores_v3(f, *, request_id: str = "-", whisper_mode: bool = False):
    """
    Compute scores using the deterministic weighted formula (v3).
    
    Formula:
    stress_raw = (0.20 * jitter_n + 0.20 * shimmer_n + 0.30 * (1 - hnr_n) + 
                  0.20 * (1 - pitch_stability) + 0.10 * speech_rate_n)
    """
    tag = f"[{request_id}]"

    # 1. Resolve inputs
    jitter   = _resolve(f, "jitter",           default=0.02)
    shimmer  = _resolve(f, "shimmer",          default=0.08)
    hnr      = _resolve(f, "hnr",              default=15.0)
    rate     = _resolve(f, "speechRate",       default=3.0)
    centroid = _resolve(f, "spectralCentroid", default=2000.0)
    rms      = _resolve(f, "rms",              default=0.05)
    f0_s_std = _resolve(f, "f0SemitoneStd",    default=2.0)

    # 2. Normalize (Global)
    jitter_n      = normalize_global(jitter,   "jitter")
    shimmer_n     = normalize_global(shimmer,  "shimmer")
    hnr_n         = normalize_global(hnr,      "hnr")
    rate_n        = normalize_global(rate,     "speechRate")
    centroid_n    = normalize_global(centroid, "spectralCentroid")
    rms_n         = normalize_global(rms,      "rms")
    
    # Pitch Stability: 1 - min(f0_semitone_std / threshold, 1.0)
    # Calibrated threshold: 6 semitones
    pitch_stability = 1.0 - min(f0_s_std / 6.0, 1.0)

    _log.debug(
        "%s ── NORMALISED (v3) ──────────────────────\n"
        "%s   jitter_n=%.3f  shimmer_n=%.3f  hnr_n=%.3f\n"
        "%s   rate_n=%.3f    stability=%.3f",
        tag, tag, jitter_n, shimmer_n, hnr_n,
        tag, rate_n, pitch_stability,
    )

    # 3. Stress Scoring Model
    # stress_raw = 0.20*jitter_n + 0.20*shimmer_n + 0.30*(1-hnr_n) + 0.20*(1-stability) + 0.10*rate_n
    stress_raw = (
        0.20 * jitter_n +
        0.20 * shimmer_n +
        0.30 * (1.0 - hnr_n) +
        0.20 * (1.0 - pitch_stability) +
        0.10 * rate_n
    )
    
    # Whisper override: reduce stress weighting
    if whisper_mode:
        stress_raw *= 0.6  # Reduce by 40%
        _log.debug("%s   whisper mode detected — scaling stress", tag)

    stress = _iclamp(stress_raw * 100, 10, 90)

    # 4. Energy (speech rate + centroid + loudness)
    energy_raw = (rate_n * 0.40 + centroid_n * 0.30 + rms_n * 0.30)
    energy = _iclamp(energy_raw * 100, 10, 90)

    # 5. Stability (direct pitch stability)
    stability = _iclamp(pitch_stability * 100, 10, 95)

    tone = _resolve_tone(stress, energy)

    return {
        "stress":         stress,
        "energy":         energy,
        "stability":      stability,
        "emotional_tone": tone,
    }

def _resolve_tone(stress, energy):
    if stress > 75: return "tense"
    if stress > 55: return "slightly tense"
    if stress < 35 and energy > 60: return "engaged"
    if stress < 35 and energy < 45: return "calm"
    if energy < 40: return "low energy"
    return "balanced"

# Update alias to use v3
def compute_scores(f, *, request_id: str = "-", whisper_mode: bool = False):
    return compute_scores_v3(f, request_id=request_id, whisper_mode=whisper_mode)


# ---------------------------------------------------------------------------
# Confidence helper
# ---------------------------------------------------------------------------

def compute_confidence(f):
    """
    Return a confidence label based on voice quality metrics.
    - Low:  Very weak signal, slow rate, or high noise.
    - High: Strong signal, clear speech rate, and high HNR.
    - Medium: Otherwise.
    """
    rms  = _resolve(f, "rms",        default=0.0)
    rate = _resolve(f, "speechRate", "speech_rate", default=0.0)
    hnr  = _resolve(f, "hnr",        default=0.0)

    # Low confidence if any metric is below critical thresholds
    if rms < 0.005 or rate < 0.5 or hnr < 3:
        return "low"

    # High confidence if all metrics are strong
    if rms >= 0.05 and rate >= 2.0 and hnr >= 18:
        return "high"

    return "medium"


# ---------------------------------------------------------------------------
# Presentation helpers (unchanged API)
# ---------------------------------------------------------------------------

def band(n):
    if n <= 40:
        return "balanced"
    if n <= 70:
        return "moderate"
    return "elevated"


def build_summary(scores):
    parts = [
        f"Your voice shows {band(scores['stress'])} stress with "
        f"{'strong' if scores['energy'] >= 60 else 'steady' if scores['energy'] >= 40 else 'low'} "
        "energy levels."
    ]
    if scores['stability'] >= 60:
        parts.append("There is noticeable variability in stability, which can reflect mental load or fatigue.")
    else:
        parts.append("Your vocal stability looks consistent.")
    parts.append(f"Overall, your tone reads as {scores['emotional_tone']}.")
    return " ".join(parts)


def build_tips(scores):
    tips = []
    if scores['stress'] >= 60:
        tips.append("Take a 2-5 minute slow-breathing break (4s in, 6s out).")
    if scores['energy'] < 45:
        tips.append("Hydrate and try a 5-minute walk to lift your energy.")
    if scores['stability'] >= 60:
        tips.append("Pause for a brief mindful reset before the next task.")
    if scores['energy'] >= 70 and scores['stress'] < 40:
        tips.append("Channel this momentum into your most demanding task next.")
    if not tips:
        tips.append("Maintain your routine - your voice signals are well-balanced.")
    return tips[:3]
