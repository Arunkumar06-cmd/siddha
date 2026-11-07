# RESEARCH INVENTORY — Gnani Great Indian AI Internship Challenge
As of 2026-11-04 | Goal: strongest problem → strongest solution, with papers & repos

## 1. Problem evidence (V)
- **NSP 2025-26 live dashboard** (NSP dashboard: [scholarships.gov.in](https://scholarships.gov.in/)): 26.01 lakh applications received; ~22.5L verified; **₹2,081 crore disbursed**. OBC = 10.17L (received) this AY; SC 6.15L; ST 6.02L; General 3.67L. Female post-matric = 11.05L of applications.
- **Haryana committee report (Feb 2026)**: thousands of post-matric applications pending *per district*; top reasons = **Aadhaar-bank not linked**, student/institute verification pending.
- **IDR (Jun 2025)**: marginalized students can't access scholarships — cluttered sites, low digital literacy, language barrier; small mistakes cost the money.
- **IJFMR (Aug 2025)**: ST students face language + digital-literacy barriers; ventures in English-only platforms exclude vernacular-medium students.
- **PIB/MoE**: NSP OTR mandatory; verification levels L1 (institute) → L2 (district) → L3 (state/ministry) — a single approval miss kills the application.

## 2. The single most directly-on-point paper (V)
**"First Impressions from Comparing Form-Based and Conversational Interfaces for Public Service Access in India"** — Chaitra C R et al., HCINLP 2025, pp. 60–71 (ACL Anthology 2025.hcinlp-1.6).
- Prabodhini (voice-first RAG over myScheme data) **beat myScheme (form-based)** for 15 low-income emergent users on usability, task completion time, preference.
- Voice aligns with emergent users' mental models (Zipf's Law of Least Effort; Gulf of Execution).
- Designed WITH 15 low-income users (user-centred process). This is the exact target user class for a scholarship voice assistant.

## 3. Adjacent papers (V)
- **IndicVoices** (ACL 2024, Manuel et al.) — 7,348 hrs, 16,237 speakers, incl. government-services voice intents (Umang-style), 22 languages, 8 kHz telephony channel. Use as motivation/eval context.
- **IndicParam** (EMNLP 2026) — even best LLMs ~58% on low-resource Indic MCQ; LLMs are weak in Governance/Law domains — argues for retrieval-grounding, not free-generation.
- **IWSLT 2025 Indic track** — cascaded ASR+NLLB systems best for low-resource Indic STT; supports cascaded architecture over end-to-end.
- **VoiceAgentBench** (Krutrim, 2025) — voice agents weak on Indic agentic tasks; motivates tight tool-calling with few intents.
- **FinTech multi-agent paper** (2512.01439) — multi-agent: language classification → function management → multilingual response; improved engagement, low latency.
- **SUKHSANDESH** (45058) — avatar + regional voice QA for rural health; shows voice-first works for sensitive low-literacy domains.

## 4. Repos & datasets (V)
**Datasets**
- myScheme: dataset on Kaggle (updated-Sep-2026 CSV, ~58 MB) — 4,700+ schemes Central+State; **HuggingFace `shrijayan/gov_myscheme`** (structured, 1,678 downloads last month, Apache-2.0) + **Kaggle `indian-government-schemes`** (12.86 MB)
- NSP: no public structured dataset; FAQ + scheme pages per ministry (160 schemes, 16 ministries)
- **MyScheme public API** (undocumented, in Next.js): api.myscheme.gov.in/schemes/v6/public/schemes?slug=&lang= — needs captcha/anti-bot measures, use Kaggle CSV instead

**Repos (idea precedent)**
- `ksm26/Multilingual-Vernacular-Voicebot-with-RAG` — Hindi/Punjabi/Tamil/Bengali RAG voicebot for schemes/banking/agriculture; Whisper + IndicLID + Flan-T5 + IndicTrans2
- `Ujwal-Jawalgi/Voice-Enabled-RAG` — Next.js + FastAPI, Sarvam saarika, 700k FAISS chunks, RRF fusion, latency dashboard, Groq LLM
- `bharat-vicky/indic-voice-rag-assistant` — 11 Indian languages, chunk 1000/200 overlap, FAISS, webm→wav ffmpeg pipeline
- `ShivaTeja05/Speech-to-Speech-model` — FastAPI 8-stage pipeline, VAD + Whisper + RAG + Llama-3.1-8B
- `mrigankad/Sakura-Voice` — VAD turn-taking, 17 Indic languages, fully-offline mode
- Gnani-published cookbook: **Call Analytics pipeline**, **Real-time compliance monitoring**, LiveKit/Pipecat plugins

## 5. Technical inventory for the build
**AI building blocks**
- STT: Gnani Prisma v3.0 (Indic, code-mixed, indic-auto, keyterms, topic hint, 504≈5s budget)
- TTS: Gnani Timbre v2.5 (42 voices incl. Hinglish `Poorvi`) / v3.0 (13 voices, all-10 languages, audio tags)
- LLM: Evon v3.3 unavailable via API; hosted substitutes — Groq (fast llama), Google AI Studio (free Gemini), OpenRouter (free); or local Ollama+Qwen2.5-7B (laptop GPU? likely not)
- Embeddings: multilingual — `BAAI/bge-m3` (100+ languages, code-mixed-friendly)
- Vector store: FAISS (in-process) — 700k myScheme chunks ≤ few GB RAM
- Reranker: BM25 + dense, RRF fusion (per Voice-Enabled-RAG pattern)
- Guardrail: refuse when out-of-scope; system prompt "I don't know, visit [scholarships.gov.in](https://scholarships.gov.in/)"
- Latency: streaming TTS (SSE/WebSocket); VAD via Silero; turn-taking

**Frontend/backend**
- FastAPI backend (Python 3.11+) + simple web PWA (mic via MediaRecorder) or Streamlit for speed
- Streaming audio to both directions: record→webm→ffmpeg→16k wav→STT; TTS→autoplay

**Scholarship/GOV data engineering**
- Kaggle myScheme CSV → filter `categories ⊃ scholarship/Education` (~150-300 schemes) + NSP FAQ + NSP common rejections (adhaar–bank link, INO pending)
- Schema per scheme: name, ministry, eligibility (income/category/state/course), benefit, last date, apply link
- Multilingual answers: generate Hindi/Tamil/… templates OR translate myScheme fields with IndicTrans2 (Apache open model) or LLM translation

**Product layer**
- Voice persona: "Sathi/Siddha" (friend) — warm, Hinglish-first, then Hindi/Tamil/English
- Auto keyterms: inject `["OTR","NSP","Aadhaar","DBT","PFMS","SC","ST","OBC","affidavit"]` to Prisma
- Demo script — enrollment state: user speaks "meraa haath mein scholarship ka form hai..." → bot reads eligibility, tells documents, warns about Aadhaar-bank link, opens application link

## 6. Judging realities (unchanged)
Engagement on nominated post > demo quality > technical sophistication. 60-90s demo, Hinglish narrative, tag @GnaniAI.

## 7. Proposed "big" WBS (7 packages)
P1. Data ingestion pipeline (myScheme CSV → scholarship subset + NSP FAQ JSON) — 3-4 h
P2. Multilingual readable schema (name/eligibility/docs/dates in Hindi + English) — 3 h
P3. RAG core (chunking 800/150, FAISS, BGE-M3, BM25+RRF) — 4 h
P4. Voice loop (mic→webm→ffmpeg→Prisma→retriever→LLM→Timbre→autoplay, streaming) — 4 h
P5. Guardrails + latency budget (Silero VAD, 30s cap, refusal path) — 2 h
P6. Demo + video + post (60-90 s, Hinglish) — 3 h
P7. Submission + interview prep — 1 h
Total ≈ 20-24 h over 6 days — feasible solo.
