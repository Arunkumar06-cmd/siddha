# Retrieval evaluation (2026-11-05)

Labeled benchmark: 30 queries against the shipped corpus (`data/scholarships.jsonl`), one expected scheme name each (case-insensitive substring match). Mix of exact-name anchors (control) and intent paraphrases in Hinglish. This is a single-authoration probe, not an independent benchmark — treat numbers as directional.

**Setup:** `BAAI/bge-m3` (1024d) dense FAISS + `rank-bm25` (BM25Okapi) fused with reciprocal rank fusion (RRF k=60), plus state-aware re-ranking (see below). `src/retriever.py`.

| Metric | MiniLM-L12 (8c90316, no state routing) | BGE-M3 + state-aware routing (this commit) |
|---|---|---|
| recall@1 | 0.53 | **0.67** |
| recall@5 | 0.73 | **0.77** |
| MRR | 0.63 | **0.73** |
| n | 30 | 30 |

** State-aware routing (shipped v2.3 content)** — the previous failure mode (a state-less query silently returned another state's post-matric scheme) is fixed in the ranker, not just in the responder's caveat. A query naming a state/UT multiplies that state's schemes by 1.35, other state schemes by 0.75, Central by 1.05; a query containing `central government|central govt|central sector` filters Central-only; a state-less query gives Central schemes a 1.2 multiplier. The Central "Post-Matric Scholarship for SC students" now ranks #1 for the demo question; a Bihar-specific question returns Bihar's post-matric scheme #1.

**Known failure (honest):** `PM USP` as an isolated acronym misses top-8 — the record contains `(PM-USP)` but the dense similarity doesn't separate it without more context words. Rephrase with intent ("college university students scholarship for meritorious") and it retrieves.

**Caveats:** single-annotator labels; the top-miss (`best performing college students ko kya mileti hai`) is genuinely ambiguous against `Post Matric Merit Scholarship`; `class 8 rural student merit scholarship without income proof` ranks **National Means-Cum-Merit** at #7, which is a reasonable outcome for that phrasing.

Reproduce: `python3 scripts/eval_retrieval.py`
