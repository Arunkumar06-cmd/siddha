"""Multilingual RAG retriever over the myScheme scholarship corpus.
Embeddings: BAAI/bge-m3 (100+ languages, code-mixed-friendly).
Fusion: dense FAISS + BM25 via Reciprocal Rank Fusion."""
import json
import pathlib
import re
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

def doc_text(rec):
    parts = [f"Scheme: {rec['name']}", f"Category: {rec['category']}", f"Level: {rec['level']}"]
    for k, label in [('details', 'What it is'), ('eligibility', 'Eligibility'),
                     ('benefits', 'Benefit'), ('documents', 'Documents needed'),
                     ('application', 'How to apply')]:
        v = rec.get(k, '')
        if v:
            parts.append(f"{label}: {v}")
    return '\n'.join(parts)

@lru_cache(maxsize=1)
def _load():
    with open(CORPUS, encoding='utf-8') as fh:
        recs = [json.loads(line) for line in fh]
    docs = [doc_text(r) for r in recs]
    model = SentenceTransformer(MODEL)
    index = faiss.read_index(str(INDEX))
    bm25 = BM25Okapi([re.findall(r'\w+', d.lower()) for d in docs])
    return recs, docs, model, index, bm25

def is_loaded() -> bool:
    """True once the model/index have been loaded, for the readiness probe."""
    return _load.cache_info().currsize > 0


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
                    'record': recs[i], 'document': docs[i]})
    return out
