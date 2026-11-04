# Siddha — Non-Functional Requirements (explicit, executable)

## Reliability
- Gnani calls (STT, TTS): timeout 60/90 s, ≤2 retries w/ backoff+jitter, circuit breaker (5 consecutive failures → 60 s cooldown) → fail fast 502.
- App: health check must be real (not a stub) — verifies server + imports.
- Temp audio files: ALWAYS deleted in finally-blocks (disk leak = memory pressure).

## Performance
- 1 turn = 1 STT + 1 TTS call (≈2 Gnani calls).
- p50 latency budget: ≤ 8 s/turn incl. 2 round trips (STT≈0.5s, retrieve≈0.1s, TTS≈1.5s).
- Corpus is pre-indexed and memory-resident: search latency target < 200 ms.

## Security / Privacy
- Secrets: GNANI_API_KEY only in ~/.env, never logged, never in repo (.dockerignore/.gitignore cover).
- PII: audio is processed transiently, never persisted; logs carry only lengths/ids, not content.
- Input: max audio 8 MB; text ≤ 500 chars; TTS text capped 600 chars.
- Rate limit: ≤ 30 requests/min per IP (in-memory token bucket).

## Correctness
- Every fact in a reply must come from a retrieved scheme record (template-composed) OR be a canned, curated constraint (NSP flow / renewal / status) — never generated freely.
- All external calls logged with status+latency (observability hook).

## Availability
- If TTS fails: sentence still rendered as text (degrade, don't crash). If STT fails: typed 502, never a stack trace.

## Known ceilings (accepted)
- 5,000 programme credits ⇒ ~2,500 turns.
- Single worker; demo scale, not horizontal.
- In-memory rate limiter + circuit breaker = per-process only.
