# Architecture

## Overview
Single-process FastAPI service. The browser owns the microphone; everything beyond MediaRecorder happens server-side.

```mermaid
flowchart TB
    subgraph client["Browser"]
        MIC["Mic · MediaRecorder<br/>webm / opus"]
    end

    subgraph api["FastAPI · one process"]
        ROUTE["POST /api/ask_audio"]
        FF["ffmpeg<br/>16 kHz mono WAV"]
        RAG["Hybrid retrieval<br/>FAISS + BM25 → RRF"]
        RESP["Grounded responder<br/>templates from scheme records"]
        GUARD["Guardrails<br/>rate limit · retry + jitter<br/>circuit breakers · typed errors"]
    end

    subgraph gnani["Gnani voice models"]
        STT["Prisma v3.0<br/>indic-auto · codemix"]
        TTS["Timbre v3.0<br/>Shivani · hi-en"]
    end

    DATA[("1,142 myScheme<br/>scholarship records")]
    OUT["JSON + base64 WAV"]

    MIC -->|"webm/opus"| ROUTE
    ROUTE --> FF --> STT
    STT -->|"transcript + language"| RAG
    DATA --> RAG
    RAG --> RESP --> TTS
    TTS --> OUT
    ROUTE -.-> GUARD
    RAG -.-> GUARD
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
