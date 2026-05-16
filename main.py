import os
import uuid

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from analysis.report_generator import generate_pdf_report

from analysis.audio_processing import decode_wav
from analysis.features import extract_features
from analysis.scoring import compute_scores_v2, compute_scores_v3, build_summary, build_tips, compute_confidence
from analysis.logger import get_logger, DEBUG_ENABLED
from analysis.baseline import (
    add_to_history,
    get_or_compute_baseline,
    apply_baseline,
    history_length,
)

_log = get_logger("main")

def _resolve_tone(stress: int, energy: int) -> str:
    """Helper to re-calculate emotional tone from blended scores."""
    if stress > 75: return "tense"
    if stress > 55: return "slightly tense"
    if stress < 35 and energy > 60: return "engaged"
    if stress < 35 and energy < 45: return "calm"
    if energy < 40: return "low energy"
    return "balanced"

app = FastAPI(title="Vocera Voice Wellness API")

# Enable CORS for all origins (frontend compatibility)
# CORS — allow all origins by default; restrict via ALLOWED_ORIGINS env var (comma-separated)
_allowed = os.environ.get("ALLOWED_ORIGINS", "*")
_origins = [o.strip() for o in _allowed.split(",")] if _allowed != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False if _origins == ["*"] else True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup():
    status = "ENABLED" if DEBUG_ENABLED else "DISABLED"
    print(f"[voice-api] Debug logging is {status}. "
          f"Set DEBUG=True in your environment to enable it.")


@app.get("/")
async def root():
    return {"status": "ok", "message": "Voice Wellness Analysis API (Python)"}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/api/analyze-voice")
async def analyze_voice_v3(request: Request):
    """
    Advanced voice analysis endpoint (v3).
    Implements deterministic scoring, gating, and global normalization.
    """
    req_id = uuid.uuid4().hex[:8]
    tag = f"[{req_id}]"
    _log.debug("%s ══ NEW V3 REQUEST ═══════════════════════════", tag)

    user_id = request.headers.get("X-User-ID") or None
    context = request.headers.get("X-Context") or None
    
    body = await request.body()
    if len(body) < 8000:
        raise HTTPException(status_code=400, detail="Recording too small")

    try:
        # 1. Decode & Extract
        samples, sample_rate = decode_wav(body)
        features = extract_features(samples, sample_rate)
        
        # 2. Gating Logic
        rms = features["rms"]
        flatness = features["spectralFlatness"]
        hnr = features["hnr"]
        
        status = "ok"
        confidence = "high"
        
        # 🔇 Insufficient Signal
        if rms < 0.005:
            return {
                "status": "low_confidence",
                "message": "Audio too quiet for reliable analysis",
                "confidence": "low",
                "raw_features": features
            }
            
        # 🌫️ Noisy Environment
        if flatness > 0.15:
            status = "noisy_environment"
            confidence = "low"
            
        # 🤫 Whisper Detection
        whisper_mode = (rms < 0.015 and hnr < 10)
        
        # 3. Baseline & Personalization
        baseline_applied = False
        relative_feedback = ""
        scoring_features = features
        
        if user_id:
            add_to_history(user_id, features, context=context)
            samples_recorded = history_length(user_id)
            baseline, baseline_source = get_or_compute_baseline(user_id, context=context)
            
            if baseline:
                # Calculate relative feedback for Pitch Stability (or Jitter)
                # "Your pitch variability is 15% higher than your baseline."
                curr_jitter = features["jitter"]
                base_jitter = baseline["jitter"]
                if base_jitter > 0:
                    diff = (curr_jitter - base_jitter) / base_jitter * 100
                    direction = "higher" if diff > 0 else "lower"
                    relative_feedback = f"Your vocal jitter is {abs(diff):.0f}% {direction} than your baseline."
                
                # For v2/v3, we use global normalization for features, 
                # but we could still use baseline-adjusted features for scoring if requested.
                # The prompt says: "Phase 1: Global normalization only. Phase 2: User baseline."
                # I'll implement Phase 2 if a baseline exists.
                if samples_recorded > 5:
                    scoring_features = apply_baseline(features, baseline)
                    baseline_applied = True

        # 4. Scoring
        scores = compute_scores_v3(scoring_features, request_id=req_id, whisper_mode=whisper_mode)
        summary = build_summary(scores)
        tips = build_tips(scores)
        
        # 5. Response
        response = {
            "status": status,
            "scores": scores,
            "insight": summary,
            "summary": summary, # backward compatibility
            "tips": tips,
            "relative_feedback": relative_feedback,
            "confidence": confidence,
            "raw_features": features,
            "disclaimer": "This provides general wellness insights and is not a medical diagnosis."
        }
        
        if whisper_mode:
            response["mode"] = "whisper"
            
        return response

    except Exception as exc:
        _log.error("%s   ERROR: %s", tag, exc)
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/analyze")
async def analyze(request: Request):
    # Short ID to group all log lines for this request together
    req_id = uuid.uuid4().hex[:8]
    tag = f"[{req_id}]"

    _log.debug("%s ══ NEW REQUEST ══════════════════════════════", tag)

    # ── Optional per-user context (passed as a request header) ──────────
    user_id: str | None = request.headers.get("X-User-ID") or None
    context: str | None = request.headers.get("X-Context") or None
    _log.debug("%s   user_id=%r  context=%r", tag, user_id, context)

    # ── Size guards ────────────────────────────────────────────────────────
    body = await request.body()
    body_kb = len(body) / 1024
    _log.debug("%s   body_size=%.1f KB", tag, body_kb)

    if len(body) < 8000:
        raise HTTPException(status_code=400, detail="Recording too small")
    if len(body) > 5_000_000:
        raise HTTPException(status_code=413, detail="Recording too large")

    try:
        # ── Decode ─────────────────────────────────────────────────────────
        samples, sample_rate = decode_wav(body)
        duration_sec = len(samples) / sample_rate

        _log.debug(
            "%s   decoded: sample_rate=%d Hz  duration=%.2f s  samples=%d",
            tag, sample_rate, duration_sec, len(samples),
        )

        if duration_sec < 2:
            raise HTTPException(
                status_code=400,
                detail="Recording is too short. Please speak for at least 5 seconds.",
            )

        # ── Feature extraction ─────────────────────────────────────────────
        features = extract_features(samples, sample_rate)

        _log.debug(
            "%s ── RAW EXTRACTED FEATURES ─────────────────────\n"
            "%s   durationSec=%.2f  sampleRate=%d  rms=%.4f\n"
            "%s   voicedRatio=%.3f  f0Mean=%.1f Hz  f0Std=%.2f Hz\n"
            "%s   jitter=%.5f  shimmer=%.5f  hnr=%.2f dB\n"
            "%s   spectralCentroid=%.1f Hz  speechRate=%.2f syl/s",
            tag,
            tag, features["durationSec"], features["sampleRate"], features["rms"],
            tag, features["voicedRatio"],  features["f0Mean"],    features["f0Std"],
            tag, features["jitter"],       features["shimmer"],   features["hnr"],
            tag, features["spectralCentroid"],                    features["speechRate"],
        )

        if features["voicedRatio"] < 0.1:
            raise HTTPException(
                status_code=400,
                detail="We couldn't detect enough voice. Please record again in a quiet environment.",
            )

        # ── Adaptive baseline calibration (optional) ───────────────────────
        baseline_applied = False
        samples_recorded = 0
        scoring_features = features          # default: use raw features

        if user_id:
            # Store this reading first so it counts toward the baseline
            add_to_history(user_id, features, context=context)
            samples_recorded = history_length(user_id)
            context_samples  = history_length(user_id, context=context) if context else 0

            # Returns (baseline, source)
            # source is "context", "global", or "none"
            baseline, baseline_source = get_or_compute_baseline(user_id, context=context)

            if baseline is not None:
                # PIPELINE: features → baseline → adjusted_features (deviations)
                scoring_features = apply_baseline(features, baseline)
                baseline_applied = True
                _log.debug(
                    "%s   baseline applied for user=%r  mode=%s  samples=%d",
                    tag, user_id, baseline_source, (context_samples if baseline_source == "context" else samples_recorded),
                )
            else:
                _log.debug(
                    "%s   baseline skipped — insufficient history",
                    tag,
                )

        # ── Scoring Pipeline (with Soft Fallback) ──────────────────────────
        generic_scores = compute_scores_v2(features, request_id=f"{req_id}-G")
        
        # Determine mode and blend weight
        # < 5:  0% baseline
        # 5-10: 30% baseline
        # > 10: 100% baseline
        mode = "generic"
        weight_baseline = 0.0
        
        if baseline_applied:
            if samples_recorded > 10:
                mode = "baseline"
                weight_baseline = 1.0
            else:
                mode = "blended"
                weight_baseline = 0.3
                
        if weight_baseline == 0.0:
            scores = generic_scores
        elif weight_baseline == 1.0:
            scores = compute_scores_v2(scoring_features, request_id=f"{req_id}-B")
        else:
            # BLENDED MODE
            baseline_scores = compute_scores_v2(scoring_features, request_id=f"{req_id}-B")
            weight_generic = 1.0 - weight_baseline
            
            scores = {
                "stress":    int(round(generic_scores["stress"] * weight_generic + baseline_scores["stress"] * weight_baseline)),
                "energy":    int(round(generic_scores["energy"] * weight_generic + baseline_scores["energy"] * weight_baseline)),
                "stability": int(round(generic_scores["stability"] * weight_generic + baseline_scores["stability"] * weight_baseline)),
            }
            # Re-calculate tone from blended metrics
            scores["emotional_tone"] = _resolve_tone(scores["stress"], scores["energy"])

        summary    = build_summary(scores)
        tips       = build_tips(scores)
        confidence = compute_confidence(features)

        _log.debug("%s ══ REQUEST COMPLETE ════════════════════════════", tag)

        # ── Response ───────────────────────────────────────────────────────
        response = {
            "features":   features,   # always raw, unmodified features
            "scores":     scores,
            "summary":    summary,
            "tips":       tips,
            "confidence": confidence,
        }

        # Calibration block is only added when a user_id was supplied
        if user_id:
            response["calibration"] = {
                "user_id":              user_id,
                "context":              context,
                "mode":                 mode,
                "baseline_source":      baseline_source if baseline_applied else "none",
                "weight_baseline":      weight_baseline,
                "samples_recorded":     samples_recorded,
                "context_samples":      context_samples if context else 0,
                "min_samples_required": 5,
            }

        return response

    except HTTPException:
        raise
    except Exception as exc:
        _log.debug("%s   ERROR during analysis: %s", tag, exc)
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/generate-report")
@app.post("/api/generate-report/")
async def generate_report(request: Request):
    """
    Generate a PDF report based on analysis results provided in the request body.
    """
    try:
        data = await request.json()
        pdf_bytes = generate_pdf_report(data)
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=voice-wellness-report.pdf"
            }
        )
    except Exception as exc:
        _log.error(f"Error generating report: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
