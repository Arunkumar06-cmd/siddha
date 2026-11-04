"""Saathi — production backend (Gnani Voice Scholarship Concierge).
Pipeline: mic audio -> ffmpeg 16k/mono -> Prisma STT -> RAG over myScheme
scholarship corpus (MiniLM + FAISS + BM25, RRF fused) -> grounded answer
-> Timbre TTS (Hinglish). All calls logged; secrets never logged."""
import os, sys, json, base64, tempfile, subprocess, pathlib, time, uuid
sys.path.insert(0, str(pathlib.Path(__file__).parent / 'src'))

import logging
import requests
from fastapi import FastAPI, UploadFile, Request, File, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi import status
from pydantic import BaseModel, Field

import config
from config import logger, GNANI_API_KEY, GNANI_BASE, STT_MODEL, TTS_MODEL, TTS_VOICE, TTS_LANG, TTS_SPEED
import retriever, responder
from spoken import render, speakify

MAX_AUDIO_BYTES = 8 * 1024 * 1024          # 8 MB ~= 50 s at 16k opus
REQUEST_TIMEOUT_STT = 60
REQUEST_TIMEOUT_TTS = 90
SESSION_ID = None  # reserved

app = FastAPI(title='Saathi', version='1.0.0', docs_url=None, redoc_url=None)
STATIC = pathlib.Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')

@app.get('/')
def index():
    return FileResponse(STATIC / 'index.html', headers={'Cache-Control': 'no-cache'})

@app.get('/api/health')
def health():
    return {'status': 'ok', 'version': '1.0.0'}

# ---------- error models: never leak internals ----------
@app.exception_handler(HTTPException)
async def _http_err(request: Request, exc: HTTPException):
    logger.warning('http_error path=%s detail=%s', request.url.path, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={'error': exc.detail})

@app.exception_handler(RequestValidationError)
async def _val_err(request: Request, exc: RequestValidationError):
    logger.warning('validation_error path=%s errs=%s', request.url.path, exc.errors())
    return JSONResponse(status_code=422, content={'error': 'Invalid request'})

@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    logger.exception('unhandled path=%s err=%s', request.url.path, exc)
    return JSONResponse(status_code=500, content={'error': 'Internal error'})

# ---------- pipeline ----------
def to_wav(raw: bytes, suffix: str) -> pathlib.Path:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(raw); src = f.name
    dst = src + '.wav'
    try:
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src,
                        '-ar', '16000', '-ac', '1', dst],
                       check=True, timeout=20)
    except subprocess.CalledProcessError:
        raise HTTPException(415, 'Could not decode audio. Use WAV/MP3/OGG/M4A.')
    except subprocess.TimeoutExpired:
        raise HTTPException(408, 'Audio decode timed out')
    return pathlib.Path(dst)

def transcribe(wav: pathlib.Path):
    t0 = time.time()
    with open(wav, 'rb') as f:
        r = requests.post(f'{GNANI_BASE}/stt/v3',
            headers={'X-API-Key-ID': GNANI_API_KEY,
                     'X-API-Request-ID': uuid.uuid4().hex},
            files={'audio_file': ('q.wav', f, 'audio/wav')},
            data={'model': STT_MODEL, 'language_code': 'indic-auto', 'format': 'codemix'},
            timeout=REQUEST_TIMEOUT_STT)
    logger.info('stt_call status=%s latency_s=%.2f', r.status_code, time.time() - t0)
    if r.status_code != 200:
        logger.error('stt_failed body=%s', r.text[:200])
        raise HTTPException(502, 'Transcription service unavailable')
    j = r.json()
    if not j.get('success'):
        logger.error('stt_unsuccessful body=%s', r.text[:200])
        raise HTTPException(502, 'Transcription failed')
    return j.get('transcript', ''), j.get('detected_language_code', 'unknown')

def synthesize(text: str):
    t0 = time.time()
    spoken_text = render(text, use_tags=True)
    r = requests.post(f'{GNANI_BASE}/api/v1/tts/inference',
        headers={'X-API-Key-ID': GNANI_API_KEY, 'Content-Type': 'application/json'},
        json={'text': spoken_text, 'voice': TTS_VOICE, 'model': TTS_MODEL,
              'language': TTS_LANG, 'speed': TTS_SPEED,
              'audio_config': {'sample_rate': 16000, 'num_channels': 1,
                               'sample_width': 2, 'encoding': 'linear_pcm',
                               'container': 'wav'}},
        timeout=REQUEST_TIMEOUT_TTS)
    logger.info('tts_call status=%s latency_s=%.2f', r.status_code, time.time() - t0)
    if r.status_code != 200:
        logger.error('tts_failed body=%s', r.text[:300])
        raise HTTPException(502, 'Voice synthesis unavailable')
    return r.content

def rag_answer(query: str):
    t0 = time.time()
    hits = retriever.search(query, k=5)
    reply, sources, is_canned = responder.answer(query, hits)
    logger.info('rag_answer query_len=%d hits=%d latency_s=%.2f canned=%s',
                len(query), len(hits), time.time() - t0, is_canned)
    return reply, sources

class TextQuery(BaseModel):
    text: str = Field(min_length=2, max_length=500)

@app.post('/api/ask_text')
def ask_text(q: TextQuery):
    reply, sources = rag_answer(q.text)
    try:
        audio_b64 = base64.b64encode(synthesize(reply)).decode()
    except HTTPException:
        audio_b64 = None
    return {'transcript': q.text, 'reply': reply, 'sources': sources, 'audio_wav_b64': audio_b64}

@app.post('/api/ask_audio')
async def ask_audio(request: Request, audio: UploadFile = File(...)):
    ctype = audio.content_type or ''
    logger.info('ask_audio filename=%s ctype=%s', audio.filename, ctype)
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
    try:
        audio_b64 = base64.b64encode(synthesize(reply)).decode()
    except HTTPException:
        audio_b64 = None
    return {'transcript': query, 'reply': reply,
            'detected_language_code': lang, 'sources': sources,
            'audio_wav_b64': audio_b64}
