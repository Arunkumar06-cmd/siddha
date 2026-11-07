# Changelog
All notable changes to Siddha. Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]
### Security / reliability hardening (pre-submission audit)
- **Session fixation/PII:** the page no longer adopts `?session=` from the URL; session and answer responses are `Cache-Control: no-store`, and the page sends `Referrer-Policy: no-referrer`.
- **Cost cap:** a global (`SIDDHA_CREDIT_BUDGET`, 5,000) and per-visitor (`SIDDHA_CLIENT_CREDIT_BUDGET`, 250) Gnani credit budget is checked and incremented under one lock before every provider HTTP attempt. Exhaustion returns 503 without touching the provider and releases a half-open breaker probe.
- **Upload DoS:** ASGI middleware counts the `/api/ask_audio` body as it streams and aborts at `MAX_AUDIO_BYTES + 512 KiB`, before FastAPI can spool an unbounded multipart body to disk.
- **Cold start:** the model and index load once under a lock (the old `lru_cache` could build the 2 GB model twice when two first requests raced) and warm in the server lifespan; the container healthcheck is `/api/ready`, which stays 503 until warm.
- **Supply chain:** `pip-audit` now fails the security workflow on any new advisory, with three documented ignores (`PYSEC-2025-194`, `PYSEC-2026-3447`, `GHSA-xmj3-9gf7-h52w`); gitleaks is checksum-verified in both workflows.
- **Eval guard:** `evals/baseline.json` is committed and `scripts/eval_retrieval.py --check` runs in CI; the Docker job now smoke-runs the image, waits for `/api/ready` and fetches the page.
- **Dead quality metrics:** `audio_turns`, `empty_transcript`, `audio_returned`, `audio_truncated` and `tts_attempted` are now incremented, so the rates in `/api/metrics` have real denominators.

### Fixed (pre-submission review)
- **No invented process.** The hard-coded NSP/PFMS "status" and "renewal" answers (which fired for any scheme, including State schemes not on NSP, and ran before retrieval) are removed. Status and renewal now quote the record or say it is silent.
- **Never speak half a rule.** Eligibility and benefit text is clipped on whole sentences (`clip_sentences`, aware of "Rs. 2.5" and "No. 4"); an overlong first sentence is sent to the official page instead of being read in part. Document lists are clipped on item boundaries (`clip_items`).
- **Deadlines are checked, not quoted blindly.** A concrete date in the past is reported as passed; a recurring phrase ("first week of April every year") is not turned into a date; only a current date is spoken as the last date.
- **Status and renewal are grounded.** "Status Tracking"/"Check Application Status" lines are quoted when present; a renewal *document* ("Last Subscription Renewal Copy") is not mistaken for the renewal *process*.
- **Eligibility quotes are verified.** The LLM classifier's quote must be a verbatim substring of the record; a paraphrased or invented line silently falls back to the grounded responder.
- **Confidence gate recalibrated.** `MIN_DENSE=0.545` (just above the off-topic maximum 0.5439) and `SOFT_DENSE=0.58`; an exact, unique scheme name overrides the floor, and the exact-name lookup searches the whole corpus. "gym membership offers" is refused; "Mukhyamantri Matrupushti Uphar kya hai" is answered.
- **Corpus deduplicated:** 1,142 rows → 1,141 unique schemes; FAISS index and embeddings rebuilt to match.
- **Audio is cut on sentence boundaries**, never by string index. The old `[:600]` slice could split a sentence or a `<pauses>` tag; the API now also reports `audio_truncated`.
- **STT retry resent an empty file** (the handle was already read to EOF); the upload is now held as bytes.
- **Circuit breaker** now has a real half-open state (one probe), no longer counts provider 4xx as outages, and logs open/half-open/closed transitions.
- **Temp-file leaks** closed: the WAV is removed when the circuit is open or decoding fails.
- **Hindi/Tamil follow-ups**: the tokenizer discarded every non-Latin character, so a Devanagari or Tamil question about a *new* scheme was answered from the previous one. Devanagari and Tamil are now tokenised (NFC-normalised) with aspect/filler/pronoun lists; unknown Indic words count as topic words and force retrieval.
- **Aspect keywords match on word starts** (`paper` no longer fires on `newspaper`; removed the `patr`/`patricia` entries).
- `ask_audio` is a plain `def` route, so ffmpeg, provider calls and embedding no longer block the event loop and `/api/health`.
- Uploads are allow-listed by container signature and decoded with `-nostdin`, a file/pipe protocol whitelist, no non-audio streams and a 30 s cap.
- Docker: the baked embedding model (`HF_HOME=/opt/hf`) is now copied into the runtime image and the runtime is offline, so the first request no longer downloads ~2 GB; CPU torch is pinned as in CI.
- Spoken layer: em/en dashes were never normalised (a `noqa` comment had swallowed the rule).
- README: removed claims the code did not support, removed hot-linked banner widgets, dropped static test/coverage badges, added **Known limitations**.

### Added
- **Conversation memory** (`src/context.py`, `src/conversation.py`): deterministic follow-up resolution keyed by session. Aspect-only follow-ups answer from the last scheme with no new retrieval; state/category refinements re-retrieve with the prior scheme as an anchor; new scheme names bypass context. Sessions are text-only, in-memory, 30-minute TTL, 500-session cap, 8-turn cap.
- Session endpoints `GET/DELETE /api/session/{id}`; page refresh restores the last turn; “Start a new conversation” resets it.
- Demo re-recorded as a **two-turn conversation** (139 s, 1080×1080): documents question, then “Aur is scheme ki last date kya hai?” with the context row visible; male founder narration (Devansh), Avinash asking, Shivani answering.
- 218 tests, 90.6% coverage.
- Opt-in eligibility reasoner (`src/eligibility.py`, `src/llm.py`): profile extraction + record-coverage classification via any OpenAI-compatible endpoint (e.g. DeepSeek), answers the "am I eligible?" gap; strict fallback to grounded templates when unconfigured; fully mocked tests (`tests/test_eligibility.py`)

- BGE-M3 index rebuilt (512-token max sequence, fp32/MPS) — replaces MiniLM-L12 for multilingual/code-mixed retrieval
- `docs/eval-audio.md`: telephonic/noise robustness probe (8 kHz, traffic/fan) with critical-term preservation and honest caveats
- `scripts/eval_retrieval.py`: four-set retrieval and confidence evaluation (hand, named, noisy, off-topic) with bootstrap intervals and a committed regression baseline (`evals/baseline.json`)
- `scripts/eval_audio.py`: reproduces the telephonic/noise probe end to end

### Changed
- Retrieval: **state-aware routing** shipped — a query naming a state/UT now ranks that state's schemes first (1.35/0.75 boost/suppression); `central government` queries filter to Central; a state-less query gets a 1.2 Central multiplier. Fixes the Bihar-instead-of-Central regression visible in the demo query (delivered in this submission build)
- Frontend rebuilt as a **paper-and-ink LaTeX look**: warm ivory background, deep-ink serif type (Iowan/Palatino stack), deep-petrol-teal accents, masthead rules, small-caps speaker labels — high contrast and calm to read
- Reply text is now `SIDDHA` small-caps with the transcript set as an ink-on-tan note and sources as hairline-bordered chips
- Demo and intro/outro cards re-recorded on the new theme (Georgia serif, ivory, teal) so the submission video matches the product
- Demo screenshot recaptured on the new theme (42 KB WebP)
- Product name unified as **Siddha** across app, docs, env vars (`SIDDHA_*`), Docker user, and repo
- README now shows a real UI screenshot instead of the hand-drawn SVG diagram
- README hero: centred title and positioning line, logo badges with `logoColor=white`, native GitHub alerts, Mermaid architecture in a collapsible block
- Demo re-recorded with a state-neutral question (`SC students … central government post matric scholarship`), so the spoken answer is the Central scheme rather than an unstated state scheme

### Fixed
- `LICENSE` contained only a header line, so GitHub reported "license not identified" — now the full MIT text
- A State scheme is now labelled with its state when the question names none, so a generic query can no longer imply nationwide eligibility
- Removed two rows of browser-capture padding that appeared as a thin line under the answer caption

### Removed
- Internal agent/working notes (`STATE.md`, `LEDGER.md`, `WBS.md`, `RULES.md`, `DECISIONS.md`, `ledger.json`) from the public tree; they stay locally and are gitignored

### Added
- Opt-in eligibility reasoner (`src/eligibility.py`, `src/llm.py`): profile extraction + record-coverage classification via any OpenAI-compatible endpoint (e.g. DeepSeek), answers the "am I eligible?" gap; strict fallback to grounded templates when unconfigured; fully mocked tests (`tests/test_eligibility.py`)

- GitHub release **v2.2.0** with the demo video attached: https://github.com/Arunkumar06-cmd/siddha/releases/tag/v2.2.0
- 139 s demo video (`docs/demo.mp4`, 1080×1080): two real Prisma STT → hybrid retrieval → Timbre TTS turns, with Avinash asking and Shivani answering; the second turn is a follow-up that keeps the scheme in context. Founder narration by Devansh.
- State/UT detection (`src/places.py`) with canonical names and common spellings, used by the grounded responder
- `docs/research-inventory.md`: the problem and source research behind the corpus
- `docs/submission.md`: project explanation, Gnani model/API list, LinkedIn and X copy, posting checklist
- README links the demo video beside the screenshot
- CI pipeline (`quality`: ruff, byte-compile, pytest, gitleaks; `docker`: image build) with pip + HF caching, 10-min timeouts, PR + main triggers
- Security workflow: gitleaks + `pip-audit` advisory scan
- `/api/metrics` endpoint (counters, circuit state, rate-limit config)
- Circuit breakers for STT/TTS (5 failures → 60 s cooldown), retry with backoff+jitter on Timeout/ConnectionError/5xx only
- Per-IP rate limiting (30 req/min), typed 4xx/5xx error envelope, `/api/health` corpus-aware health check
- Failure-mode suite: temp-file cleanup, synthetic timeout → circuit opens, concurrency, rate limit (17→20 tests, **84%** coverage)
- Docs: `architecture.md`, `decisions.md` (ADRs), `api.md`, `specs/NFR.md`, quality gates in `Makefile`
- Multi-stage Dockerfile (build/runtime separation, non-root `siddha` user)

### Fixed
- CI failed on a clean runner: `config.py` assumed a developer `~/.env` — key now resolves env → `~/.env` → `./.env` with an actionable error
- Chromium runner had no `ffmpeg`; missing decoder now returns typed **503** and is surfaced by `/api/health` instead of a raw 500
- `/api/health` resolved `data/` relative to CWD — now anchored to the source directory, so it works from any launch dir
- TTS read raw government text (slashes, brackets, ₹) — now voice-safe `<pauses>` rendering via Timbre v3
- Temp WAVs leaked after each STT call — now always `finally`-deleted
- Raw provider 5xx accepted as success — now trips breaker via `ConnectionError` conversion
- Answers rendered via `innerHTML` (built-in XSS risk) — now `textContent`
- 422 responses leaked raw pydantic internals — now typed envelope

## [1.0.0] - 2026-11-04
### Added
- Opt-in eligibility reasoner (`src/eligibility.py`, `src/llm.py`): profile extraction + record-coverage classification via any OpenAI-compatible endpoint (e.g. DeepSeek), answers the "am I eligible?" gap; strict fallback to grounded templates when unconfigured; fully mocked tests (`tests/test_eligibility.py`)

- Initial Siddha: mic → Prisma STT → FAISS+BM25/RRF RAG over 1,142 myScheme scholarships → Hinglish Timbre TTS
- Grounded, template-composed answers (zero hallucination), Hinglish-first
- Offline corpus tooling: `prepare_corpus.py`, `build_index.py`
