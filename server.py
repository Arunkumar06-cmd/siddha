"""Saathi — Production backend (Gnani 2026). NFR: specs/NFR.md.
Budget: 1 turn = 1 STT + 1 TTS call. All external calls:
timeout -> retry(backoff+jitter) -> circuit breaker -> typed error."""
import os, sys, json, base64, tempfile, subprocess, pathlib, time, uuid, threading, collections
sys.path.insert(0, str(pathlib.Path(__file__).parent / 'src'))

import requests
from fastapi import FastAPI, UploadFile, Request, File, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
from config import logger, GNANI_API_KEY, GNANI_BASE, STT_MODEL, TTS_MODEL, TTS_VOICE, TTS_LANG, TTS_SPEED
from resilience import CircuitBreaker, retry, CircuitOpen
import retriever, responder
from spoken import render

MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_TTS_CHARS = 600
STT_BREAKER = CircuitBreaker('stt', threshold=5, cooldown_s=60)
TTS_BREAKER = CircuitBreaker('tts', threshold=5, cooldown_s=60)
RATE_LIMIT = int(os.getenv('SAATHI_RATE_LIMIT', '30'))
_metrics = collections.Counter()
_metrics_lock = threading.Lock()
_ip_calls = collections.defaultdict(list)
_ip_lock = threading.Lock()

app = FastAPI(title='Saathi', version='2.0.0', docs_url=None, redoc_url=None)
STATIC = pathlib.Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')

def _rate_limit(ip: str):
    now = time.time()
    with _ip_lock:
        calls = [t for t in _ip_calls[ip] if now - t < 60]
        if len(calls) >= RATE_LIMIT:
            _ip_calls[ip] = calls
            raise HTTPException(429, 'Too many requests — slow down, max 30 per minute')
        calls.append(now); _ip_calls[ip] = calls

@app.middleware('http')
async def _rate(request: Request, call_next):
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

@app.get('/')
def index():
    return FileResponse(STATIC / 'index.html', headers={'Cache-Control': 'no-cache'})

@app.get('/api/health')
def health():
    ok = all([(pathlib.Path('data/scholarships.jsonl').exists()),
              (pathlib.Path('data/scholarships.faiss').exists()),
              bool(GNANI_API_KEY)])
    if not ok:
        raise HTTPException(503, 'Health check failed: corpus or key missing')
    return {'status': 'ok', 'version': '2.0.0'}

@app.get('/api/metrics')
def metrics():
    with _metrics_lock:
        snap = dict(_metrics)
    return {'counters': snap, 'stt_circuit': STT_BREAKER.state(),
            'tts_circuit': TTS_BREAKER.state(), 'rate_limit_per_min': RATE_LIMIT}

def _count(key, n=1):
    with _metrics_lock:
        _metrics[key] += n

# ---------- pipeline ----------
def to_wav(raw: bytes, suffix: str) -> pathlib.Path:
    f_src = f_dst = None
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(raw); f_src = f.name
    dst = f_src + '.wav'
    try:
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', f_src,
                        '-ar', '16000', '-ac', '1', dst],
                       check=True, timeout=20)
        return pathlib.Path(dst)
    except subprocess.CalledProcessError:
        raise HTTPException(415, 'Could not decode audio. Use WAV/MP3/OGG/M4A.')
    except subprocess.TimeoutExpired:
        raise HTTPException(408, 'Audio decode timed out')
    finally:
        try:
            os.unlink(f_src)
        except OSError:
            pass

def _retryable(e: Exception) -> bool:
    import requests as _rq
    return isinstance(e, (_rq.Timeout, _rq.ConnectionError))

def transcribe(wav: pathlib.Path):
    if not STT_BREAKER.allow():
        _count('stt_circuit_open')
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
                    raise requests.ConnectionError('server 5xx')
                return r
            r = retry(call, attempts=2, retryable=_retryable)
        logger.info('stt_call status=%s latency_s=%.2f', r.status_code, time.time() - t0)
        STT_BREAKER.record_success(); _count('stt_ok')
        if r.status_code != 200:
            logger.error('stt_failed body=%s', r.text[:200]); _count('stt_fail_http')
            raise HTTPException(502, 'Transcription service unavailable')
        j = r.json()
        if not j.get('success'):
            logger.error('stt_unsuccessful body=%s', r.text[:200]); _count('stt_fail_body')
            raise HTTPException(502, 'Transcription failed')
        return j.get('transcript', ''), j.get('detected_language_code', 'unknown')
    except HTTPException:
        STT_BREAKER.record_failure(); raise
    except Exception as e:          # noqa: BLE001
        STT_BREAKER.record_failure(); _count('stt_fail_exc')
        logger.error('stt_exc err=%s', e)
        raise HTTPException(502, 'Transcription service unavailable')
    finally:
        try:
            os.unlink(wav)
        except OSError:
            pass

def synthesize(text: str):
    if not TTS_BREAKER.allow():
        _count('tts_circuit_open')
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
                raise requests.ConnectionError('server 5xx')
            return r
        r = retry(call, attempts=2, retryable=_retryable)
        logger.info('tts_call status=%s latency_s=%.2f chars=%d', r.status_code, time.time() - t0, len(capped))
        TTS_BREAKER.record_success(); _count('tts_ok')
        if r.status_code != 200:
            logger.error('tts_failed body=%s', r.text[:300]); _count('tts_fail_http')
            raise HTTPException(502, 'Voice synthesis unavailable')
        return r.content
    except HTTPException:
        TTS_BREAKER.record_failure(); raise
    except Exception as e:          # noqa: BLE001
        TTS_BREAKER.record_failure(); _count('tts_fail_exc')
        logger.error('tts_exc err=%s', e)
        raise HTTPException(502, 'Voice synthesis unavailable')

def rag_answer(query: str):
    t0 = time.time()
    hits = retriever.search(query, k=5)
    reply, sources, is_canned = responder.answer(query, hits)
    logger.info('rag_answer hits=%d latency_s=%.2f canned=%s', len(hits), time.time() - t0, is_canned)
    _count('rag_answered')
    return reply, sources

class TextQuery(BaseModel):
    text: str = Field(min_length=2, max_length=500)

def _audio_or_none(reply: str):
    try:
        return base64.b64encode(synthesize(reply)).decode()
    except HTTPException:
        _count('tts_degraded')
        return None

@app.post('/api/ask_text')
def ask_text(q: TextQuery):
    reply, sources = rag_answer(q.text)
    return {'transcript': q.text, 'reply': reply, 'sources': sources,
            'audio_wav_b64': _audio_or_none(reply)}

@app.post('/api/ask_audio')
async def ask_audio(request: Request, audio: UploadFile = File(...)):
    raw = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(raw) > MAX_AUDIO_BYTES:
        raise HTTPException(413, 'Audio too large (max 8 MB)')
    suffix = pathlib.Path(audio.filename or 'q.webm').suffix or '.webm'
    wav = to_wav(raw, suffix)
    query, lang = transcribe(wav)
    if not query.strip():
        return {'transcript': '', 'reply': 'Suno, awaaz samajh nahi aayi. Thodi der phir se kahein.',
                'detected_language_code': lang, 'sources': [], 'audio_wav_b64': None}
    reply, sources = rag_answer(query)
    return {'transcript': query, 'reply': reply, 'detected_language_code': lang,
            'sources': sources, 'audio_wav_b64': _audio_or_none(reply)}
