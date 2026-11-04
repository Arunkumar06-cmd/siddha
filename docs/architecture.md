# Architecture

## Overview
Single-process FastAPI service. The browser owns the microphone; everything beyond MediaRecorder happens server-side.

```mermaid
flowchart LR
    A[Browser mic<br/>MediaRecorder] -->|webm/opus| B[FastAPI /api/ask_audio]
    B -->|ffmpeg| C[16 kHz mono WAV]
    C -->|multipart| D[Gnani Prisma v3.0<br/>indic-auto · codemix]
    D -->|transcript + detected_language| E[RAG retriever]
    E -->|Top-5 chunk| F[Responder<br/>grounded composition]
    F -->|answer + <pauses>| G[Gnani Timbre TTS]
    G -->|WAV| H[/api/ask_audio response<br/>audio_wav_b64 |
    E <--> I[(FAISS index<br/>+ BM25 + RRF)]
    I <--> J[(scholarships.jsonl<br/>1,142 schemes)]
```

## Data flow
1. Mic audio → webm/opus in browser → POST `/api/ask_audio`.
2. `to_wav()` re-encodes to 16 kHz mono (Prisma requirement), deletes source in `finally`.
3. `transcribe()` → Prisma; retries on Timeout/ConnectionError/5xx (2 attempts), circuit breaker trips after 5 failures (60 s cooldown).
4. `rag_answer()` → retriever loads prebuilt FAISS + BM25, RRF-fuses, picks ann-ready top-5; `responder` composes Hinglish, canned answers for status/renewal flows.
5. `synthesize()` → Timbre with voice-safe rendering (`spoken.render()` caps length, strips markup, inserts `<pauses>`).
6. `/api/ask_audio` returns `{transcript, detected_language_code, reply, sources[], audio_wav_b64}`.

## Key decisions
- **No generative LLM in the answer path.** Answers are assembled from retrieved scheme records (zero hallucination). An LLM slot is deliberately left open (`specs/NFR.md` trim-down reasons) but disabled until an owner explicitly supplies a key.
- **Retrieval-grounded, not free-chat.** Whether it speaks Hinglish, Hindi, Tamil or mixed — the facts always come from the corpus.
- **Prebuilt indices committed to repo** (`scholarships.faiss`, `corpus_emb.npy`) — demo/cold-start is seconds, not minutes.
- **Temp WAVs are always deleted in `finally`.** No disk buildup.

## Scaling bounds
Single worker (rate limiter and breakers are in-memory). To scale: replace in-memory counters with Redis; move `to_wav` to a queue; shard FAISS by category.
