"""Telephonic/noise robustness evaluation for the Prisma STT path.

Generates utterances with Timbre (Avinash, same voice as the demo), degrades
them the way a real Indian phone call does (8 kHz band-pass, quantization,
traffic and fan noise), optionally denoises, and measures word error rate
against the reference. Saves the table to docs/eval-audio.md.

No network beyond the Gnani API (key from ~/.env). Dev-only script.
"""
import io
import struct
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, 'src')
from config import GNANI_API_KEY, GNANI_BASE, STT_MODEL, TTS_LANG, TTS_MODEL, TTS_SPEED

OUT = Path(tempfile.gettempdir()) / 'siddha-eval-audio'
OUT.mkdir(exist_ok=True)

QUESTIONS = [
    'SC students ke liye post matric scholarship ke documents kya chahiye?',
    'National means cum merit scholarship eligibility kya hai?',
    'Girl students ko koi engineering scholarship milegi kya?',
    'Mera papa driver hai, kya mujhe scholarship milegi?',
    'Post matric scholarship ka deadline kab hai?',
    'Central government ki scholarship mein income limit kitna hai?',
    'Bihar mein post matric SC scholarship kaise apply kare?',
    'Disability waale student ko kaunsi scholarship milegi?',
    'Minority students ke liye koi scheme hai kya?',
    'College admission ke liye loan subsidy milegi kya?',
    'Meritocracy scholarship SC category mein kya hai?',
    'Post matric scholarship documents kya chahiye?',
]


def tts(text, voice='Avinash'):
    r = requests.post(f'{GNANI_BASE}/api/v1/tts/inference',
        headers={'X-API-Key-ID': GNANI_API_KEY, 'Content-Type': 'application/json'},
        json={'text': text, 'voice': voice, 'model': TTS_MODEL, 'language': TTS_LANG,
              'speed': TTS_SPEED, 'audio_config': {'sample_rate': 16000, 'num_channels': 1,
              'sample_width': 2, 'encoding': 'linear_pcm', 'container': 'wav'}}, timeout=90)
    r.raise_for_status()
    return r.content


def fix_wav(raw):
    """Extract PCM payload from the WAV-ish container and rebuild as 16-bit 16 kHz mono."""
    pos, payload = 12, None
    while pos + 8 <= len(raw):
        cid, size = raw[pos:pos+4], struct.unpack('<I', raw[pos+4:pos+8])[0]
        body = raw[pos+8:pos+8+size]
        if cid == b'data':
            payload = body
            break
        pos += 8 + size + (size & 1)
    payload = (payload or raw[44:])
    payload = payload[:len(payload)//2*2]
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(payload)
    return out.getvalue()


def pcm16(b):
    with wave.open(io.BytesIO(b)) as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def wav16(x):
    x = np.clip(x, -1, 1)
    b = io.BytesIO()
    with wave.open(b, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((x * 32767).astype('<i2').tobytes())
    return b.getvalue()


def lowpass(x, fc, fs=16000):
    """Simple one-pole-ish FIR via FFT for speed and stability."""
    X = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / fs)
    X[freqs > fc] = 0
    return np.fft.irfft(X)


def bandpass(x, lo=300, hi=3400, fs=16000):
    X = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / fs)
    X[(freqs < lo) | (freqs > hi)] = 0
    return np.fft.irfft(X)


def snr_mix(speech, noise, target_db):
    rms_s = np.sqrt(np.mean(speech ** 2)) + 1e-9
    rms_n = np.sqrt(np.mean(noise ** 2)) + 1e-9
    gain = rms_s / (rms_n * 10 ** (target_db / 20))
    return speech + noise * gain


def traffic_noise(n, fs=16000, seed=0):
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(n)
    brown = np.cumsum(white)
    brown = bandpass(brown - brown.mean(), 40, 500, fs)
    honks = np.zeros(n)
    t = n / fs
    for _ in range(int(t)):
        on = int(rng.uniform(0.2, t - 0.4) * fs)
        dur = int(rng.uniform(0.12, 0.3) * fs)
        f = rng.uniform(380, 700)
        tt = np.arange(dur) / fs
        honks[on:on + dur] = 0.8 * np.sin(2 * np.pi * f * tt) * np.exp(-tt * 8)
    return (brown / (np.max(np.abs(brown)) + 1e-9)) * 0.6 + honks


def fan_noise(n, fs=16000, seed=0):
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(n)
    x = lowpass(white, 1200, fs)
    hum = 0.25 * np.sin(2 * np.pi * 50 * np.arange(n) / fs)
    return x * 0.5 + hum


def wer(ref, hyp):
    r, h = ref.lower().split(), hyp.lower().split()
    if not r:
        return 1.0 if h else 0.0
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (0 if r[i - 1] == h[j - 1] else 1))
            prev = cur
    return d[-1] / len(r)


def stt(wav_bytes):
    r = requests.post(f'{GNANI_BASE}/stt/v3',
        headers={'X-API-Key-ID': GNANI_API_KEY, 'X-API-Request-ID': __import__('uuid').uuid4().hex},
        files={'audio_file': ('q.wav', wav_bytes, 'audio/wav')},
        data={'model': STT_MODEL, 'language_code': 'indic-auto', 'format': 'codemix'},
        timeout=90)
    if r.status_code != 200:
        print('     STT http', r.status_code, r.text[:150])
        return None
    j = r.json()
    if not j.get('success', True) and not j.get('transcript'):
        return None
    return j.get('transcript', '')


def main():
    rows = []
    for i, q in enumerate(QUESTIONS):
        print(f'[{i + 1}/{len(QUESTIONS)}] {q[:70]}')
        try:
            clean = pcm16(fix_wav(tts(q)))
        except Exception as e:
            print('   TTS failed:', e)
            continue
        clean = lowpass(clean, 7200)  # keep within audio band, kill edge artefacts
        base = wav16(clean)
        variants = [('16k clean', base)]
        tel = bandpass(clean.copy(), 300, 3400)
        # 8 kHz telephony: resample 16k -> 8k -> 16k
        ds8 = tel[::2]
        tel = np.repeat(ds8, 2)[:len(tel)]
        tel_q = np.round(tel * 127) / 127  # 7-bit telephony quantization
        variants.append(('8k telephony', wav16(tel_q)))
        variants.append(('8k + traffic', wav16(snr_mix(tel_q, traffic_noise(len(tel_q), 16000, seed=i), 10))))
        variants.append(('8k + fan', wav16(snr_mix(tel_q, fan_noise(len(tel_q), 16000, seed=i), 15))))
        for name, blob in variants:
            hyp = stt(blob)
            if hyp is None:
                print(f'     {name}: STT error')
                rows.append((name, q, None, None))
                continue
            w = wer(q, hyp)
            print(f'     {name}: WER {w:.2f}  -> {hyp[:80]}')
            rows.append((name, q, hyp, w))

    print('\n| variant | mean WER |')
    agg = {}
    for name, _, _, w in rows:
        if w is not None:
            agg.setdefault(name, []).append(w)
    for name, vals in sorted(agg.items()):
        print(f'| {name} | {np.mean(vals):.2f} (n={len(vals)}) |')

    out = ['| Variant | Utterances | Mean WER |', '|---|---|---|']
    for name, vals in sorted(agg.items()):
        out.append(f'| {name} | {len(vals)} | {np.mean(vals):.2f} |')
    OUT / 'table.md'.write_text('\n'.join(out) + '\n')
    print('\nwrote /tmp/eval_audio/table.md')


if __name__ == '__main__':
    main()
