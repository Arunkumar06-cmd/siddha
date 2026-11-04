"""Saathi backend. FastAPI. Pipeline: mic audio -> Prisma STT -> RAG
(MiniLM+FAISS+BM25/RRF) -> grounded answer -> Timbre TTS (return wav b64)."""
import os, sys, json, base64, tempfile, subprocess, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent / 'src'))
import requests
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import retriever, responder, config  # config asserts env on import

app = FastAPI(title='Saathi — Voice Scholarship Concierge')
STATIC = pathlib.Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')

@app.get('/')
def index():
    return FileResponse(STATIC / 'index.html')

def to_wav(upload_bytes: bytes, suffix: str):
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(upload_bytes); src = f.name
    dst = src + '.wav'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src,
                    '-ar', '16000', '-ac', '1', dst], check=True)
    return pathlib.Path(dst)

def transcribe(wav_path: pathlib.Path):
    with open(wav_path, 'rb') as f:
        r = requests.post('https://api.vachana.ai/stt/v3',
            headers={'X-API-Key-ID': config.GNANI_API_KEY},
            files={'audio_file': ('q.wav', f, 'audio/wav')},
            data={'model': 'prisma-v3.0', 'language_code': 'indic-auto',
                  'format': 'codemix'},
            timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f'STT {r.status_code}: {r.text[:200]}')
    j = r.json()
    return j.get('transcript', ''), j.get('detected_language_code', 'unknown')

def synthesize(text: str):
    r = requests.post('https://api.vachana.ai/api/v1/tts/inference',
        headers={'X-API-Key-ID': config.GNANI_API_KEY,
                 'Content-Type': 'application/json'},
        json={'text': text, 'voice': 'Poorvi', 'model': 'timbre-v2.5',
              'language': 'hi-en',
              'audio_config': {'sample_rate': 16000, 'num_channels': 1,
                               'sample_width': 2, 'encoding': 'linear_pcm',
                               'container': 'wav'}},
        timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f'TTS {r.status_code}: {r.text[:300]}')
    return r.content

def rag_answer(query: str):
    hits = retriever.search(query, k=5)
    reply, sources = responder.answer(query, hits)
    return reply, sources

class TextQuery(BaseModel):
    text: str

@app.post('/api/ask_text')
def ask_text(q: TextQuery):
    reply, sources = rag_answer(q.text)
    try:
        audio_b64 = base64.b64encode(synthesize(reply)).decode()
    except Exception as e:
        audio_b64 = None
    return {'transcript': q.text, 'reply': reply, 'sources': sources,
            'audio_wav_b64': audio_b64}

@app.post('/api/ask_audio')
def ask_audio(audio: UploadFile = File(...)):
    raw = audio.file.read()
    suffix = pathlib.Path(audio.filename or 'q.webm').suffix or '.webm'
    wav = to_wav(raw, suffix)
    query, lang = transcribe(wav)
    if not query.strip():
        return {'transcript': '', 'reply': 'Sunai nahi diya — fir se bole.',
                'detected_language_code': lang, 'sources': [], 'audio_wav_b64': None}
    reply, sources = rag_answer(query)
    try:
        audio_b64 = base64.b64encode(synthesize(reply)).decode()
    except Exception:
        audio_b64 = None
    return {'transcript': query, 'reply': reply, 'detected_language_code': lang,
            'sources': sources, 'audio_wav_b64': audio_b64}

@app.get('/api/health')
def health():
    try:
        r = requests.get('https://api.vachana.ai/', timeout=5)
    except Exception:
        pass
    return {'status': 'ok'}
