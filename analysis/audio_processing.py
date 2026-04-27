import numpy as np
import io
import soundfile as sf

def decode_wav(buf: bytes):
    # Decode 16-bit PCM mono WAV
    # Using soundfile for reliability, but checking if we need manual decoding
    # like the TS version if soundfile behaves differently.
    # The TS version handles numChannels and bitsPerSample specifically.
    data, sample_rate = sf.read(io.BytesIO(buf))
    # If it's multi-channel, the TS version averages them: sum / numChannels
    if len(data.shape) > 1:
        data = np.mean(data, axis=1)
    return data.astype(np.float32), sample_rate

def rms(a, start=0, end=None):
    if end is None:
        end = len(a)
    sub = a[start:end]
    if len(sub) == 0:
        return 0
    return np.sqrt(np.mean(sub**2))

def frame_samples(samples, frame_len, hop):
    # Replicating the TS frame function:
    # for (let i = 0; i + frameLen <= samples.length; i += hop) {
    #   frames.push(samples.subarray(i, i + frameLen));
    # }
    frames = []
    for i in range(0, len(samples) - frame_len + 1, hop):
        frames.append(samples[i : i + frame_len])
    return frames

def spectral_centroid(frame, sample_rate):
    N = len(frame)
    # Hann window
    # const w = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (N - 1));
    window = 0.5 - 0.5 * np.cos((2 * np.pi * np.arange(N)) / (N - 1))
    win_frame = frame * window
    
    # TS implementation uses a manual DFT loop for k = 1 to N/2 - 1
    # This matches the positive frequencies of the DFT, skipping DC.
    # We can use np.fft.rfft(win_frame) which is much faster.
    
    fft_res = np.fft.rfft(win_frame)
    magnitudes = np.abs(fft_res)
    
    # k = 1 to K-1 where K = N >> 1
    K = N >> 1
    # frequencies = (k * sampleRate) / N
    freqs = np.fft.rfftfreq(N, d=1/sample_rate)
    
    # The TS code: for (let k = 1; k < K; k++)
    # k=1 is the second element, K is N/2.
    # If N is 640 (40ms at 16k), K is 320.
    # np.fft.rfft(N=640) returns 321 elements (0 to 320).
    # So k < 320 means we take indices 1 to 319.
    
    mags_subset = magnitudes[1:K]
    freqs_subset = freqs[1:K]
    
    num = np.sum(freqs_subset * mags_subset)
    den = np.sum(mags_subset)
    
    return num / den if den > 0 else 0
