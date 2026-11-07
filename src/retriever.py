"""Multilingual RAG retriever over the myScheme scheme corpus.
Embeddings: BAAI/bge-m3 (100+ languages, code-mixed-friendly).
Fusion: dense FAISS + BM25 via Reciprocal Rank Fusion."""
import collections
import json
import pathlib
import re
import threading
from functools import lru_cache

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

import places

# Anchored to this file, not the working directory: a relative path made the first query crash
# with FileNotFoundError whenever the server was started from anywhere but the repo root.
DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / 'data'
CORPUS = DATA_DIR / 'scholarships.jsonl'
INDEX = DATA_DIR / 'scholarships.faiss'
MODEL = 'BAAI/bge-m3'

# A scheme whose full, unique name appears verbatim in the query is what the user asked for.
# Without this, the generic "no state named -> Central x1.2" prior below outranked a State
# scheme asked for by its exact name: 256 of 262 exact-name misses were a State scheme losing
# to an unrelated Central one ("Abhinandan Education Loan Subsidy Scheme" -> a PM scheme).
NAME_MATCH_BOOST = 2.0
MIN_NAME_CHARS = 8   # and at least two words: one-word names are too generic to be evidence


@lru_cache(maxsize=4096)
def _squash(text):
    """Lower-case alphanumeric words joined by single spaces, so punctuation and dash
    variants (hyphen, en dash, middle dot) do not stop a name from matching."""
    return ' '.join(re.findall(r'[^\W_]+', str(text).lower()))


def _name_matches(query, recs, candidates):
    """Candidate ids whose unique, full scheme name is contained in the query; only the most
    specific (longest) such name counts, so "Pre-Matric Scholarship" does not tie with
    "Pre-Matric Scholarship for Backward Class Students" when the user said the latter.

    A name shared by several records ("Post Matric Scholarship", one per state) is generic and
    is left to the Central/State routing: boosting all of them would hand a state-less
    question to an arbitrary state."""
    padded = f' {_squash(query)} '
    found = []
    for i in candidates:
        name = _squash(recs[i]['name'])
        if len(name) >= MIN_NAME_CHARS and ' ' in name and f' {name} ' in padded:
            found.append((len(name), i, name))
    if not found:
        return []
    longest = max(length for length, _, _ in found)
    counts = collections.Counter(_squash(r['name']) for r in recs)
    return [i for length, i, name in found if length == longest and counts[name] == 1]

def doc_text(rec):
    parts = [f"Scheme: {rec['name']}", f"Category: {rec['category']}", f"Level: {rec['level']}"]
    for k, label in [('details', 'What it is'), ('eligibility', 'Eligibility'),
                     ('benefits', 'Benefit'), ('documents', 'Documents needed'),
                     ('application', 'How to apply')]:
        v = rec.get(k, '')
        if v:
            parts.append(f"{label}: {v}")
    return '\n'.join(parts)

_load_lock = threading.Lock()
_cache = None


def _read_all():
    """Read the corpus and index and build the model. Called at most once."""
    with open(CORPUS, encoding='utf-8') as fh:
        recs = [json.loads(line) for line in fh]
    docs = [doc_text(r) for r in recs]
    model = SentenceTransformer(MODEL)
    index = faiss.read_index(str(INDEX))
    bm25 = BM25Okapi([re.findall(r'\w+', d.lower()) for d in docs])
    return recs, docs, model, index, bm25


def _load():
    """Load everything exactly once, even when several first requests race.

    lru_cache can run the wrapped function more than once on a cold cache: two
    concurrent first turns would each build a 2 GB model. The double check under
    one lock means one loader and one copy, while later calls stay lock-free."""
    global _cache
    if _cache is not None:
        return _cache
    with _load_lock:
        if _cache is None:
            _cache = _read_all()
    return _cache


def is_loaded() -> bool:
    """True once the model/index have been loaded, for the readiness probe."""
    return _cache is not None


def warm_up():
    """Load before the first user turn; called from the server's lifespan."""
    return _load()


def search(query, k=8, dense_k=20, bm25_k=20, rrf_k=60):
    recs, docs, model, index, bm25 = _load()
    q = model.encode([query], normalize_embeddings=True)[0].astype('float32')
    d_scores, d_ids = index.search(np.expand_dims(q, 0), dense_k)
    # IndexFlatIP over L2-normalised vectors: the score is the cosine similarity. FAISS pads
    # with id -1 when it has fewer than dense_k vectors; recs[-1] would silently be the last
    # record, so drop the padding.
    dense_sim = {int(i): float(s) for i, s in zip(d_ids[0], d_scores[0], strict=True) if i >= 0}
    d_ids = [i for i in d_ids[0] if i >= 0]
    tokenized = re.findall(r'\w+', query.lower())
    b_scores = bm25.get_scores(tokenized)
    # No query token appears in the corpus (a pure Devanagari or Tamil query against an
    # English corpus): every score is 0 and argsort over ties returns records 0..19 by
    # position, which would then earn RRF credit as if they were keyword matches.
    b_ids = np.argsort(-b_scores)[:bm25_k] if float(b_scores.max()) > 0 else []
    # RRF fusion
    fused = {}
    for rank, i in enumerate(d_ids):
        fused[int(i)] = fused.get(int(i), 0) + 1.0 / (rrf_k + rank + 1)
    for rank, i in enumerate(b_ids):
        fused[int(i)] = fused.get(int(i), 0) + 1.0 / (rrf_k + rank + 1)
    # Check the whole corpus, not only the fused candidates: an exact name can be
    # missed by both dense and BM25 (a rare spelling, a short query) and still be
    # the one scheme the student asked for. A unique full name is strong evidence.
    name_hits = set(_name_matches(query, recs, range(len(recs))))
    for i in name_hits:
        fused[i] = fused.get(i, 0.0) + 1.0 / (rrf_k + 1)
        fused[i] *= NAME_MATCH_BOOST
    # State-aware re-ranking: a State scheme must not silently win for a
    # state-less query, and a State-specific query should not be answered with
    # another State's scheme.
    mentioned = places.mentioned(query)
    wants_central = places.mentioned_central(query)
    for i in list(fused):
        level = recs[i].get('level')
        if wants_central:
            if level != 'Central':
                fused[i] *= 0.15
            continue
        if mentioned:
            owner = places.state_of(recs[i])
            if owner == mentioned:
                fused[i] *= 1.35
            elif owner:
                fused[i] *= 0.75
            else:  # Central or ambiguous State
                fused[i] *= 1.05
        else:
            if level == 'Central':
                fused[i] *= 1.2
    ranked = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
    out = []
    for i, score in ranked:
        # dense_score is None when the record reached the list through BM25 alone: that is a
        # keyword hit with no semantic support, which the confidence gate treats as weak.
        out.append({'rank_score': round(score, 4),
                    'dense_score': round(dense_sim[i], 4) if i in dense_sim else None,
                    'name_match': i in name_hits,
                    'record': recs[i], 'document': docs[i]})
    return out
