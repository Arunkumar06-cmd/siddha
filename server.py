"""Siddha — routes layer (Gnani 2026). Business logic lives in src/pipeline.py.
NFR: specs/NFR.md — rate limit, circuit breakers, typed errors, no secrets logged."""
import base64
import collections
import os
import pathlib
import re
import secrets
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent / 'src'))

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import conversation
import reqid
import retriever
import stats
import timing
from config import GNANI_API_KEY, logger
from pipeline import (
    FFMPEG_BIN,
    MAX_AUDIO_BYTES,
    STT_BREAKER,
    TTS_BREAKER,
    rag_answer,
    speakable,
    synthesize,
    to_wav,
    transcribe,
)
from version import VERSION

BASE_DIR = pathlib.Path(__file__).parent
RATE_LIMIT = int(os.getenv('SIDDHA_RATE_LIMIT', '30'))
_metrics = collections.Counter()
_lock = threading.Lock()
_ip_calls = collections.defaultdict(list)
_ip_lock = threading.Lock()

# A session id is a bearer secret: whoever holds it can read the last turn and reset the
# conversation. 32+ URL-safe characters (>= 128 bits when minted by the server, 122 for a
# browser randomUUID) makes guessing another visitor's session infeasible. An 8-character,
# client-chosen id such as "12345678" was guessable.
SID_RE = re.compile(r'^[A-Za-z0-9_-]{32,80}$')

app = FastAPI(title='Siddha', version=VERSION, docs_url=None, redoc_url=None)
STATIC = pathlib.Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')

_IP_TABLE_SOFT_CAP = 10_000


def _evict_idle_ips(now: float):
    """Drop clients with no call in the last minute so the table cannot grow without bound."""
    for ip in [k for k, v in _ip_calls.items() if not v or now - v[-1] >= 60]:
        del _ip_calls[ip]


def _rate_limit(ip: str):
    now = time.time()
    with _ip_lock:
        if len(_ip_calls) > _IP_TABLE_SOFT_CAP:
            _evict_idle_ips(now)
        calls = [t for t in _ip_calls[ip] if now - t < 60]
        if len(calls) >= RATE_LIMIT:
            _ip_calls[ip] = calls
            raise HTTPException(429, f'Too many requests — max {RATE_LIMIT} per minute')
        calls.append(now)
        _ip_calls[ip] = calls

@app.middleware('http')
async def _global(request: Request, call_next):
    # One correlation id per request: logged on every line, returned to the caller and
    # sent to Gnani. A well-formed inbound X-Request-ID is kept so a client can trace it.
    rid = reqid.accept_or_new(request.headers.get('x-request-id'))
    reqid.set_current(rid)
    request.state.request_id = rid
    timings = timing.begin()
    t_start = time.perf_counter()
    id_header = {'X-Request-ID': rid}
    # /api/health is the container healthcheck: it must never spend a client's quota.
    if request.url.path.startswith('/api') and request.url.path != '/api/health':
        try:
            _rate_limit(request.client.host if request.client else 'anon')
        except HTTPException as e:
            logger.warning('rate_limited ip=%s', request.client.host if request.client else 'anon')
            return JSONResponse(status_code=e.status_code, content={'error': e.detail}, headers=id_header)
    response = await call_next(request)
    if request.url.path.startswith('/api/ask'):
        total = time.perf_counter() - t_start
        timing.record('total', total)
        timings['total'] = total
        logger.info('timing path=%s status=%s %s', request.url.path, response.status_code,
                    timing.server_timing(timings))
    st = timing.server_timing(timings)
    if response.status_code == 422:
        return JSONResponse(status_code=422, headers={**id_header, **({'Server-Timing': st} if st else {})},
                            content={'error': 'Invalid request — check audio/upload size and fields'})
    response.headers['X-Request-ID'] = rid
    if st:
        response.headers['Server-Timing'] = st
    return response

@app.exception_handler(HTTPException)
async def _http_err(request: Request, exc: HTTPException):
    logger.warning('http_error path=%s status=%s detail=%s', request.url.path, exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={'error': exc.detail})

@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    # Runs outside the middleware stack, so restore the id from request.state.
    rid = getattr(request.state, 'request_id', None)
    if rid:
        reqid.set_current(rid)
    logger.exception('unhandled path=%s err=%s', request.url.path, exc)
    return JSONResponse(status_code=500, content={'error': 'Internal error'},
                        headers={'X-Request-ID': rid} if rid else None)

@app.get('/')
def index():
    return FileResponse(STATIC / 'index.html', headers={'Cache-Control': 'no-cache'})

@app.get('/api/health')
def health():
    missing = [
        name for name, present in (
            ('corpus', (BASE_DIR / 'data/scholarships.jsonl').exists()),
            ('index', (BASE_DIR / 'data/scholarships.faiss').exists()),
            ('api_key', bool(GNANI_API_KEY)),
            ('ffmpeg', bool(FFMPEG_BIN)),
        ) if not present
    ]
    if missing:
        raise HTTPException(503, f'Health check failed: missing {", ".join(missing)}')
    return {'status': 'ok', 'version': VERSION}


@app.get('/api/ready')
def ready():
    """Readiness: the model and index are in memory, so the first real turn will not
    pay a multi-second load. /api/health stays a pure liveness probe."""
    not_ready = [name for name, ok in (
        ('model_and_index', retriever.is_loaded()),
        ('ffmpeg', bool(FFMPEG_BIN)),
    ) if not ok]
    if not_ready:
        return JSONResponse(status_code=503, content={'status': 'not_ready', 'waiting_for': not_ready,
                                                       'version': VERSION})
    return {'status': 'ready', 'version': VERSION}

@app.get('/api/metrics')
def metrics():
    snap = stats.snapshot()
    return {'counters': snap['counters'], 'quality': snap,
            'stt_circuit': STT_BREAKER.state(),
            'tts_circuit': TTS_BREAKER.state(), 'rate_limit_per_min': RATE_LIMIT,
            'stage_seconds': timing.snapshot()}

@app.get('/metrics')
def prometheus_metrics():
    return PlainTextResponse(stats.prometheus() + timing.prometheus(),
                             media_type='text/plain; version=0.0.4')

_count = stats.count

def _session_id(value: str | None):
    if not value:
        return None
    if not SID_RE.match(value):
        raise HTTPException(400, 'Invalid session id')
    return value


@app.post('/api/session')
def session_new():
    """Mint an unguessable session id (192 random bits, 32 URL-safe characters)."""
    return {'session_id': secrets.token_urlsafe(24)}

class TextQuery(BaseModel):
    text: str = Field(min_length=2, max_length=500)
    session_id: str | None = Field(default=None, max_length=80)
    speak: bool = True

def _speak_or_none(reply: str):
    try:
        return base64.b64encode(synthesize(reply)).decode()
    except HTTPException:
        _count('tts_degraded')
        return None


def _audio_fields(reply: str):
    """Audio plus a flag telling the client when the voice covers only the first part of the text."""
    audio = _speak_or_none(reply)
    truncated = bool(audio) and speakable(reply)[1]
    return {'audio_wav_b64': audio, 'audio_truncated': truncated}

@app.post('/api/ask_text')
def ask_text(q: TextQuery):
    sid = _session_id(q.session_id)
    reply, sources, meta = rag_answer(q.text, sid)
    _count('rag_answered')
    audio = _audio_fields(reply) if q.speak else {'audio_wav_b64': None, 'audio_truncated': False}
    return {'transcript': q.text, 'reply': reply, 'sources': sources,
            'session_id': sid, **meta, **audio}

@app.get('/api/session/{session_id}')
def session_state(session_id: str):
    session_id = _session_id(session_id)
    last = conversation.STORE.last(session_id)
    if last is None:
        return {'session_id': session_id, 'turn': None}
    return {'session_id': session_id, 'turn': {
        'transcript': last.query, 'reply': last.reply, 'sources': last.sources,
        'context_used': last.context_used, 'context_name': last.context_name,
    }}

@app.delete('/api/session/{session_id}')
def session_reset(session_id: str):
    session_id = _session_id(session_id)
    conversation.STORE.reset(session_id)
    return {'session_id': session_id, 'reset': True}

@app.post('/api/ask_audio')
def ask_audio(audio: UploadFile = File(...), session_id: str = Form('')):
    # A plain `def` route: FastAPI runs it in the threadpool. ffmpeg, the provider
    # calls and the embedding model are all blocking, and as `async def` any one
    # slow turn would have frozen every other request, /api/health included.
    sid = _session_id(session_id)  # reject a bad id before any STT credit is spent
    raw = audio.file.read(MAX_AUDIO_BYTES + 1)
    if len(raw) > MAX_AUDIO_BYTES:
        raise HTTPException(413, 'Audio too large (max 8 MB)')
    suffix = pathlib.Path(audio.filename or 'q.webm').suffix or '.webm'
    suffix = suffix if suffix in {'.webm', '.wav', '.mp3', '.ogg', '.m4a', '.flac', '.aac'} else '.webm'
    wav = to_wav(raw, suffix)
    query, lang = transcribe(wav)
    if not query.strip():
        return {'transcript': '', 'reply': 'Suno, awaaz samajh nahi aayi. Thodi der phir se kahein.',
                'detected_language_code': lang, 'sources': [], 'audio_wav_b64': None,
                'audio_truncated': False, 'session_id': sid, 'follow_up': False,
                'context_used': False, 'context_name': None}
    reply, sources, meta = rag_answer(query, sid)
    _count('rag_answered')
    return {'transcript': query, 'reply': reply, 'detected_language_code': lang,
            'sources': sources, 'session_id': sid, **meta, **_audio_fields(reply)}
