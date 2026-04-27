import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

from analysis.baseline import (
    add_to_history,
    compute_baseline,
    apply_baseline,
    get_or_compute_baseline,
    history_length
)
from analysis.scoring import compute_confidence, compute_scores_v3

def test_v3_pipeline():
    user_id = "v3_tester"
    
    # Mock features
    def make_features(val):
        return {
            "jitter": val,
            "shimmer": 0.08,
            "hnr": 20.0,
            "spectralCentroid": 2000.0,
            "spectralFlatness": 0.05,
            "speechRate": 3.0,
            "rms": 0.05,
            "f0Mean": 200.0,
            "f0Std": 20.0,
            "f0SemitoneStd": 2.0,
            "durationSec": 10.0,
            "sampleRate": 16000,
            "voicedRatio": 0.8
        }

    print(f"--- V3 Pipeline Test for user: {user_id} ---")
    
    # 1. Baseline activation
    for i in range(1, 6):
        features = make_features(0.01)
        add_to_history(user_id, features)
        baseline, source = get_or_compute_baseline(user_id)
        print(f"Sample {i}: Baseline Source={source}")

    # 2. Scoring (v3)
    features = make_features(0.02)
    scores = compute_scores_v3(features, request_id="TEST-V3")
    print(f"\nScoring Result (v3):")
    for k, v in scores.items():
        print(f"  {k}: {v}")

    # 3. Whisper mode
    whisper_features = make_features(0.01)
    whisper_features["rms"] = 0.01
    whisper_features["hnr"] = 8.0
    scores_w = compute_scores_v3(whisper_features, request_id="TEST-W", whisper_mode=True)
    print(f"\nWhisper Mode Scoring Result:")
    print(f"  Stress (Whisper): {scores_w['stress']}")
    
    scores_nw = compute_scores_v3(whisper_features, request_id="TEST-NW", whisper_mode=False)
    print(f"  Stress (Normal): {scores_nw['stress']}")
    
    if scores_w['stress'] < scores_nw['stress']:
        print("  Whisper reduction: SUCCESS")

if __name__ == "__main__":
    test_v3_pipeline()
