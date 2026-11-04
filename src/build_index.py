"""Encode corpus once and persist FAISS index + embeddings to disk."""
import json, re, sys, time
import numpy as np, faiss
from sentence_transformers import SentenceTransformer
from retriever import doc_text, CORPUS

t0 = time.time()
recs = [json.loads(l) for l in open(CORPUS, encoding='utf-8')]
docs = [doc_text(r) for r in recs]
print('docs:', len(docs))
model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
emb = model.encode(docs, batch_size=64, normalize_embeddings=True, show_progress_bar=True)
np.save('data/corpus_emb.npy', emb.astype('float32'))
idx = faiss.IndexFlatIP(emb.shape[1])
idx.add(np.ascontiguousarray(emb.astype('float32')))
faiss.write_index(idx, 'data/scholarships.faiss')
print('saved. embeddings', emb.shape, f'{time.time()-t0:.0f}s')
