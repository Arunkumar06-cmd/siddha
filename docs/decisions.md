# Architecture Decision Records

## ADR-001: Grounded template composer over LLM generation
**Date:** 2026-11-04 · **Status:** accepted
**Context:** Judging is reliability + clarity, not lyrical prose. An LLM could fabricate eligibility or deadlines — dangerous and disqualifying in a public demo.
**Decision:** Compose answers from retrieved scheme records only; LLM slot left as opt-in escape hatch requiring an explicit key.
**Consequences:** Zero hallucination; template-y phrasing accepted.

## ADR-002: ECC-free offline corpus build vs live scrape
**Date:** 2026-11-04
**Context:** myScheme blocks scraping (CAPTCHA); but Kaggle hosts the April 2025 dump (updated 13 Jul 2025, 3,400 rows).
**Decision:** Use the Kaggle dump → `scholarships.jsonl` (1,142 scholarship/education schemes, deterministic). No runtime dependency.
**Consequences:** Corpus is a snapshot, update via `src/prepare_corpus.py` when upstream changes.

## ADR-003: MiniLM-L12 (384d) for embeddings
**Date:** 2026-11-04
**Context:** Need multilingual (Hinglish/Hindi/Tamil) vectors that run on CPU in <1 s for 1,142 docs.
**Decision:** `paraphrase-multilingual-MiniLM-L12-v2` — 384d, ~118 MB, CPU.
**Consequences:** Fast & cached; no GPU requirement; retrieval quality good enough over a small corpus.

## ADR-004: Circuit breaker + retry over raw retries
**Date:** 2026-11-04
**Context:** Gnani API is a paid voice API (5,000 credits); blind retries on a dead provider burn money and wall-clock.
**Decision:** Retry on Timeout/ConnectionError/5xx only, then open breaker for 60 s after 5 consecutive failures. 4xx never retried.
**Consequences:** Bounded cost; transient blips survive; sustained outage fails fast (no stack traces leaked).

## ADR-005: No secrets in repo — `~/.env` only, `.env` never committed
**Date:** 2026-11-04
**Context:** The user's working key must stay local; repo is public.
**Decision:** `/Users/arunkumar/.env` is the runtime source; `.env.example` documents variables; `.gitignore` enforces; gitleaks runs in CI.
**Consequences:** Public repo is clean by construction.

## ADR-006: Rate limit 30/min/IP in-memory
**Date:** 2026-11-04
**Context:** Demo needs protection from accidental double-POST storms; shared demo wouldn't survive unbraked public traffic anyway.
**Decision:** In-memory token bucket; bounded to 30/min/IP; returns 429 with typed error.
**Consequences:** Per-process only (documented ceiling in specs/NFR.md); survives demo traffic.

## ADR-007: Local parameter server (172.x) NOT used without explicit consent
**Date:** 2026-11-04
**Context:** A local OpenAI-compatible endpoint exists on this machine (172.16.13.91:8050). The owner pasted keys only implicitly; consent not yet granted for building against it.
**Decision:** Default = grounded templates, zero LLM calls. Any LLM use requires explicit owner approval.
**Consequences:** Safest default; nothing silently burns private compute.

## ADR-008: torch 2.12.1 over 2.13.0 (PYSEC-2025-194)
**Date:** 2026-11-04 · **Status:** accepted-risk
**Context:** pip-audit flags torch 2.12.1 (fix: 2.13.0). This machine's toolkit hard-pins `torchvision==0.27.1 → torch==2.12.1`; upgrading torch breaks the resolver for the rest of the Anaconda env.
**Decision:** Pin `torch==2.12.1`. Saathi feeds only a local, trusted corpus through the `MiniLM-L12` encoder; no untrusted tensor/model inputs reach torch ops at request time. Revisit when torchvision releases a 2.13-compatible pin.
**Consequences:** One advisory accepted; re-audit on any torchvision bump.

## ADR-009: setuptools 81.0.0 (env-level advisory)
**Date:** 2026-11-04 · **Status:** accepted-risk
**Context:** pip-audit flags setuptools 81.0.0 (fixes require ≥83). `torch==2.12.1` hard-requires `setuptools<82` — upgrading breaks torch. setuptools is a build/install tool, not a runtime path.
**Decision:** Defer; not in request path. Re-check on the coordinated torch+torchvision bump.
**Consequences:** Documented accepted-risk; silence CI does not — advisory visible in CI logs.
