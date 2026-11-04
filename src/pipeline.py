"""Siddha pipeline: mic -> ffmpeg -> Prisma STT -> RAG -> Timbre TTS.
All external calls: timeout -> retry(backoff+jitter) -> circuit breaker -> typed error."""
import contextlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import requests
from fastapi import HTTPException

import responder
import retriever
from config import (
    GNANI_API_KEY,
    GNANI_BASE,
    STT_MODEL,
    TTS_LANG,
    TTS_MODEL,
    TTS_SPEED,
    TTS_VOICE,
    logger,
)
from resilience import CircuitBreaker, retry
from spoken import render

MAX_AUDIO_BYTES = 8 * 1024 * 1024     # 8 MB ~ 50 s opus
MAX_TTS_CHARS = 600                    # Timbre input cap (voice-safe length)
MAX_WAV_SECONDS = 30                   # Prisma hard limit

# Resolved once at import: a missing decoder is a deployment fault, not a
# per-request surprise. The route layer turns it into a typed 503.
FFMPEG_BIN = shutil.which('ffmpeg')
if not FFMPEG_BIN:
    logger.error('ffmpeg_not_found: audio uploads will fail with 503 until it is installed')

STT_BREAKER = CircuitBreaker('stt', threshold=5, cooldown_s=60)
TTS_BREAKER = CircuitBreaker('tts', threshold=5, cooldown_s=60)

def to_wav(raw: bytes, suffix: str) -> pathlib.Path:
    """Decode to 16 kHz mono WAV for Prisma; always remove the source temp file."""
    if not FFMPEG_BIN:
        raise HTTPException(503, 'Audio decoding unavailable on this server')
    f_src = None
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(raw)
        f_src = f.name
    dst = f_src + '.wav'
    try:
        subprocess.run(  # noqa: S603 - FFMPEG_BIN is an absolute which-resolved path
            [FFMPEG_BIN, '-y', '-loglevel', 'error', '-i', f_src,
             '-ar', '16000', '-ac', '1', dst],
            check=True, timeout=20, shell=False)
        return pathlib.Path(dst)
    except subprocess.CalledProcessError as e:
        logger.warning('ffmpeg_decode_failed src=%s', f_src)
        raise HTTPException(415, 'Could not decode audio. Use WAV/MP3/OGG/M4A.') from e
    except subprocess.TimeoutExpired as e:
        raise HTTPException(408, 'Audio decode timed out') from e
    finally:
        with contextlib.suppress(OSError):
            os.unlink(f_src)

def _retryable(exc: Exception) -> bool:
    return isinstance(exc, (requests.Timeout, requests.ConnectionError))

def transcribe(wav: pathlib.Path):
    """STT via Prisma v3.0 (indic-auto, codemix).

    Deletes the wav on completion. On any failure, records the circuit-breaker
    failure and raises a typed HTTPException — never a raw provider exception."""
    if not STT_BREAKER.allow():
        raise HTTPException(502, 'Transcription service temporarily unavailable (circuit open)')
    t0 = time.time()
    try:
        with open(wav, 'rb') as f:
            def call():
                r = requests.post(f'{GNANI_BASE}/stt/v3',
                    headers={'X-API-Key-ID': GNANI_API_KEY, 'X-API-Request-ID': uuid.uuid4().hex},
                    files={'audio_file': ('q.wav', f, 'audio/wav')},
                    data={'model': STT_MODEL, 'language_code': 'indic-auto', 'format': 'codemix'},
                    timeout=60)
                if r.status_code >= 500:
                    # turn transient 5xx into a retryable signal; never count 4xx as failures to retry
                    raise requests.ConnectionError(f'server {r.status_code}')
                return r

            r = retry(call, attempts=2, retryable=_retryable)
        logger.info('stt_call status=%s latency_s=%.2f', r.status_code, time.time() - t0)
        if r.status_code != 200:
            logger.error('stt_failed status=%s body=%s', r.status_code, r.text[:200])
            raise HTTPException(502, 'Transcription service unavailable')
        j = r.json()
        if not j.get('success'):
            logger.error('stt_unsuccessful body=%s', r.text[:200])
            raise HTTPException(502, 'Transcription failed')
        STT_BREAKER.record_success()
        return j.get('transcript', ''), j.get('detected_language_code', 'unknown')
    except HTTPException:
        STT_BREAKER.record_failure()
        raise
    except Exception as e:
        # every provider failure must trip the breaker
        STT_BREAKER.record_failure()
        logger.exception('stt_exc err=%s', e)
        raise HTTPException(502, 'Transcription service unavailable') from e
    finally:
        with contextlib.suppress(OSError):
            os.unlink(wav)

def synthesize(text: str):
    """TTS via Timbre (voice-safe rendering, input capped).

    On any failure, records the circuit-breaker failure and raises a typed
    HTTPException — the route layer degrades to text-only replies."""
    if not TTS_BREAKER.allow():
        raise HTTPException(502, 'Voice synthesis temporarily unavailable (circuit open)')
    capped = render(text, use_tags=True)[:MAX_TTS_CHARS]
    t0 = time.time()
    try:
        def call():
            r = requests.post(f'{GNANI_BASE}/api/v1/tts/inference',
                headers={'X-API-Key-ID': GNANI_API_KEY, 'Content-Type': 'application/json'},
                json={'text': capped, 'voice': TTS_VOICE, 'model': TTS_MODEL,
                      'language': TTS_LANG, 'speed': TTS_SPEED,
                      'audio_config': {'sample_rate': 16000, 'num_channels': 1,
                                       'sample_width': 2, 'encoding': 'linear_pcm',
                                       'container': 'wav'}},
                timeout=90)
            if r.status_code >= 500:
                raise requests.ConnectionError(f'server {r.status_code}')
            return r

        r = retry(call, attempts=2, retryable=_retryable)
        logger.info('tts_call status=%s latency_s=%.2f chars=%d', r.status_code, time.time() - t0, len(capped))
        if r.status_code != 200:
            logger.error('tts_failed status=%s body=%s', r.status_code, r.text[:300])
            raise HTTPException(502, 'Voice synthesis unavailable')
        TTS_BREAKER.record_success()
        return r.content
    except HTTPException:
        TTS_BREAKER.record_failure()
        raise
    except Exception as e:
        # every provider failure must trip the breaker
        TTS_BREAKER.record_failure()
        logger.exception('tts_exc err=%s', e)
        raise HTTPException(502, 'Voice synthesis unavailable') from e

def rag_answer(query: str):
    """Retrieval + grounded composition; logs the top match for observability."""
    t0 = time.time()
    hits = retriever.search(query, k=5)
    reply, sources, is_canned = responder.answer(query, hits)
    logger.info('rag_answer hits=%d latency_s=%.2f canned=%s', len(hits), time.time() - t0, is_canned)
    return reply, sources
