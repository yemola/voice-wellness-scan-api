import numpy as np
from .audio_processing import rms, frame_samples, spectral_centroid
from .utils import mean, std

def estimate_f0(frame, sample_rate):
    min_lag = int(sample_rate / 400) # 400 Hz max
    max_lag = int(sample_rate / 70)  # 70 Hz min
    N = len(frame)
    
    e = rms(frame)
    if e < 0.01:
        return 0
    
    r0 = np.sum(frame * frame)
    if r0 <= 0:
        return 0
    
    best_lag = -1
    best_val = 0
    
    # Replicating the loop exactly for deterministic output
    for lag in range(min_lag, min(max_lag + 1, N)):
        # sum += frame[i] * frame[i + lag]
        # This can be vectorized with np.dot or np.sum
        sum_val = np.sum(frame[:N-lag] * frame[lag:])
        norm = sum_val / r0
        if norm > best_val:
            best_val = norm
            best_lag = lag
            
    if best_lag < 0 or best_val < 0.3:
        return 0
    return sample_rate / best_lag

def spectral_flatness(frame):
    """
    Compute spectral flatness: Geometric Mean / Arithmetic Mean of power spectrum.
    Higher values (> 0.1) indicate noisier signal.
    """
    # Use real FFT
    p = np.abs(np.fft.rfft(frame))**2
    if np.sum(p) <= 0:
        return 0.0
    # Add epsilon to avoid log(0)
    p = p + 1e-12
    g_mean = np.exp(np.mean(np.log(p)))
    a_mean = np.mean(p)
    return float(g_mean / a_mean)

def jitter_local(periods):
    if len(periods) < 3:
        return 0
    diff = 0
    for i in range(1, len(periods)):
        diff += abs(periods[i] - periods[i-1])
    m = mean(periods)
    return diff / (len(periods) - 1) / m if m > 0 else 0

def shimmer_local(amps):
    if len(amps) < 3:
        return 0
    diff = 0
    for i in range(1, len(amps)):
        diff += abs(amps[i] - amps[i-1])
    m = mean(amps)
    return diff / (len(amps) - 1) / m if m > 0 else 0

def hnr_from_autocorr(r_peak_normalized):
    r = max(0.001, min(0.999, r_peak_normalized))
    return 10 * np.log10(r / (1 - r))

def estimate_speech_rate(samples, sample_rate, duration_sec):
    frame_len = int(sample_rate * 0.02) # 20ms
    hop = frame_len
    env = []
    for i in range(0, len(samples) - frame_len + 1, hop):
        env.append(rms(samples, i, i + frame_len))
        
    if not env:
        return 0
        
    # Smooth (moving average, ~80ms)
    w = 4
    sm = [0] * len(env)
    for i in range(len(env)):
        start = max(0, i - w)
        end = min(len(env) - 1, i + w)
        sm[i] = mean(env[start : end + 1])
        
    m = mean(sm)
    threshold = m * 1.2
    
    peaks = 0
    last_peak = -1000
    min_dist = 6
    for i in range(1, len(sm) - 1):
        if sm[i] > threshold and sm[i] > sm[i-1] and sm[i] >= sm[i+1] and (i - last_peak) > min_dist:
            peaks += 1
            last_peak = i
            
    return peaks / duration_sec if duration_sec > 0 else 0

def extract_features(samples, sample_rate):
    duration_sec = len(samples) / sample_rate
    frame_len = int(sample_rate * 0.04) # 40ms
    hop = int(sample_rate * 0.02)      # 20ms
    frames = frame_samples(samples, frame_len, hop)
    
    f0s = []
    periods = []
    amps = []
    centroids = []
    acorr_peaks = []
    flatness_values = []
    voiced_frames = 0
    
    for f in frames:
        flatness_values.append(spectral_flatness(f))
        f0 = estimate_f0(f, sample_rate)
        if f0 > 0:
            voiced_frames += 1
            f0s.append(f0)
            periods.append(1 / f0)
            amps.append(rms(f))
            
            # Re-derive normalized autocorr peak at lag for HNR
            lag = int(round(sample_rate / f0))
            r0 = np.sum(f * f)
            if r0 > 0:
                # sum += f[i] * f[i + lag]
                rl = np.sum(f[:len(f)-lag] * f[lag:])
                rn = rl / r0
            else:
                rn = 0
            acorr_peaks.append(max(0, rn))
            centroids.append(spectral_centroid(f, sample_rate))
            
    f0_mean = mean(f0s)
    f0_std = std(f0s)
    
    # Pitch stability in semitones
    if len(f0s) > 1:
        semitones = [12 * np.log2(f / 440.0) for f in f0s]
        f0_semitone_std = std(semitones)
    else:
        f0_semitone_std = 0.0
        
    j = jitter_local(periods)
    sh = shimmer_local(amps)
    hnr = hnr_from_autocorr(mean(acorr_peaks)) if acorr_peaks else 0
    sc = mean(centroids)
    sf = mean(flatness_values) if flatness_values else 0
    speech_rate = estimate_speech_rate(samples, sample_rate, duration_sec)
    
    return {
        "durationSec": float(duration_sec),
        "sampleRate": int(sample_rate),
        "rms": float(rms(samples)),
        "voicedRatio": float(voiced_frames / len(frames)) if frames else 0.0,
        "f0Mean": float(f0_mean),
        "f0Std": float(f0_std),
        "f0SemitoneStd": float(f0_semitone_std),
        "jitter": float(j),
        "shimmer": float(sh),
        "hnr": float(hnr),
        "spectralCentroid": float(sc),
        "spectralFlatness": float(sf),
        "speechRate": float(speech_rate)
    }
