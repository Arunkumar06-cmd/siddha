# Siddha — a voice-first scholarship guide for India

**One-liner:** Ask about a government scholarship in Hinglish, Hindi or Tamil, and Siddha answers out loud with the exact scheme, the documents you need, and where to check the current deadline.

**The problem.** MyScheme lists 1,142 scholarship schemes. The students who need them most — often first-generation, cost-sensitive, and more comfortable in their own language than in English forms — have no usable way to find out which scheme fits them. The portals are text-heavy, form-first, and incomplete. So legitimate students leave money on the table because we never tell them it exists.

**What Siddha does.**
- You tap a mic and ask, naturally.
- Gnani **Prisma v3.0** transcribes the code-mixed speech.
- Siddha retrieves the closest scheme records from a local FAISS + BM25 index (BGE-M3 multilingual embeddings, RRF fusion) over the official myScheme corpus.
- A grounded responder composes the answer — eligibility, benefit, documents, where to apply — strictly from those records. Nothing is generated from outside knowledge; if it can't ground it, it says so instead of inventing it.
- Gnani **Timbre v3.0** speaks the answer back in the same language.
- Follow-ups keep the thread: “Aur last date kya hai?” resolves to the scheme just discussed, and the UI shows the carried scheme. A new scheme name or state still retrieves fresh.
- The UI shows sources next to the answer, so it's auditable rather than magical.

**Why this is different from a translation wrapper.** Siddha's job is not "read the portal in Hindi." It's to answer: *which* scholarship applies, *what* it needs, and *where* to apply — from a corpus that already exists but is invisible to most people. There are also honest measures: the docs include retrieval evals (recall@1 0.53 → 0.67, recall@5 0.73 → 0.77, MRR 0.63 → 0.73), noise-test WER (100% transcription on 12 clean utterances; 11/12 critical terms preserved on 8 kHz telephony with traffic/fan noise), and a Tamil-script roundtrip (`detected_language_code=ta-IN`, 0.14 s).

**What it is honestly.** Not a form-filler, not an eligibility automator, not a lawyer. It's a reliable, grounded, voice-accessible front door to 1,142 government scholarships — built around the idea that eligibility answers should be assembled from official records, not from a language model's memory.

**Tech.** Python, FastAPI, FAISS + BM25 retriever (BGE-M3 embeddings), RRF fusion, Docker, GitHub Actions, 63 tests, 86% coverage. Voice path: Prisma STT → retrieval → grounded responder → Timbre TTS.

**Target lane.** Mixed Vibes (best code-mixed Hinglish build) with a Real Deal framing (real impact for students who rarely get told).

**Links.** Repo: https://github.com/Arunkumar06-cmd/siddha — Release v2.2.0 (2-minute demo video attached): https://github.com/Arunkumar06-cmd/siddha/releases/tag/v2.2.0
