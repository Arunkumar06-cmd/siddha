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

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import requests
from fastapi import HTTPException

import context
import conversation
import reqid
import responder
import retriever
import stats
import timing
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

def sniff_audio(raw: bytes) -> bool:
    """Allow-list of container signatures the browser/mobile recorders produce.

    ffmpeg picks its demuxer from content, not from the file name, so we refuse
    anything that is not recognisably audio before it ever reaches ffmpeg
    (playlist/concat/text demuxers are not something an upload should reach)."""
    head = raw[:16]
    return bool(
        head[:4] == b'\x1aE\xdf\xa3'                         # WebM / Matroska
        or (head[:4] == b'RIFF' and head[8:12] == b'WAVE')    # WAV
        or head[:4] in (b'OggS', b'fLaC')                     # Ogg, FLAC
        or head[:3] == b'ID3'                                 # MP3 with tag
        or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)  # MP3/ADTS sync
        or head[4:8] == b'ftyp'                               # MP4 / M4A (Safari)
    )


def to_wav(raw: bytes, suffix: str) -> pathlib.Path:
    """Decode to 16 kHz mono WAV for Prisma; always remove temp files.

    Input is allow-listed by signature, restricted to the file protocol, stripped
    of non-audio streams and capped at MAX_WAV_SECONDS (Prisma's hard limit)."""
    if not FFMPEG_BIN:
        raise HTTPException(503, 'Audio decoding unavailable on this server')
    if not sniff_audio(raw):
        raise HTTPException(415, 'Unsupported audio. Use WebM, WAV, MP3, OGG, M4A or FLAC.')
    f_src = None
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(raw)
        f_src = f.name
    dst = f_src + '.wav'
    try:
        with timing.stage('ffmpeg'):
            subprocess.run(  # noqa: S603 - FFMPEG_BIN is an absolute which-resolved path
                [FFMPEG_BIN, '-y', '-nostdin', '-loglevel', 'error',
                 '-protocol_whitelist', 'file,pipe', '-i', f_src,
                 '-vn', '-sn', '-dn', '-t', str(MAX_WAV_SECONDS),
                 '-ar', '16000', '-ac', '1', dst],
                check=True, timeout=20, shell=False)
        return pathlib.Path(dst)
    except subprocess.CalledProcessError as e:
        logger.warning('ffmpeg_decode_failed src=%s', f_src)
        with contextlib.suppress(OSError):
            os.unlink(dst)
        raise HTTPException(415, 'Could not decode audio. Use WAV/MP3/OGG/M4A.') from e
    except subprocess.TimeoutExpired as e:
        with contextlib.suppress(OSError):
            os.unlink(dst)
        raise HTTPException(408, 'Audio decode timed out') from e
    finally:
        with contextlib.suppress(OSError):
            os.unlink(f_src)

def _retryable(exc: Exception) -> bool:
    return isinstance(exc, (requests.Timeout, requests.ConnectionError))


def _client_status(code: int) -> int:
    """Map a provider 4xx to what the caller should see. The provider answered,
    so none of these is an outage and none of them trips a circuit breaker."""
    if code in (400, 413, 415, 422):
        return 422
    if code == 429:
        return 503
    return 502


def transcribe(wav: pathlib.Path):
    """STT via Prisma v3.0 (indic-auto, codemix).

    The WAV is deleted on every exit path, including an open circuit. Only
    timeouts, connection errors and 5xx count against the breaker; a 4xx means
    the provider is up and the request was the problem."""
    try:
        # Read before allow(): allow() may claim the single half-open probe slot, and a
        # failure after that point would leave the slot held. Bytes, not a file handle:
        # a retry must resend the whole upload.
        data = wav.read_bytes()
        if not STT_BREAKER.allow():
            raise HTTPException(502, 'Transcription service temporarily unavailable (circuit open)')
        t0 = time.time()

        def call():
            stats.gnani_call('stt')
            r = requests.post(f'{GNANI_BASE}/stt/v3',
                headers={'X-API-Key-ID': GNANI_API_KEY, 'X-API-Request-ID': reqid.upstream('stt')},
                files={'audio_file': ('q.wav', data, 'audio/wav')},
                data={'model': STT_MODEL, 'language_code': 'indic-auto', 'format': 'codemix'},
                timeout=60)
            if r.status_code >= 500:
                raise requests.ConnectionError(f'server {r.status_code}')
            return r

        try:
            with timing.stage('stt'):
                r = retry(call, attempts=2, retryable=_retryable)
            payload = r.json() if r.status_code == 200 else None
        except Exception as e:
            STT_BREAKER.record_failure()
            logger.exception('stt_exc err=%s', e)
            raise HTTPException(502, 'Transcription service unavailable') from e

        logger.info('stt_call status=%s latency_s=%.2f', r.status_code, time.time() - t0)
        STT_BREAKER.record_success()  # the provider answered
        if r.status_code != 200:
            logger.error('stt_failed status=%s body=%s', r.status_code, r.text[:200])
            raise HTTPException(_client_status(r.status_code), 'Transcription service unavailable')
        if not payload.get('success'):
            logger.error('stt_unsuccessful body=%s', str(payload)[:200])
            raise HTTPException(422, 'Could not transcribe this audio')
        return payload.get('transcript', ''), payload.get('detected_language_code', 'unknown')
    finally:
        with contextlib.suppress(OSError):
            os.unlink(wav)


def speakable(text: str):
    """(text sent to Timbre, whether it is shorter than the full reply)."""
    full = render(text, use_tags=True)
    capped = render(text, use_tags=True, max_chars=MAX_TTS_CHARS)
    return capped, len(capped) < len(full)


def synthesize(text: str):
    """TTS via Timbre (voice-safe rendering, cut on sentence boundaries).

    Provider failures (timeouts, connection errors, 5xx) trip the breaker; a 4xx
    does not. Any failure raises a typed HTTPException and the route degrades
    to a text-only reply."""
    if not TTS_BREAKER.allow():
        raise HTTPException(502, 'Voice synthesis temporarily unavailable (circuit open)')
    capped, _ = speakable(text)
    t0 = time.time()

    def call():
        stats.gnani_call('tts')
        r = requests.post(f'{GNANI_BASE}/api/v1/tts/inference',
            headers={'X-API-Key-ID': GNANI_API_KEY, 'Content-Type': 'application/json',
                     'X-API-Request-ID': reqid.upstream('tts')},
            json={'text': capped, 'voice': TTS_VOICE, 'model': TTS_MODEL,
                  'language': TTS_LANG, 'speed': TTS_SPEED,
                  'audio_config': {'sample_rate': 16000, 'num_channels': 1,
                                   'sample_width': 2, 'encoding': 'linear_pcm',
                                   'container': 'wav'}},
            timeout=90)
        if r.status_code >= 500:
            raise requests.ConnectionError(f'server {r.status_code}')
        return r

    try:
        with timing.stage('tts'):
            r = retry(call, attempts=2, retryable=_retryable)
    except Exception as e:
        TTS_BREAKER.record_failure()
        logger.exception('tts_exc err=%s', e)
        raise HTTPException(502, 'Voice synthesis unavailable') from e

    logger.info('tts_call status=%s latency_s=%.2f chars=%d', r.status_code, time.time() - t0, len(capped))
    TTS_BREAKER.record_success()  # the provider answered
    if r.status_code != 200:
        logger.error('tts_failed status=%s body=%s', r.status_code, r.text[:300])
        raise HTTPException(502, 'Voice synthesis unavailable')
    return r.content

ELIGIBILITY_ENABLED = os.getenv('SIDDHA_ELIGIBILITY', '0').strip().lower() not in {'0', 'false', 'off'}

def _scheme_from(sources, hits, focus):
    """The record a turn was built from, for the next follow-up."""
    if focus:
        return focus
    if not sources:
        return None
    name = sources[0].get('name')
    for h in hits:
        if h['record'].get('name') == name:
            return h['record']
    return None


def _remember(session_id, query, reply, scheme, sources, aspects, used, name):
    if not session_id:
        return
    conversation.STORE.record(session_id, conversation.Turn(
        query=query, reply=reply, scheme=scheme, sources=list(sources or []),
        aspects=tuple(aspects), context_used=used, context_name=name,
    ))


def rag_answer(query: str, session_id: str | None = None):
    """Retrieval + composition, with session-scoped follow-up resolution.

    A follow-up that names only an aspect is answered from the scheme already
    on the table. A follow-up with a state/category is re-retrieved with the
    previous scheme as an anchor. A question that names another scheme is
    treated as new. Eligibility intent still goes through the opt-in LLM
    classifier; any failure falls back to the grounded responder.
    """
    t0 = time.time()
    last = conversation.STORE.last(session_id)
    follow = context.is_follow_up(query, last)
    aspects = responder.classify_aspects(query)
    focus = last.scheme if (follow and last and last.scheme and context.is_aspect_only(query)) else None

    if focus:
        hits = [{'record': focus, 'rank_score': 0.0}]
        used, context_name = True, focus['name']
    else:
        search_query = context.rewrite(query, last) if follow else query
        with timing.stage('retrieve'):
            hits = retriever.search(search_query, k=5)
        stats.observe_retrieval(hits)
        used = bool(follow and last and last.scheme and hits
                    and hits[0]['record'].get('id') == last.scheme.get('id'))
        context_name = last.scheme['name'] if used and last else None

    stats.count('turns')
    if used:
        stats.count('context_used')
    if follow:
        stats.count('follow_ups')
    meta = {'follow_up': follow, 'context_used': used, 'context_name': context_name}

    if _eligibility_ready():
        try:
            import eligibility
            if eligibility.intended(query):
                looked = eligibility.advise(query, hits)
                if looked:
                    reply, sources = looked
                    _remember(session_id, query, reply, _scheme_from(sources, hits, focus),
                              sources, aspects, used, context_name)
                    logger.info('rag_answer path=eligibility hits=%d context=%s latency_s=%.2f',
                                len(hits), used, time.time() - t0)
                    return reply, sources, meta
        except Exception:
            logger.exception('eligibility_failed_fallback')

    with timing.stage('respond'):
        reply, sources, is_canned = responder.answer(query, hits, follow_up=used)
    scheme = None if is_canned else _scheme_from(sources, hits, focus)
    if is_canned:
        stats.count('canned_answers')
    _remember(session_id, query, reply, scheme, sources, aspects, used, context_name)
    logger.info('rag_answer hits=%d latency_s=%.2f canned=%s context=%s',
                len(hits), time.time() - t0, is_canned, used)
    return reply, sources, meta

def _eligibility_ready():
    if not ELIGIBILITY_ENABLED:
        return False
    import llm
    return llm.configured()
