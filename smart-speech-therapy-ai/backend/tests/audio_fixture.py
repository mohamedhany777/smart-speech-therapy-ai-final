"""Generate a real (synthetic but valid) WAV audio file for tests, so the
audio analysis tests exercise real librosa signal processing rather than a
mocked file."""
import io
import wave

import numpy as np


def make_wav_bytes(duration_seconds: float = 2.0, sample_rate: int = 16000, freq_hz: float = 150.0) -> bytes:
    """A simple sine wave with a bit of amplitude modulation (so it isn't
    perfectly silent per our own silence heuristic) — a real waveform, not
    a mock object standing in for one."""
    t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 1.0 * t)  # slow envelope to create "pause-like" dips
    signal = 0.3 * envelope * np.sin(2 * np.pi * freq_hz * t)
    pcm = (signal * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()
