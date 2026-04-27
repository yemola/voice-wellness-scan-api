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
from analysis.scoring import compute_confidence

def test_baseline_logic():
    user_id = "test_user_123"
    
    # Mock features
    def make_features(val):
        return {
            "jitter": val,
            "shimmer": val,
            "hnr": 20.0,
            "spectralCentroid": 2000.0,
            "speechRate": 3.0,
            "rms": 0.05,
            "f0Mean": 200.0,
            "f0Std": 20.0,
            "durationSec": 10.0,
            "sampleRate": 16000,
            "voicedRatio": 0.8
        }

    print(f"--- Starting test for user: {user_id} ---")
    
    # 1. Add 4 samples
    for i in range(1, 5):
        features = make_features(0.01 * i)
        add_to_history(user_id, features)
        print(f"Added sample {i}: jitter={features['jitter']}")
        
        baseline = get_or_compute_baseline(user_id)
        if baseline is None:
            print(f"  Samples: {history_length(user_id)} | Baseline: NONE (Correct)")
        else:
            print(f"  Samples: {history_length(user_id)} | Baseline: FAILED")
            return

    # 2. Add 5th sample
    features_5 = make_features(0.05)
    add_to_history(user_id, features_5)
    print(f"Added sample 5: jitter={features_5['jitter']}")
    
    baseline = get_or_compute_baseline(user_id)
    if baseline is not None:
        print(f"  Samples: {history_length(user_id)} | Baseline: {baseline['jitter']} (Correct)")
        if abs(baseline['jitter'] - 0.03) < 1e-6:
            print("  Median check: SUCCESS")
    
    # 3. Apply baseline
    current = make_features(0.07)
    adjusted = apply_baseline(current, baseline)
    print(f"Applying baseline to jitter=0.07 -> Adjusted: {adjusted['jitter']} (Expected 0.04)")

    # 4. Check None handling
    def make_sample(j_val):
        s = make_features(0.01)
        s["jitter"] = j_val
        return s

    history_with_none = [
        make_sample(0.01), make_sample(None), make_sample(0.02),
        make_sample("invalid"), make_sample(0.03), make_sample(0.04),
        make_sample(0.05)
    ]
    print("\nChecking None/invalid handling in compute_baseline...")
    baseline_none = compute_baseline(history_with_none)
    if baseline_none is not None and abs(baseline_none['jitter'] - 0.03) < 1e-6:
        print("  None/Invalid handling: SUCCESS")

    # 5. Check Confidence Scoring
    print("\nChecking Confidence Scoring...")
    
    low_f = make_features(0.01)
    low_f["rms"] = 0.001
    print(f"  RMS=0.001 -> {compute_confidence(low_f)} (Expected: low)")
    
    med_f = make_features(0.01)
    med_f["rms"] = 0.01
    print(f"  RMS=0.01  -> {compute_confidence(med_f)} (Expected: medium)")
    
    high_f = make_features(0.01)
    high_f["rms"] = 0.1
    high_f["speechRate"] = 3.0
    high_f["hnr"] = 25.0
    print(f"  High Qual -> {compute_confidence(high_f)} (Expected: high)")

if __name__ == "__main__":
    test_baseline_logic()
