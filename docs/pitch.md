# Siddha — a voice-first scholarship guide for India

**One-liner:** Ask about a government scholarship in Hinglish, Hindi, or Tamil. Siddha answers out loud with the matching scheme, the documents you need, and where to check the current deadline.

**The problem.** MyScheme lists 1,141 government schemes, 694 of them in education and 236 named scholarships. Many of the students who need them are first-generation, cost-sensitive, or more comfortable in their own language than in English forms. The portals are text-heavy and form-first, so finding the right scheme takes effort many students cannot spare. The result is simple: eligible students miss scholarships they could use.

**What Siddha does.**
- You tap the mic and ask in your own words.
- Gnani **Prisma v3.0** transcribes the code-mixed speech.
- Siddha retrieves the closest scheme records from a local FAISS + BM25 index (BGE-M3 multilingual embeddings, RRF fusion) over the official myScheme corpus.
- A grounded responder composes the answer — eligibility, benefit, documents, where to apply — from those records only. It does not generate facts from outside knowledge. If it cannot ground a detail, it says so.
- Gnani **Timbre v3.0** speaks the answer back in Hinglish (`hi-en`). Hindi and Tamil are understood as input, but replies are Hinglish templates today.
- Follow-ups keep the thread: “Aur last date kya hai?” stays on the scheme just discussed, and the UI shows the carried scheme. A new scheme name or state retrieves fresh results.
- The UI shows sources next to the answer, so the response can be checked.

**Why this is different from a translation wrapper.** Siddha does not just read a portal in Hindi. It answers three questions from a corpus that already exists but is hard to find: *which* scholarship applies, *what* it needs, and *where* to apply. The docs include honest measures: four-set retrieval evals (30 hand-written Hinglish queries: recall@1 0.733, recall@5 0.767; all 1,141 names: recall@1 0.999; 400 ASR-damaged names: recall@1 0.682, recall@5 0.925; off-topic refusal 30/30), noise-test WER (100% transcription on 12 clean utterances; 11/12 critical terms preserved on 8 kHz telephony with traffic/fan noise), and a Tamil-script roundtrip (`detected_language_code=ta-IN`, 0.14 s).

**What it is.** Siddha is not a form-filler, an eligibility automator, or a lawyer. It is a grounded, voice-accessible front door to 1,141 government schemes, mostly education and welfare. Eligibility answers are assembled from official records, not from a language model's memory.

**Tech.** Python, FastAPI, FAISS + BM25 retriever (BGE-M3 embeddings), RRF fusion, Docker, GitHub Actions, 227 tests in the suite (224 locally passed; three model-backed retrieval checks need the BGE-M3 cache), 90.26% coverage on the runnable suite. Voice path: Prisma STT → retrieval → grounded responder → Timbre TTS.

**Target lane.** Mixed Vibes (best code-mixed Hinglish build) with a Real Deal framing (real impact for students who rarely get told).

**Links.** Repo: https://github.com/Arunkumar06-cmd/siddha — Demo (139 s, two live turns, streams inline): https://arunkumar06-cmd.github.io/siddha/ — Download master: https://github.com/Arunkumar06-cmd/siddha/releases/download/v2.2.0/demo.mp4 — Release: https://github.com/Arunkumar06-cmd/siddha/releases/tag/v2.2.0
