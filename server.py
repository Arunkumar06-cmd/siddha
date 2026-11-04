"""Siddha — routes layer (Gnani 2026). Business logic lives in src/pipeline.py.
NFR: specs/NFR.md — rate limit, circuit breakers, typed errors, no secrets logged."""
import base64
import collections
import os
import pathlib
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent / 'src'))

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import GNANI_API_KEY, logger
from pipeline import (
    FFMPEG_BIN,
    STT_BREAKER,
    TTS_BREAKER,
    rag_answer,
    synthesize,
    to_wav,
    transcribe,
)

BASE_DIR = pathlib.Path(__file__).parent
RATE_LIMIT = int(os.getenv('SIDDHA_RATE_LIMIT', '30'))
_metrics = collections.Counter()
_lock = threading.Lock()
_ip_calls = collections.defaultdict(list)
_ip_lock = threading.Lock()

app = FastAPI(title='Siddha', version='2.2.0', docs_url=None, redoc_url=None)
STATIC = pathlib.Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')

def _rate_limit(ip: str):
    now = time.time()
    with _ip_lock:
        calls = [t for t in _ip_calls[ip] if now - t < 60]
        if len(calls) >= RATE_LIMIT:
            _ip_calls[ip] = calls
            raise HTTPException(429, f'Too many requests — max {RATE_LIMIT} per minute')
        calls.append(now)
        _ip_calls[ip] = calls

@app.middleware('http')
async def _global(request: Request, call_next):
    if request.url.path.startswith('/api'):
        try:
            _rate_limit(request.client.host if request.client else 'anon')
        except HTTPException as e:
            logger.warning('rate_limited ip=%s', request.client.host if request.client else 'anon')
            return JSONResponse(status_code=e.status_code, content={'error': e.detail})
    response = await call_next(request)
    if response.status_code == 422:
        return JSONResponse(status_code=422, content={'error': 'Invalid request — check audio/upload size and fields'})
    return response

@app.exception_handler(HTTPException)
async def _http_err(request: Request, exc: HTTPException):
    logger.warning('http_error path=%s status=%s detail=%s', request.url.path, exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={'error': exc.detail})

@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    logger.exception('unhandled path=%s err=%s', request.url.path, exc)
    return JSONResponse(status_code=500, content={'error': 'Internal error'})

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
    return {'status': 'ok', 'version': '2.2.0'}

@app.get('/api/metrics')
def metrics():
    with _lock:
        snap = dict(_metrics)
    return {'counters': snap, 'stt_circuit': STT_BREAKER.state(),
            'tts_circuit': TTS_BREAKER.state(), 'rate_limit_per_min': RATE_LIMIT}

def _count(key, n=1):
    with _lock:
        _metrics[key] += n

class TextQuery(BaseModel):
    text: str = Field(min_length=2, max_length=500)

def _speak_or_none(reply: str):
    try:
        return base64.b64encode(synthesize(reply)).decode()
    except HTTPException:
        _count('tts_degraded')
        return None

@app.post('/api/ask_text')
def ask_text(q: TextQuery):
    reply, sources = rag_answer(q.text)
    _count('rag_answered')
    return {'transcript': q.text, 'reply': reply, 'sources': sources,
            'audio_wav_b64': _speak_or_none(reply)}

@app.post('/api/ask_audio')
async def ask_audio(audio: UploadFile = File(...)):
    raw = await audio.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(413, 'Audio too large (max 8 MB)')
    suffix = pathlib.Path(audio.filename or 'q.webm').suffix or '.webm'
    suffix = suffix if suffix in {'.webm', '.wav', '.mp3', '.ogg', '.m4a', '.flac', '.aac'} else '.webm'
    wav = to_wav(raw, suffix)
    query, lang = transcribe(wav)
    if not query.strip():
        return {'transcript': '', 'reply': 'Suno, awaaz samajh nahi aayi. Thodi der phir se kahein.',
                'detected_language_code': lang, 'sources': [], 'audio_wav_b64': None}
    reply, sources = rag_answer(query)
    _count('rag_answered')
    return {'transcript': query, 'reply': reply, 'detected_language_code': lang,
            'sources': sources, 'audio_wav_b64': _speak_or_none(reply)}
