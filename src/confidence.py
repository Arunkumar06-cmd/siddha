"""Retrieval confidence gate: answer, hedge, or admit the records do not cover the question.

The retriever always returns k results, so without a gate every question, however far
outside the corpus, was answered from whichever scheme happened to be nearest ("gym
membership offers" -> an export-council membership scheme). The signal is the dense cosine
similarity (BGE-M3, normalised, IndexFlatIP): unlike the fused RRF score it has a stable
scale, so it can be thresholded.

Thresholds come from scripts/calibrate_confidence.py on 100 queries (30 hand-written and
40 name-anchored in-domain, 30 off-topic): in-domain top-5 best score had min 0.497 /
p10 ~0.55 / median ~0.66; clearly off-topic had median 0.42 / max 0.544. The floor is
0.545, just above the off-topic maximum, so "gym membership offers" is refused instead of
answered with an export-council scheme.

An exact, unique scheme name in the query overrides the dense floor: the student named the
record, so the answer is grounded even when the embedding similarity is low (for example
"Mukhyamantri Matrupushti Uphar kya hai" scores 0.4865 but is exactly the record asked for).
The retriever marks that hit with `name_match`.

    best < MIN_DENSE            LOW   nothing in the records supports an answer: say so
    MIN_DENSE <= best < SOFT    SOFT  probably right but shaky: answer, but hedge and invite
                                      the scheme's name
    best >= SOFT_DENSE          OK    answer normally

Both are overridable (SIDDHA_MIN_DENSE / SIDDHA_SOFT_DENSE) because a model swap or a corpus
refresh moves them; re-run the calibration script when either changes. A top-2 margin rule
was tried and dropped: correct answers often have margins under 0.01 because a State and a
Central variant of the same scheme sit side by side, so it clarified far too often.
"""
import os

LOW, SOFT, OK = 'low', 'soft', 'ok'

MIN_DENSE = float(os.getenv('SIDDHA_MIN_DENSE', '0.545'))
SOFT_DENSE = float(os.getenv('SIDDHA_SOFT_DENSE', '0.58'))

NOT_FOUND = ("Suno. Mujhe iska jawab apne records mein nahi mila. Scheme ka naam, ya apna state "
             "aur class bataiye, phir se dhoondha jayega. Sab schemes scholarships.gov.in pe bhi milengi.")


def best_dense(hits):
    """Highest dense similarity among the returned hits; None if none has one.

    A hit's dense_score is None when it entered the list through BM25 alone. The best of
    the top-k is used, not the first hit's: State routing can lift a keyword-only State
    scheme to #1, and that must not look like "no semantic support"."""
    scores = [h['dense_score'] for h in hits if h.get('dense_score') is not None]
    return max(scores) if scores else None


def tier(hits):
    if not hits:
        return LOW
    if hits[0].get('name_match'):
        # The query contains this record's unique full name. The student named the
        # scheme, so dense similarity is not the deciding signal.
        return OK
    if not any('dense_score' in h for h in hits):
        # Not produced by the retriever (a carried-over scheme, a test double): there is no
        # similarity to judge, so do not invent a verdict.
        return OK
    best = best_dense(hits)
    if best is None or best < MIN_DENSE:
        return LOW
    if best < SOFT_DENSE:
        return SOFT
    return OK
