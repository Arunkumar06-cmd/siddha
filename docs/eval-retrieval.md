# Retrieval evaluation (2026-11-07)

Four labelled sets, run against the shipped corpus (`data/scholarships.jsonl`, 1,141 unique records) and the shipped gate (`src/confidence.py`). Every number below is from `scripts/eval_retrieval.py` on this commit; the same report is committed as `evals/latest.json`, and `evals/baseline.json` is the CI regression guard.

**Setup:** `BAAI/bge-m3` (1024d) dense FAISS + `rank-bm25` (BM25Okapi), fused with reciprocal rank fusion (RRF k=60), plus state-aware re-ranking, whole-corpus exact-name lookup, and a dense-confidence gate. `src/retriever.py`, `src/confidence.py`.

| Set | n | recall@1 [95% CI] | recall@5 [95% CI] | MRR [95% CI] | refused | hedged |
|---|---:|---|---|---|---:|---:|
| `hand` — hand-written Hinglish/intent queries | 30 | 0.733 [0.567, 0.867] | 0.767 [0.600, 0.900] | 0.761 [0.618, 0.884] | 0.033 | 0.167 |
| `named` — one exact-name query per record | 1,141 | 0.999 [0.997, 1.000] | 0.999 [0.997, 1.000] | 0.999 [0.998, 1.000] | 0.001 | 0.001 |
| `noisy` — names after deterministic ASR-style damage | 400 | 0.682 [0.637, 0.728] | 0.925 [0.897, 0.950] | 0.782 [0.750, 0.813] | 0.095 | 0.098 |
| `ood` — questions no scheme should answer | 30 | — | — | — | **1.000** | 0.000 |

`refused` is the share the gate sends to the honest "records do not cover this" reply; `hedged` is the share answered with a caveat and an invitation to name the scheme. `named` and `noisy` labels are generated from the corpus, so they measure name lookup, not intent understanding. `hand` is the only intent set, it is small, and it has a single annotator: read its interval, not its point estimate.

**Confidence gate.** The gate thresholds come from `scripts/calibrate_confidence.py` on 100 queries (30 hand-written and 40 name-anchored in-domain, 30 off-topic): in-domain top-5 best dense score had min 0.497 / p10 ~0.55 / median ~0.66; clearly off-topic had median 0.42 / max 0.544. The shipped floor is **0.545**, just above the off-topic maximum, so "gym membership offers" (max 0.5439) is refused instead of answered with an export-council membership scheme. The hedge boundary is **0.58**.

An exact, unique scheme name in the query overrides the dense floor: the student named the record, so the answer is grounded even when embedding similarity is low. "Mukhyamantri Matrupushti Uphar kya hai" scores 0.4865 (below the floor) but is exactly the record asked for; the retriever marks it `name_match` and the gate answers it. The exact-name lookup searches the whole corpus, not only the fused candidates.

**State-aware routing.** A query naming a state/UT multiplies that state's schemes by 1.35 and other states by 0.75 (Central 1.05); `central government|central govt|central sector` filters to Central; a state-less query gives Central schemes a 1.2 multiplier. Without this, a State scheme could silently win a state-less question, and a state-specific question could be answered with another state's scheme.

**Hand-set misses (honest).** The current run ranks these below 1; the expected scheme is in the list only when rank is not `None`:

| Rank | Query | Top hit |
|---:|---|---|
| 5 | Top Class Education Scheduled Castes students scholarship | Pre-Matric Scholarships Scheme for Schedule… |
| — | PM USP central sector scholarship college university students | Pradhan Mantri Uchchatar Shiksha Protsahan… |
| — | Risktaking engineering student nudi, help milegi scholarships | Merit cum Means Scholarship: Engineering… |
| 7 | class 8 rural student merit scholarship without income proof | Top Class Education For Scheduled Caste… |
| 7 | university post graduate students ke liye national scholarship | Post Graduate Scholarship for GATE/GPAT… |
| — | best performing college students ko kya scholarship mileti hai | Haryana State Meritorious Incentive Scheme… |
| 6 | minority community post matric scholarship Maharashtra | Post-Matric Scholarship To VJNT Students — M… |
| 6 | safai karmachari ke bachcho ki coaching kaunsi scheme hai | Loan Based Schemes For Safai Karamchari… |

Several are genuinely ambiguous without more context (class 8, "best performing", "risktaking"); `PM USP` as an isolated acronym is a known vocabulary miss — the record contains `(PM-USP)` but the dense vector does not separate it without intent words.

**CI gate.** `evals/baseline.json` stores this report. `python3 scripts/eval_retrieval.py --check evals/baseline.json` exits 1 if a tracked metric regresses beyond the larger of `--tol` (0.02) and 1.5 queries' worth for that set, so a model swap, a routing change, a corpus refresh or a threshold change cannot quietly make search or refusal worse. The CI `quality` job runs this after the tests.

**Caveats.** Single-annotator hand labels; no held-out intent split; `named`/`noisy` labels are corpus-generated; the state multipliers were set with the hand set in view, so the intent figures are optimistic. The numbers are a regression guard and a calibration source, not an independent benchmark.

Reproduce:

```bash
python3 scripts/eval_retrieval.py                      # print the report
python3 scripts/eval_retrieval.py --json evals/latest.json
python3 scripts/eval_retrieval.py --check evals/baseline.json
```
