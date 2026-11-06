"""Multilingual RAG retriever over the myScheme scholarship corpus.
Embeddings: BAAI/bge-m3 (100+ languages, code-mixed-friendly).
Fusion: dense FAISS + BM25 via Reciprocal Rank Fusion."""
import json
import re
from functools import lru_cache

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

import places

CORPUS = 'data/scholarships.jsonl'
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
    index = faiss.read_index('data/scholarships.faiss')
    bm25 = BM25Okapi([re.findall(r'\w+', d.lower()) for d in docs])
    return recs, docs, model, index, bm25

def is_loaded() -> bool:
    """True once the model/index have been loaded, for the readiness probe."""
    return _load.cache_info().currsize > 0


def search(query, k=8, dense_k=20, bm25_k=20, rrf_k=60):
    recs, docs, model, index, bm25 = _load()
    q = model.encode([query], normalize_embeddings=True)[0].astype('float32')
    _, d_ids = index.search(np.expand_dims(q, 0), dense_k)
    d_ids = d_ids[0]
    tokenized = re.findall(r'\w+', query.lower())
    b_scores = bm25.get_scores(tokenized)
    b_ids = np.argsort(-b_scores)[:bm25_k]
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
        out.append({'rank_score': round(score, 4), 'record': recs[i], 'document': docs[i]})
    return out
