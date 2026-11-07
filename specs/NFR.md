# Siddha — Non-Functional Requirements (explicit, executable)

## Reliability
- Gnani calls (STT, TTS): timeout 60/90 s, ≤2 retries w/ backoff+jitter, circuit breaker (5 consecutive failures → 60 s cooldown) → fail fast 502. A budget refusal releases a half-open probe instead of blaming the provider.
- App: `/api/health` is liveness (corpus, key, ffmpeg); `/api/ready` is readiness (model and index in memory) and is the container healthcheck.
- Temp audio files: ALWAYS deleted in finally-blocks (disk leak = memory pressure).

## Performance
- 1 turn = 1 STT + 1 TTS call (≈2 Gnani calls).
- p50 latency budget: ≤ 8 s/turn incl. 2 round trips (STT≈0.5s, retrieve≈0.1s, TTS≈1.5s).
- Corpus is pre-indexed and memory-resident: search latency target < 200 ms. The model is warmed in the server lifespan, once, under a lock.

## Security / Privacy
- Secrets: GNANI_API_KEY only in ~/.env, never logged, never in repo (.dockerignore/.gitignore cover).
- PII: audio is processed transiently, never persisted; logs carry only lengths/ids, not content. Session and answer responses are `Cache-Control: no-store`; the page never adopts a session id from the URL and sends `Referrer-Policy: no-referrer`.
- Input: max audio 8 MB; the whole multipart body is cut at 8 MB + 512 KiB while streaming, before FastAPI can spool it to disk; text ≤ 500 chars; TTS text capped 600 chars.
- Rate limit: ≤ 30 requests/min per IP (in-memory token bucket).
- Cost: ≤ 5,000 Gnani calls globally and ≤ 250 per visitor, checked and incremented under one lock before the provider request; exhaustion is a typed 503.

## Correctness
- Every fact in a reply must come from a retrieved scheme record (template-composed) or be an explicit statement that the record is silent. There is no canned portal flow and no free generation.
- Eligibility verdicts may only quote a verbatim substring of the record; an unverified quote falls back to the grounded responder.
- A concrete deadline in the past is reported as passed; a recurring phrase is not converted into a date.
- All external calls logged with status+latency (observability hook).

## Availability
- If TTS fails: sentence still rendered as text (degrade, don't crash). If STT fails: typed 502, never a stack trace.

## Known ceilings (accepted)
- 5,000 programme credits ⇒ ~2,500 turns; the per-visitor cap of 250 calls ⇒ ~125 turns per visitor.
- Single worker; demo scale, not horizontal.
- In-memory rate limiter, budgets and circuit breaker = per-process only.
