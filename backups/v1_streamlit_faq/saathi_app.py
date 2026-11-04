import json, os, pathlib, subprocess, sys
import streamlit as st
import numpy as np
try:
    import requests
except ImportError:
    sys.exit("requests not installed")
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = pathlib.Path(__file__).parent

def load_key():
    env = {}
    p = pathlib.Path('/Users/arunkumar/.env')
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env['GNANI_API_KEY']

API = load_key()
FAQ = json.loads((ROOT / 'faq.json').read_text())
QUESTIONS = [f['q'] for f in FAQ]

# character n-gram TF-IDF: robust for code-mixed / transliterated text
VERCORIZER = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 5), lowercase=True)
V = VERCORIZER.fit_transform(QUESTIONS)

def find_best(query: str):
    qv = VERCORIZER.transform([query])
    sims = cosine_similarity(qv, V)[0]
    idx = int(np.argmax(sims))
    return FAQ[idx], float(sims[idx])

def to_wav(src: pathlib.Path) -> pathlib.Path:
    dst = src.with_suffix('.wav')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(src),
                    '-ar', '16000', '-ac', '1', str(dst)], check=True)
    return dst

def transcribe(wav: pathlib.Path) -> str:
    with open(wav, 'rb') as f:
        r = requests.post('https://api.vachana.ai/stt/v3',
            headers={'X-API-Key-ID': API},
            files={'audio_file': ('q.wav', f, 'audio/wav')},
            data={'model': 'prisma-v3.0',
                  'language_code': 'indic-auto',
                  'format': 'transliterate'},
            timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f'STT {r.status_code}: {r.text}')
    return r.json().get('transcript', '')

def synthesize(text: str) -> bytes:
    # short Hinglish answer, Poorvi voice
    r = requests.post('https://api.vachana.ai/api/v1/tts/inference',
        headers={'X-API-Key-ID': API, 'Content-Type': 'application/json'},
        json={'text': text, 'voice': 'Poorvi', 'model': 'timbre-v2.5',
              'language': 'hi-en',
              'audio_config': {'sample_rate': 16000, 'num_channels': 1,
                               'sample_width': 2, 'encoding': 'linear_pcm',
                               'container': 'wav'}},
        timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f'TTS {r.status_code}: {r.text[:300]}')
    return r.content

st.set_page_config(page_title='Saathi — Voice Scholarship Guide', page_icon='🎓', layout='centered')
st.title('🎓 Saathi — Your Voice Guide to Scholarships')
st.caption('Built on Gnani Prisma STT + Timbre TTS · Speak Hinglish, Hindi or English')
st.markdown('**Try:** "scholarship ke liye kaunse documents chahiye" or "NSP ka status kaise check karein"')

audio = st.audio_input('🎙️ Ask Saathi your scholarship question')

if audio:
    src = pathlib.Path(st.session_state.get('audio_path', 'recorded.webm'))
    src.write_bytes(audio.getbuffer())
    with st.spinner('Listening with Prisma…'):
        try:
            wav = to_wav(src)
            query = transcribe(wav)
        except Exception as e:
            st.error(f'Speech error: {e}')
            st.stop()

    st.write('**You asked:**', query)
    if not query.strip():
        st.warning('Could not hear anything — try again in a quieter place.')
        st.stop()

    best, score = find_best(query)
    st.write(f'_match confidence: {score:.2f}_')
    st.success(f'**Saathi:** {best["a"]}')

    with st.spinner('Speaking with Timbre…'):
        try:
            reply = synthesize(best['a'])
            st.audio(reply, format='audio/wav', autoplay=True)
        except Exception as e:
            st.warning(f'Voice reply unavailable: {e}')

st.divider()
st.caption('Demo for Gnani Great Indian AI Internship Challenge · 2026 · Voice AI for every Indian student')
