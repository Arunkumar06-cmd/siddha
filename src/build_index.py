"""Encode corpus once and persist FAISS index + embeddings to disk."""
import json
import logging
import time

import faiss
import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from retriever import CORPUS, doc_text

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger(__name__)

t0 = time.time()
with open(CORPUS, encoding='utf-8') as fh:
    recs = [json.loads(line) for line in fh]
docs = [doc_text(r) for r in recs]
log.info('docs: %d', len(docs))
model = SentenceTransformer('BAAI/bge-m3', device='mps',
                                          model_kwargs={'torch_dtype': torch.float32})
model.max_seq_length = 512
emb = model.encode(docs, batch_size=16, normalize_embeddings=True, show_progress_bar=True)
np.save('data/corpus_emb.npy', emb.astype('float32'))
idx = faiss.IndexFlatIP(emb.shape[1])
idx.add(np.ascontiguousarray(emb.astype('float32')))
faiss.write_index(idx, 'data/scholarships.faiss')
log.info('saved embeddings shape=%s sec=%.0f', emb.shape, time.time() - t0)
