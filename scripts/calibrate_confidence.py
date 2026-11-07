"""Calibrate the confidence-gate thresholds (src/confidence.py) against the eval sets.

    python3 scripts/calibrate_confidence.py

Prints the distribution of the best dense similarity for in-domain and off-topic queries, then
a sweep: for each candidate MIN_DENSE, what share of in-domain queries would be wrongly refused
and what share of off-topic queries would be correctly refused. Pick the knee, set
SIDDHA_MIN_DENSE / SIDDHA_SOFT_DENSE (or the defaults in confidence.py), then re-run
scripts/eval_retrieval.py and refresh evals/baseline.json.

Re-run this whenever the embedding model, the corpus or the document text that is embedded
changes: cosine scales are model-specific, so the thresholds do not carry over.
"""
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

import evalsets  # noqa: E402

import confidence  # noqa: E402
import retriever  # noqa: E402


def best_scores(queries):
    return sorted(confidence.best_dense(retriever.search(q, k=8)) or 0.0 for q in queries)


def pct(values, p):
    return values[min(len(values) - 1, int(p * len(values)))]


def describe(name, values):
    print(f"{name:12} n={len(values):4} min={values[0]:.3f} p05={pct(values, .05):.3f} "
          f"p10={pct(values, .10):.3f} median={pct(values, .5):.3f} p90={pct(values, .9):.3f} "
          f"max={values[-1]:.3f}")


def main():
    recs = [json.loads(line) for line in retriever.CORPUS.read_text(encoding='utf-8').splitlines() if line.strip()]
    retriever.search('warm up', k=1)
    rnd = random.Random(5)
    named = [q for q, _ in rnd.sample(evalsets.named_queries(recs), 300)]
    noisy = [q for q, _ in evalsets.noisy_queries(recs, n=300)]
    hand = [q for q, _ in evalsets.PAIRS]

    in_domain = {'hand': best_scores(hand), 'named': best_scores(named), 'noisy': best_scores(noisy)}
    ood = best_scores(evalsets.OOD)
    pooled = sorted(v for vals in in_domain.values() for v in vals)

    print('best dense similarity of the top-8 hits\n')
    for name, vals in in_domain.items():
        describe(name, vals)
    describe('in-domain', pooled)
    describe('off-topic', ood)

    print(f"\n{'MIN_DENSE':>9}  {'in-domain wrongly refused':>26}  {'off-topic correctly refused':>28}")
    for step in range(40, 63, 2):
        t = step / 100
        fr = sum(1 for v in pooled if v < t) / len(pooled)
        ok = sum(1 for v in ood if v < t) / len(ood)
        mark = '  <- current' if abs(t - confidence.MIN_DENSE) < 1e-9 else ''
        print(f"{t:>9.2f}  {fr:>25.1%}  {ok:>27.1%}{mark}")

    soft = sum(1 for v in pooled if confidence.MIN_DENSE <= v < confidence.SOFT_DENSE) / len(pooled)
    print(f"\ncurrent gate: refuse < {confidence.MIN_DENSE}, hedge < {confidence.SOFT_DENSE} "
          f"-> {soft:.1%} of in-domain queries get the hedge")


if __name__ == '__main__':
    main()
