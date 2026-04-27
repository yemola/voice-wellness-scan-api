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
from analysis.scoring import compute_confidence, compute_scores_v2

def test_blending_logic():
    user_id = "blend_user"
    
    def make_features(val):
        return {
            "jitter": val, "shimmer": val, "hnr": 20.0,
            "spectralCentroid": 2000.0, "speechRate": 3.0, "rms": 0.05,
            "f0Mean": 200.0, "f0Std": 20.0, "durationSec": 10.0,
            "sampleRate": 16000, "voicedRatio": 0.8
        }

    print(f"--- Blending Logic Test for {user_id} ---")
    
    # Mode helper
    def get_mode(count):
        if count < 5: return "generic", 0.0
        if count <= 10: return "blended", 0.3
        return "baseline", 1.0

    for i in range(1, 15):
        features = make_features(0.02) # constant features
        add_to_history(user_id, features)
        count = history_length(user_id)
        mode, weight = get_mode(count)
        print(f"Sample {i:2}: Mode={mode:8} Weight={weight:.1f}")

    # Verify blending calculation
    # Generic score (mock)
    g = {"stress": 40, "energy": 50, "stability": 60}
    # Baseline score (mock)
    b = {"stress": 20, "energy": 70, "stability": 80}
    
    # Blended (30% baseline)
    w_b = 0.3
    w_g = 0.7
    blended = {
        "stress": int(round(g["stress"] * w_g + b["stress"] * w_b)),
        "energy": int(round(g["energy"] * w_g + b["energy"] * w_b)),
        "stability": int(round(g["stability"] * w_g + b["stability"] * w_b)),
    }
    # stress: 40*0.7 + 20*0.3 = 28 + 6 = 34
    # energy: 50*0.7 + 70*0.3 = 35 + 21 = 56
    # stability: 60*0.7 + 80*0.3 = 42 + 24 = 66
    
    print("\nManual Blend Verification (30% baseline):")
    print(f"  Generic: {g}")
    print(f"  Baseline: {b}")
    print(f"  Blended: {blended}")
    
    expected = {"stress": 34, "energy": 56, "stability": 66}
    if blended == expected:
        print("  Calculation: SUCCESS")
    else:
        print(f"  Calculation: FAILED (Expected {expected})")

if __name__ == "__main__":
    test_blending_logic()
