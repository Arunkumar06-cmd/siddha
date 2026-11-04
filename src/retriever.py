"""Multilingual RAG retriever over the myScheme scholarship corpus.
Embeddings: paraphrase-multilingual-MiniLM-L12-v2 (CPU, ~118 MB).
Fusion: dense FAISS + BM25 via Reciprocal Rank Fusion."""
import json, re, math
import numpy as np
from functools import lru_cache

import faiss
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

CORPUS = 'data/scholarships.jsonl'
MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'

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
    recs = [json.loads(l) for l in open(CORPUS, encoding='utf-8')]
    docs = [doc_text(r) for r in recs]
    model = SentenceTransformer(MODEL)
    index = faiss.read_index('data/scholarships.faiss')
    bm25 = BM25Okapi([re.findall(r'\w+', d.lower()) for d in docs])
    return recs, docs, model, index, bm25

def search(query, k=8, dense_k=20, bm25_k=20, rrf_k=60):
    recs, docs, model, index, bm25 = _load()
    q = model.encode([query], normalize_embeddings=True)[0].astype('float32')
    d_scores, d_ids = index.search(np.expand_dims(q, 0), dense_k)
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
    ranked = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
    out = []
    for i, score in ranked:
        out.append({'rank_score': round(score, 4), 'record': recs[i], 'document': docs[i]})
    return out
