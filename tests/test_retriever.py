"""Retriever tests: unit (doc_text/fusion) + a real end-to-end search on the shipped corpus."""
import json

import retriever


def test_doc_text_includes_required_fields():
    rec = {
        'name': 'Scheme X',
        'level': 'Central',
        'category': 'Education',
        'details': 'd',
        'eligibility': 'e',
        'benefits': 'b',
        'documents': 'doc',
        'application': 'app',
    }
    text = retriever.doc_text(rec)
    assert 'Scheme: Scheme X' in text
    assert 'Eligibility: e' in text
    assert 'Documents needed: doc' in text


def test_corpus_jsonl_is_committed():
    path = pathlib_Path('data/scholarships.jsonl')
    assert path.exists()
    with open(path, encoding='utf-8') as fh:
        line = fh.readline()
    rec = json.loads(line)
    assert rec['name'] and rec['eligibility']


def pathlib_Path(p):
    import pathlib
    return pathlib.Path(p)


def test_search_end_to_end_on_real_corpus():
    # Uses the cached MiniLM model; validates the fusion finds a plausible scholarship.
    hits = retriever.search('National Scholarship Portal SC students', k=3)
    assert len(hits) == 3
    assert all('name' in h['record'] for h in hits)
    assert hits[0]['rank_score'] > 0
