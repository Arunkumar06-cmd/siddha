# Saathi ✦ — Voice Guide to Scholarships for India

A voice-first assistant that tells students **which scholarship they qualify for, what documents they need, and how to apply** — in Hinglish, Hindi, Tamil and more — grounded in the live myScheme corpus (1,142 government schemes).

Built for the **Gnani Great Indian AI Internship Challenge** (Nov 2026). Powered end-to-end by Gnani's own models:

- **Prisma v3.0** (`/stt/v3`, `indic-auto`, `codemix`) — speech to text
- **Timbre v3.0** (Hinglish voice, `<pauses>` audio tags) — text to speech

## Architecture

```
browser mic ─► MediaRecorder (webm/opus)
            ─► FFmpeg 16 kHz mono WAV
            ─► Gnani Prisma STT ─► transcript (+ detected language)
            ─► RAG over myScheme scholarships.jsonl
                MiniLM-L12 multilingual (384d) + FAISS IP (dense)
                BM25 + Reciprocal Rank Fusion
            ─► grounded answer (template-composed, zero hallucination)
            ─► Timbre TTS (Hinglish, <pauses>) ─► audio reply
```

## Run locally

```bash
pip install -r requirements.txt
# .env: GNANI_API_KEY=...   (from app.gnani.ai → API keys)
uvicorn server:app --host 0.0.0.0 --port 8765
# open http://localhost:8765
```

## Tests

```bash
python -m pytest tests/ -q     # 13 tests: unit + HTTP-mocked integration
```

## Deploy (public demo)

Any Docker host works (HF Spaces / Render / Fly.io). Set one secret:
`GNANI_API_KEY` → `~/.env` injected at runtime (never in the image).
Never commit `.env`. Health check: `GET /api/health`.

## Anti-slop notes
- Retrieval-grounded answers; the LLM is **not** allowed to invent facts — every reply quotes scheme-shaped facts.
- All Gnani calls are logged (status, latency), secrets never logged.
- Test suite includes unhappy paths (empty audio, validation errors, mocked API failure).
- Rate of external calls per request: exactly 2 (STT, TTS) + cached embeddings.

## Cost & limits
- ~1 STT + 1 TTS call per turn. 5,000 programme credits ⇒ ~2,500 turns of headroom.
- No data leaves your server except voice audio to Gnani (the demo data: myScheme is public).
