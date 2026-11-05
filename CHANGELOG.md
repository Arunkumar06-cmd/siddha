# Changelog
All notable changes to Siddha. Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]
### Added
- Opt-in eligibility reasoner (`src/eligibility.py`, `src/llm.py`): profile extraction + record-coverage classification via any OpenAI-compatible endpoint (e.g. DeepSeek), answers the "am I eligible?" gap; strict fallback to grounded templates when unconfigured; fully mocked tests (`tests/test_eligibility.py`)

- BGE-M3 index rebuilt (512-token max sequence, fp32/MPS) — replaces MiniLM-L12 for multilingual/code-mixed retrieval
- `docs/eval-audio.md`: telephonic/noise robustness probe (8 kHz, traffic/fan) with critical-term preservation and honest caveats
- `scripts/eval_retrieval.py`: 30-query labeled retrieval evaluation (recall@1, recall@5, MRR) for verifiable comparisons
- `scripts/eval_audio.py`: reproduces the telephonic/noise probe end to end

### Changed
- Retrieval: **state-aware routing** shipped — a query naming a state/UT now ranks that state's schemes first (1.35/0.75 boost/suppression); `central government` queries filter to Central; a state-less query gets a 1.2 Central multiplier. Fixes the Bihar-instead-of-Central regression visible in the demo query (v2.3 content, delivered early)
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
- 54.9 s demo video (`docs/demo.mp4`, 1080×1080): a real Prisma STT → hybrid retrieval → Timbre TTS turn, with Avinash asking the Hinglish question and Shivani answering
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
