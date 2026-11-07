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

    DATA[("1,141 myScheme<br/>scheme records")]
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
1. Browser mic audio (webm/opus) is sent to `POST /api/ask_audio`.
2. `to_wav()` re-encodes it to 16 kHz mono (a Prisma requirement) and deletes the source file in `finally`.
3. `transcribe()` calls Prisma. It retries on Timeout/ConnectionError/5xx (2 attempts); the circuit breaker opens after 5 failures (60 s cooldown).
4. `rag_answer()` resolves session context, loads the prebuilt FAISS + BM25 index, fuses results with RRF, and selects the top 5. `responder` composes the Hinglish answer from record fields. Status and renewal questions are answered from the record text. Aspect-only follow-ups reuse the last record and skip retrieval.
5. `synthesize()` calls Timbre. `spoken.render()` keeps the text voice-safe (caps length, strips markup, inserts `<pauses>`).
6. `/api/ask_audio` returns `{transcript, detected_language_code, reply, sources[], session_id, follow_up, context_used, context_name, audio_wav_b64}`.

## Conversation context
Sessions are keyed by a random ID generated in the browser and validated server-side (`^[A-Za-z0-9_-]{8,80}$`). The store is text-only, in-memory, expires after 30 minutes of inactivity, holds at most 500 sessions and 8 turns per session.

Resolution is deterministic (`src/context.py`), not a model rewrite:

| Follow-up | Behaviour |
|---|---|
| pronoun or “aur/and” with only an aspect (“aur last date?”) | answer from the last scheme, no new retrieval |
| state / category / course refinement (“Tamil Nadu ke liye?”) | re-retrieve with the last scheme as an anchor |
| a new scheme name (“PM Kisan…”) | treat as a new topic; bypass context |

`GET /api/session/{id}` restores the last turn after a refresh; `DELETE /api/session/{id}` starts a new conversation.

## Key decisions
- **No generative LLM in the answer path.** Answers are assembled from retrieved scheme records (zero hallucination). An LLM slot is deliberately left open (`specs/NFR.md` trim-down reasons) but disabled until an owner explicitly supplies a key.
- **Retrieval-grounded, not free-chat.** Whether it speaks Hinglish, Hindi, Tamil or mixed — the facts always come from the corpus.
- **Prebuilt indices committed to repo** (`scholarships.faiss`, `corpus_emb.npy`) — demo/cold-start is seconds, not minutes.
- **Temp WAVs are always deleted in `finally`.** No disk buildup.

## Scaling bounds
Single worker (rate limiter and breakers are in-memory). To scale: replace in-memory counters with Redis; move `to_wav` to a queue; shard FAISS by category.
