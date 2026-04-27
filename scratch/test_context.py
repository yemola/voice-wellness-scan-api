import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

from analysis.baseline import (
    add_to_history,
    get_or_compute_baseline,
    history_length
)

def test_context_logic():
    user_id = "context_user"
    
    def make_features(val):
        return {
            "jitter": val, "shimmer": val, "hnr": 20.0,
            "spectralCentroid": 2000.0, "speechRate": 3.0, "rms": 0.05,
            "f0Mean": 200.0, "f0Std": 20.0, "durationSec": 10.0,
            "sampleRate": 16000, "voicedRatio": 0.8
        }

    print(f"--- Context-Aware Logic Test for {user_id} ---")
    
    # 1. Add 3 samples with context "work"
    for i in range(3):
        add_to_history(user_id, make_features(0.01), context="work")
    
    print(f"Added 3 'work' samples.")
    baseline, source = get_or_compute_baseline(user_id, context="work")
    print(f"  Request context='work' -> Source: {source} (Expected: none - only 3 samples)")

    # 2. Add 2 more samples with context "rest" (Total 5: 3 work, 2 rest)
    for i in range(2):
        add_to_history(user_id, make_features(0.05), context="rest")
    
    print(f"Added 2 'rest' samples (Total 5).")
    baseline, source = get_or_compute_baseline(user_id, context="work")
    print(f"  Request context='work' -> Source: {source} (Expected: global - work only has 3, but global has 5)")
    
    # 3. Add 2 more samples with context "work" (Total 7: 5 work, 2 rest)
    for i in range(2):
        add_to_history(user_id, make_features(0.01), context="work")
        
    print(f"Added 2 more 'work' samples (Total 7, work=5).")
    baseline, source = get_or_compute_baseline(user_id, context="work")
    print(f"  Request context='work' -> Source: {source} (Expected: context - work now has 5)")
    if baseline and abs(baseline["jitter"] - 0.01) < 1e-6:
        print("  Context median: SUCCESS")
    else:
        print(f"  Context median: FAILED (Got {baseline})")

    # 4. Request unknown context
    baseline, source = get_or_compute_baseline(user_id, context="meeting")
    print(f"  Request context='meeting' -> Source: {source} (Expected: global - meeting has 0, but global has 7)")

if __name__ == "__main__":
    test_context_logic()
