# Submission — Siddha

> Voice-first guide to 1,141 Indian government schemes, mostly education and welfare (236 are named scholarships). Ask in Hinglish, Hindi or Tamil; hear the exact scheme, the documents you need, and where to check the current deadline.

## Form-ready answers

- **Project URL (one-page pitch):** https://github.com/Arunkumar06-cmd/siddha/blob/main/docs/pitch.md
- **Demo video (139 s, two turns — fits X’s 140 s cap) — watch in browser:** https://arunkumar06-cmd.github.io/siddha/
  - Download current master: https://raw.githubusercontent.com/Arunkumar06-cmd/siddha/main/docs/demo.mp4
- **Problem:** 1,141 government schemes are published on myScheme (694 in education), but the students who need them most cannot find the right one through English, form-first portals. Siddha makes discovery voice-first in Hinglish, Hindi and Tamil — and keeps a follow-up on the same scheme.
- **Gnani models/APIs:** Prisma v3.0 STT (`indic-auto`, `codemix`); Timbre v3.0 TTS (Shivani, `hi-en`).
- **Who uses it:** students, first-generation families, school and college counsellors, scholarship helpdesks.
- **Contribution:** solo — corpus, retrieval, grounded responder, context layer, voice loop, UI, tests, CI, docs, demo.
- **Repository:** https://github.com/Arunkumar06-cmd/siddha

## Personal details (from registration)

- **Full name:** Arunkumar K
- **Registered email ID:** 127156014@sastra.ac.in
- **Institution:** Sastra Deemed University

The final submission form is emailed to this registered address after registration; check that inbox and spam.

## Award lane and target users

**Lane: Mixed Vibes** — the best code-mixed Hinglish voice build. Siddha is Hinglish-first end to end: code-mixed listening (Prisma `indic-auto`/`codemix`), Hinglish-shaped grounded answers, and a code-mixed voice (Shivani) delivering them. Secondary framing: **Real Deal** — an information deficit India already pays for in unclaimed scholarships; Siddha removes it for the student who needs it most. Robustness numbers and the Tamil roundtrip are evidence, not decoration: see `docs/eval-audio.md` and the Tamil probe (Prisma detect `ta-IN`, 0.14 s, verbatim transcript of a Tamil-script question answered from the corpus).

## The problem

India publishes 1,141 government schemes on myScheme, 694 of them in education. The students who need them most are often the least served by an English, form-first web portal. Discovery is a language and interface problem, not only a data problem.

## What Siddha does

1. The student taps the mic and asks naturally — “SC students ke liye central government post matric scholarship ke documents kya chahiye?”
2. **Gnani Prisma v3.0** transcribes the code-mixed speech (`indic-auto`, `codemix`).
3. Hybrid retrieval (BGE-M3 multilingual embeddings + FAISS + BM25, fused with RRF) finds the most relevant official scheme records.
4. A grounded responder composes the answer from those records — eligibility, benefit, documents, application route — with no free-form generation. If the chosen scheme belongs to a State and the question named none, the reply says which state it is.
5. **Gnani Timbre v3.0** speaks the reply in the student's language, with voice-safe prose (`<pauses>`, no slashes, URLs or currency symbols read literally).

A deterministic session layer keeps the scheme on the table. A follow-up that names only an aspect (“Aur is scheme ki last date kya hai?”) is answered from the same record with no new retrieval; a follow-up that adds a state or category re-retrieves with the previous scheme as an anchor; a new scheme name is treated as a new topic. Sessions are text-only, in-memory, 30-minute TTL, with a 500-session cap.

The UI shows the transcript, the spoken answer, the carried scheme when context is used, and the retrieved sources, so the answer is inspectable.

## Gnani models / APIs used

| Purpose | Model | API | Settings |
|---|---|---|---|
| Speech-to-text | **Prisma v3.0** (`prisma-v3.0`) | `POST https://api.vachana.ai/stt/v3` | `language_code=indic-auto`, `format=codemix` |
| Text-to-speech | **Timbre v3.0** (`timbre-v3.0`) | `POST https://api.vachana.ai/api/v1/tts/inference` | voice `Shivani`, language `hi-en`, 16 kHz mono WAV |

**Optional third-party reasoning (disclosed, auditable, off by default):** eligibility questions (e.g. "eligible hun kya?") route through an LLM classifier — any OpenAI-compatible endpoint, e.g. DeepSeek's free API — that *extracts a structured profile and classifies record coverage*. It never speaks freely: verdicts must quote the record verbatim, code composes the reply, and **any failure — congestion, timeout, empty verdict — falls back to the original grounded templates silently.** A live eligibility verdict is a bonus; the demo never depends on the endpoint's availability. No LLM is involved in the standard spoken answer path unless `LLM_API_KEY` is set. Gnani calls remain the only *voice* inference calls.

## Architecture

- **Robustness (docs/eval-audio.md):** 12 Hinglish scholarship utterances × telemetry conditions. Prisma transcribed 100% of utterances; 11/12 kept every critical term even on band-passed 8 kHz telephony with traffic/fan noise (the misses are Devanagari-script transcripts of correct content).
- **Serving:** single-process FastAPI, vanilla HTML/JS mic UI.
- **Audio:** ffmpeg normalises browser webm/opus to 16 kHz mono WAV, deletes the temp file in `finally`.
- **Retrieval:** prebuilt FAISS index + BM25 over `data/scholarships.jsonl` (1,141 records); RRF fusion; top-5 records.
- **Answering:** aspect classification (documents / eligibility / benefit / apply / renewal / status / deadline) and template composition strictly from retrieved fields; aspect-only follow-ups reuse the last scheme and skip retrieval.
- **Voice safety:** number, currency, URL, slash and bracket normalisation; comma-separated document lists; word-boundary truncation; dangling-preposition removal.
- **Resilience:** retries with backoff + jitter on timeout/connection/5xx, circuit breakers for STT and TTS, per-IP rate limit, global and per-visitor Gnani credit budgets enforced before each provider call, a streaming cap on audio uploads, typed error envelope, `/api/health` corpus check, `/api/ready` warm-up probe, `/api/metrics`.
- **Delivery:** multi-stage Docker image, non-root user, CI (ruff, compile, 227-test suite, 80% coverage gate, four-set retrieval/confidence regression gate, gitleaks, Docker build + smoke run) and a security workflow (`gitleaks`, `pip-audit` with explicit, documented ignores).

## Why it is not a mockup

- 227 tests in the suite; 224 passed locally, with three model-backed retrieval tests blocked by the unavailable BGE-M3 cache. The runnable suite measured 90.26% coverage; ruff is clean.
- The demo is a screen recording of the running service: two questions are played into Chrome as microphone input, then the real Prisma STT → retrieval → grounded responder → Timbre TTS path produces each transcript and audio in the recording.
- The two student questions (“SC students ke liye central government post matric scholarship ke documents kya chahiye?” and “Aur is scheme ki last date kya hai?”) are synthesized with Timbre (voice **Avinash**) so the recording is reproducible without a human caller; the answers use the product voice **Shivani**. The corrected opening and evaluation narration were also generated with Gnani Timbre v3.0 (voice **Shivani**). All spoken parts are synthetic.
- The API key is never in the repo or the image; it is resolved from the environment or `~/.env`.

## Solo contribution

Designed and built solo: corpus pipeline, retrieval, grounded responder, voice-safety layer, FastAPI service, mic UI, resilience layer, tests, CI/security, docs, and the demo video.

## What I would build next

- Live deadline/status refresh from official sources instead of pointing to the portal.
- A public Hugging Face Space (Dockerfile is ready; needs a Space secret).
- More languages, noisy-telephony evaluation, and a human study with students.
- An IVR/telephony channel for students without smartphones.

## Links
- One-page pitch (use this for the submission form's Project URL): https://github.com/Arunkumar06-cmd/siddha/blob/main/docs/pitch.md

- Repository: https://github.com/Arunkumar06-cmd/siddha
- Code release v2.2.0: https://github.com/Arunkumar06-cmd/siddha/releases/tag/v2.2.0
- Current demo video (139 s, two turns — watch in browser): https://arunkumar06-cmd.github.io/siddha/ (download the current main-branch file: https://raw.githubusercontent.com/Arunkumar06-cmd/siddha/main/docs/demo.mp4)
- Architecture: https://github.com/Arunkumar06-cmd/siddha/blob/main/docs/architecture.md
- API reference: https://github.com/Arunkumar06-cmd/siddha/blob/main/docs/api.md
- LinkedIn post: _add after posting_
- X post: _add after posting_

---

## Post copy

### LinkedIn (attach `docs/demo.mp4`)

> India's myScheme portal lists 1,141 government schemes, 694 of them for education. Many students never hear which one fits them.
>
> The rules exist, but they sit behind English forms, dropdowns, and PDFs that most students will not open. I built Siddha to make that search voice-first.
>
> Ask in plain speech: “SC students ke liye post matric scholarship ke documents kya chahiye?” Siddha replies with the matching scheme, the documents, and where the current deadline lives. It understands Hindi and Tamil input; replies today are in Hinglish.
>
> What it uses:
> • Gnani Prisma v3.0 for STT on code-mixed speech (indic-auto, codemix)
> • FAISS + BM25 over the official myScheme corpus, fused with RRF (BGE-M3 multilingual embeddings)
> • Answers assembled from official records — no invented eligibility, no made-up deadlines
> • Follow-up context — ask “aur last date?” and Siddha stays on the same record
> • Gnani Timbre v3.0 (Shivani) for the spoken reply
>
> Built solo for the Great Indian AI Internship Challenge — I'm in the Mixed Vibes lane: code-mixed both directions. This is a two-minute recording of the real pipeline, with a live follow-up.
>
> Tagging @gnani.ai. Code: https://github.com/Arunkumar06-cmd/siddha
>
> #GnaniAI #GreatIndianAIInternshipChallenge

**Tagging:** type `@` and select the official **gnani.ai** company page. A plain `@gnani.ai` string may not link.

### X (attach `docs/demo.mp4`; repo link in the first reply)

> Many Indian students miss scholarships they qualify for because the rules are buried in portals.
>
> Siddha lets you ask in Hinglish, Hindi, or Tamil and hear the scheme and documents, grounded in 1,141 records.
>
> Built with @GnaniAi Prisma + Timbre.
> #GnaniAI #GreatIndianAIInternshipChallenge

**Reply:** Full code, architecture, and a 2-minute walkthrough: https://github.com/Arunkumar06-cmd/siddha

---

## Posting checklist

- [x] Register — done (email from Team Gnani AI, Nov 4; registration confirmed, 5,000 programme credits, 3 free API keys, closing date Nov 10, 23:59 IST).
- [x] Working app + release cut — Siddha v2.2.0 published with demo attached
- [x] Keys claimed and usage confirmed — live Prisma STT and Timbre TTS calls return 200
- [ ] Attach `docs/demo.mp4` (1080×1080, 139 s, 6.4 MB; also fits X’s free-account 140 s cap).
- [ ] Tag the official account: **gnani.ai** on LinkedIn, **@GnaniAi** on X.
- [ ] Include both hashtags exactly: `#GnaniAI` `#GreatIndianAIInternshipChallenge`.
- [ ] Post publicly **as early as possible** — shortlisting verifies reactions, comments and reshares, and only engagement before the cutoff counts.
- [ ] Copy both post URLs into the workspace submission.
- [ ] Nominate one post per platform.
- [ ] Submit before **10 November 2026, 11:59 PM IST** (no extensions).

## Workspace submission fields

From the participation terms, the workspace asks for:

1. The problem the project addresses.
2. The Gnani AI models or APIs used (Prisma STT, Timbre TTS — see the table above).
3. Who will use it (students, counsellors, scholarship helpdesks).
4. Each member's contribution (solo build — all components).
5. Demo or video link.
6. Written project explanation.
7. LinkedIn and/or X post links, with one nominated post per platform.
