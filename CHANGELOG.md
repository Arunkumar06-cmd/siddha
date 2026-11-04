# Changelog
All notable changes to Siddha. Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]
### Changed
- Product renamed **Saathi → Siddha** across app, docs, env vars (`SIDDHA_*`), Docker user, and repo
- README now shows a real UI screenshot instead of the hand-drawn SVG diagram
- README hero: centred title and positioning line, logo badges with `logoColor=white`, native GitHub alerts, Mermaid architecture in a collapsible block
- Demo screenshot converted to a 95 KB WebP (under the 200 KB README asset budget)

### Fixed
- `LICENSE` contained only a header line, so GitHub reported "license not identified" — now the full MIT text

### Added
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
- Initial Siddha: mic → Prisma STT → FAISS+BM25/RRF RAG over 1,142 myScheme scholarships → Hinglish Timbre TTS
- Grounded, template-composed answers (zero hallucination), Hinglish-first
- Offline corpus tooling: `prepare_corpus.py`, `build_index.py`
