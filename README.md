<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&section=header&height=180&color=0:22C1A0,100:FF8A00&text=Siddha&fontSize=64&fontAlignY=38&desc=Voice-first%20scholarship%20guide%20for%20India&descSize=17&descAlignY=63&fontColor=071926&animation=fadeIn" alt="Siddha — voice-first scholarship guide for India" width="100%" />
</p>

<div align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Inter&weight=600&size=21&pause=1000&color=22C1A0&center=true&vCenter=true&width=760&lines=Ask%20in%20Hinglish%2C%20get%20the%20exact%20scholarship;Grounded%20in%201%2C142%20official%20myScheme%20schemes;Powered%20by%20Gnani%20Prisma%20%2B%20Timbre" alt="Ask in Hinglish, get the exact scholarship — grounded in 1,142 official myScheme schemes — powered by Gnani Prisma + Timbre" />
</div>

<p align="center">
  <b>A voice-first scholarship guide for India.</b><br/>
  Ask in Hinglish, Hindi or Tamil. Get the exact scheme, the documents you need, and where to check the current deadline — spoken back in your language.
</p>

<p align="center">
  <a href="https://github.com/Arunkumar06-cmd/siddha/actions"><img src="https://img.shields.io/github/actions/workflow/status/Arunkumar06-cmd/siddha/ci.yml?branch=main&style=for-the-badge&logo=githubactions&logoColor=white" alt="CI status"></a>
  <a href="https://github.com/Arunkumar06-cmd/siddha"><img src="https://img.shields.io/badge/tests-63%20passing-22c1a0?style=for-the-badge&logo=pytest&logoColor=white" alt="63 tests passing"></a>
  <a href="https://github.com/Arunkumar06-cmd/siddha"><img src="https://img.shields.io/badge/coverage-86%25-22c1a0?style=for-the-badge&logo=codecov&logoColor=white" alt="Coverage 86%"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11%2B-ffb84d?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/github/license/Arunkumar06-cmd/siddha?style=for-the-badge&logo=opensourceinitiative&logoColor=white" alt="MIT license"></a>
  <a href="#roadmap"><img src="https://img.shields.io/badge/version-2.2.0-ff8a00?style=for-the-badge&logo=git&logoColor=white" alt="Version 2.2.0"></a>
</p>

<img src="https://capsule-render.vercel.app/api?type=wave&color=0:22C1A0,100:FF8A00&height=42" width="100%" alt="" />

> [!IMPORTANT]
> **No hallucinated eligibility.** Every answer is assembled from 1,142 official myScheme scholarship records. Siddha never invents a deadline, amount, or required document.

![Siddha — ask by voice, get a grounded scholarship answer](docs/demo.webp)

<p align="center">
  <a href="./docs/demo.mp4"><b>▶ Watch the 2-minute demo</b></a>
  &nbsp;·&nbsp;
  <a href="./docs/architecture.md">Architecture</a>
  <br/>
  <sub>Real UI, two live Gnani Prisma + Timbre turns; the second is a follow-up with no scheme name repeated.</sub>
</p>

## Table of contents
- [Features](#features)
- [Quick start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
- [API reference](#api-reference)
- [Project structure](#project-structure)
- [Contributing](#contributing)
- [Roadmap](#roadmap)
- [License](#license)

## Features
- **Voice-in, voice-out.** Browser mic → Prisma STT → retrieval → Timbre TTS. No chat box required.
- **Grounded answers, not generative ones.** The answer is assembled from 1,142 official myScheme records. If a fact isn't in the corpus, Siddha doesn't invent it. The UI shows the sources it used.
- **Conversation, not cold starts.** A follow-up like “Aur last date kya hai?” resolves against the scheme already on the table; a new scheme name or a new state still retrieves fresh. Sessions are text-only, in-memory, and expire after 30 minutes. The UI shows the carried scheme, so context is visible, not guessed.
- **States stay in their lane.** A state-specific question gets that state's schemes first; a national question gets Central schemes. When a State scheme is chosen for a state-less query, it's named as one.
- **Eligibility questions work too.** Ask "qualify hun kya?" and Siddha checks your profile against the actual record text — the verdict includes the line it matched. Opt-in via any OpenAI-compatible endpoint (e.g. a free DeepSeek key). Without a key the original grounded path answers unchanged.
- **Survives call-quality audio.** 12 code-mixed utterances on 8 kHz band-passed telephony with traffic and fan noise: Prisma transcribes all 12; 11/12 keep every critical term (`docs/eval-audio.md`).
- **Tamil is native, not bolted on.** A Tamil-script question roundtrips in 0.14 s with `detected_language_code=ta-IN`.
- **Retrieval that mixes two signals.** BGE-M3 multilingual embeddings for semantic match, BM25 for exact keywords, fused with reciprocal rank fusion.
- **Hinglish-first** — answers are shaped for Indian code-mixed speech, not translated English.
- **Cheap to run.** One turn = exactly 2 Gnani calls (one STT, one TTS). Roughly 2,500 full voice turns per 5,000 programme credits.
- **Crash-safe** — circuit breakers, retry with backoff+jitter, per-IP rate limits, typed errors.

## Quick start
```bash
git clone https://github.com/Arunkumar06-cmd/siddha.git
cd siddha
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # ~10 min on CPU torch
python -m uvicorn server:app --host 127.0.0.1 --port 8765
```
Open http://127.0.0.1:8765 — tap the mic, ask in Hinglish.

> [!NOTE]
> `GNANI_API_KEY` must exist in `~/.env` or the environment before startup. It never ships in the repo or the Docker image.

## Installation
**Prerequisites:** Python 3.11+, macOS/Linux, ffmpeg on PATH, ~2 GB free disk (CPU torch), a valid `GNANI_API_KEY` from [app.gnani.ai](https://app.gnani.ai/).

```bash
pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
```

Environment variables (put in `~/.env` locally; never commit):

| Variable | Required | Description | Default |
|---|---|---|---|
| `GNANI_API_KEY` | yes | Key from app.gnani.ai → API keys (scope: `STT`, `TTS`) | — |
| `SIDDHA_HOST` | no | Bind address (`0.0.0.0` exposes the LAN) | `127.0.0.1` |
| `SIDDHA_PORT` | no | Port | `8765` |
| `SIDDHA_RATE_LIMIT` | no | Requests per minute per IP | `30` |

## Usage

Text question via curl (no mic needed):

```bash
curl -s -X POST http://127.0.0.1:8765/api/ask_text \
  -H 'Content-Type: application/json' \
  -d '{"text":"scholarship ke liye kaunse documents chahiye"}'
```

Voice question via MediaRecorder POST (see `static/index.html`):

```bash
curl -s -X POST http://127.0.0.1:8765/api/ask_audio \
  -F 'audio=@question.wav;type=audio/wav'
```

```diff
+ The response contains transcript, reply, sources[], and audio_wav_b64 (base64 WAV).
```

> [!TIP]
> No microphone? `/api/ask_text` runs the same retrieval and voice synthesis path without STT.

## API reference

| Endpoint | Method | Purpose | Body |
|---|---|---|---|
| `/api/ask_text` | POST | RAG answer | `{"text": "...", "session_id": "..."}` (2–500 chars) |
| `/api/ask_audio` | POST | Voice STT→RAG→TTS | multipart `audio` ≤ 8 MB + optional `session_id` |
| `/api/session/{id}` | GET | Restore the last turn: transcript, reply, sources, context | — |
| `/api/session/{id}` | DELETE | Start a new conversation | — |
| `/api/health` | GET | Liveness + corpus check (503 if degraded) | — |
| `/api/metrics` | GET | Counters + circuit state | — |

## Project structure
```
.
├── server.py            # thin routes layer (FastAPI)
├── src/
│   ├── pipeline.py      # mic→ffmpeg→Prisma→RAG→Timbre (testable core)
│   ├── retriever.py     # FAISS + BM25 + RRF over myScheme corpus
│   ├── responder.py     # grounded answer composition
│   ├── context.py       # deterministic follow-up resolution
│   ├── conversation.py  # session memory (TTL + caps)
│   ├── spoken.py        # voice-safe prose (<pauses> for Timbre v3)
│   ├── resilience.py    # circuit breakers + retry/backoff
│   ├── config.py        # typed env config + logging
│   └── prepare_corpus.py / build_index.py  # offline corpus tools
├── static/index.html    # mic UI
├── data/scholarships.jsonl   # 1,142 schemes (extracted from myScheme)
├── data/scholarships.faiss   # prebuilt FAISS index
├── specs/NFR.md         # non-functional requirements (explicit)
├── tests/               # 63 tests, 86% coverage
├── docs/                # demo video, screenshot, architecture, ADRs, API
└── .github/workflows/   # CI + security
```

<details>
<summary><b>Architecture</b> — a voice turn, with follow-up context</summary>

```mermaid
flowchart LR
    A["Mic<br/>MediaRecorder"] -->|webm/opus| B["FastAPI<br/>/api/ask_audio"]
    B --> C["ffmpeg<br/>16 kHz mono WAV"]
    C --> D["Prisma v3.0<br/>indic-auto · codemix"]
    D --> E["Hybrid retrieval<br/>FAISS + BM25 → RRF"]
    F[("1,142 myScheme<br/>schemes")] --> E
    E --> G["Grounded responder<br/>templates, no generation"]
    G --> H["Timbre v3.0<br/>Shivani · hi-en"]
    H --> I["JSON + base64 WAV"]
```

A follow-up that names only an aspect (“aur last date?”) is answered from the record already on the table, with no additional retrieval. A follow-up with a new state or category re-retrieves with the previous scheme as an anchor; a new scheme name is treated as a new topic. The rules are deterministic and unit-tested in `tests/test_context.py`.

</details>

<details><summary>Advanced: self-host a public demo</summary>

Any Docker host works. For Hugging Face Spaces (free):
1. Create a Space → SDK: Docker.
2. Add repo as remote.
3. Space → Settings → **Secrets**: `GNANI_API_KEY`.
4. The Space runs on port 7860 (Dockerfile default). `/api/health` must be green.

Everything (model pre-download, healthcheck, non-root user) is baked in — no manual steps beyond the secret.
</details>

## Contributing
Fork → branch → `make lint test` → PR → CI green → 1 review. See [CONTRIBUTING.md](./CONTRIBUTING.md).

## Roadmap
- **Shipped (v2.2)** — grounded Hinglish voice loop, BGE-M3 hybrid FAISS + BM25 retrieval, state-aware routing, deterministic follow-up context, 2-minute demo
- **v2.3** — live deadline/status refresh from official sources; eligibility parsing from voice remains
- **v2.4** — opt-in LLM phrasing (grounded in retrieved records, requires a key); streaming TTS
- **v3.0** — voice-based form filling (auto-populate NSP fields from speech)

## License
MIT — see [LICENSE](./LICENSE).

*Built with FastAPI, Gnani Prisma/Timbre and FAISS by Arunkumar Karumbayiram.*

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://capsule-render.vercel.app/api?type=waving&section=footer&height=150&color=0:071926%2C55:0B2E3E%2C100:0C3344&text=Built%20with%20Gnani%20Prisma%20%2B%20Timbre&fontSize=24&fontAlignY=38&desc=Ask%20by%20voice.%20Answer%20from%20official%20data.&descSize=15&descAlignY=64&fontColor=EEF4F9&animation=fadeIn" />
  <img src="https://capsule-render.vercel.app/api?type=waving&section=footer&height=150&color=0:C7E9DF,55:F5E3CB,100:FFFFFF&text=Built%20with%20Gnani%20Prisma%20%2B%20Timbre&fontSize=24&fontAlignY=38&desc=Ask%20by%20voice.%20Answer%20from%20official%20data.&descSize=15&descAlignY=64&fontColor=071926&animation=fadeIn" width="100%" alt="Built with Gnani Prisma + Timbre — ask by voice, answer from official data" />
</picture>
