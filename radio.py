"""
Radio voice - makes JARVIS sound like he's talking through an earpiece / comms channel.

How (3 small steps on the sound itself):
  1. Decode the MP3 into raw sound samples (numbers between -1 and 1).
  2. Band-pass: keep only the middle frequencies (like a radio or phone line).
     Very deep bass and very bright treble are removed.
  3. A little "drive" (soft clipping) adds the slightly crunchy, electronic edge.
     Then a faint hiss, and we turn it back into an MP3.

The numbers in SETTINGS control how strong the effect is.
"""

from pathlib import Path

import lameenc
import miniaudio
import numpy as np

# "Light" - picked by ear on the Home Mini (medium: 300/3800/2.2/0.004/0.85, strong: 400/3200/3.5/0.008/1.0)
SETTINGS = {
    "low_cut_hz": 200,    # remove sound below this (bass)
    "high_cut_hz": 5000,  # remove sound above this (treble)
    "drive": 1.5,         # 1 = clean; higher = more crunchy
    "hiss": 0.002,        # background noise level; 0 = none
    "mix": 0.6,           # 1 = full radio; 0 = original voice
}


def _band_pass(samples: np.ndarray, rate: int, low: float, high: float) -> np.ndarray:
    """Remove frequencies outside [low, high] using an FFT (split sound into frequencies,
    zero the ones we don't want, put it back together). Edges are softened to avoid ringing."""
    spectrum = np.fft.rfft(samples)
    freqs = np.fft.rfftfreq(len(samples), 1 / rate)
    gain = np.clip((freqs - low * 0.7) / (low * 0.3), 0, 1) * np.clip((high * 1.25 - freqs) / (high * 0.25), 0, 1)
    return np.fft.irfft(spectrum * gain, n=len(samples))


def make_radio(mp3: Path, settings: dict = SETTINGS) -> None:
    """Rewrite mp3 in place with the radio effect."""
    decoded = miniaudio.decode_file(str(mp3), output_format=miniaudio.SampleFormat.FLOAT32, nchannels=1)
    rate = decoded.sample_rate
    clean = np.frombuffer(decoded.samples, dtype=np.float32).astype(np.float64)
    if clean.size == 0:
        return

    radio = _band_pass(clean, rate, settings["low_cut_hz"], settings["high_cut_hz"])
    peak = np.max(np.abs(radio)) or 1.0
    radio = np.tanh(radio / peak * settings["drive"]) / np.tanh(settings["drive"])  # soft clip
    radio += np.random.default_rng(0).normal(0, settings["hiss"], radio.size) * (np.abs(clean) > 0.002)

    mix = settings["mix"]
    out = mix * radio + (1 - mix) * clean / (np.max(np.abs(clean)) or 1.0)
    out = out / (np.max(np.abs(out)) or 1.0) * 0.9  # leave some headroom
    pcm = (out * 32767).astype(np.int16).tobytes()

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(48)
    encoder.set_in_sample_rate(rate)
    encoder.set_channels(1)
    encoder.set_quality(2)
    mp3.write_bytes(encoder.encode(pcm) + encoder.flush())
