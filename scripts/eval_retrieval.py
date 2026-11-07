"""Retrieval and confidence-gate evaluation over the shipped corpus.

Runs the four sets in scripts/evalsets.py through the real retriever (BGE-M3 + BM25 + state
routing) and the real confidence gate, and reports recall@1, recall@5 and MRR with 95%
bootstrap intervals, plus how often the gate refuses or hedges.

    python3 scripts/eval_retrieval.py                          # print the report
    python3 scripts/eval_retrieval.py --json evals/latest.json
    python3 scripts/eval_retrieval.py --check evals/baseline.json

--check exits 1 if a tracked metric regressed beyond tolerance, so a change to the retriever,
the routing multipliers, the embedding model or the gate thresholds cannot quietly make
search worse. Tolerance is the larger of --tol and 1.5 queries' worth for that set, so a single
flipped query on the 30-query hand set is not a failure but a real drop is.

Needs the embedding model on disk (about 2 GB, cached after the first run). CPU, about a minute.
"""
import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

import evalsets  # noqa: E402

import confidence  # noqa: E402
import retriever  # noqa: E402

# (metric key, direction): "up" must not fall, "down" must not rise.
TRACKED = {
    'hand': [('recall@5', 'up'), ('recall@1', 'up'), ('refused_share', 'down')],
    'named': [('recall@5', 'up'), ('recall@1', 'up'), ('refused_share', 'down')],
    'noisy': [('recall@5', 'up'), ('recall@1', 'up'), ('refused_share', 'down')],
    'ood': [('refused_share', 'up')],
}


def tier_shares(tiers):
    n = sum(tiers.values())
    return {'refused_share': round(tiers[confidence.LOW] / n, 4),
            'hedged_share': round(tiers[confidence.SOFT] / n, 4)}


def run_ranked(pairs, substring):
    ranks, tiers, misses = [], dict.fromkeys((confidence.LOW, confidence.SOFT, confidence.OK), 0), []
    for query, expect in pairs:
        hits = retriever.search(query, k=8)
        rank = evalsets.rank_of(expect, [h['record']['name'] for h in hits], substring)
        ranks.append(rank)
        tiers[confidence.tier(hits)] += 1
        if rank != 1:
            misses.append({'query': query, 'expected': expect, 'rank': rank,
                           'top': hits[0]['record']['name']})
    return {**evalsets.summarise(ranks), **tier_shares(tiers)}, misses


def run_ood(queries):
    tiers = dict.fromkeys((confidence.LOW, confidence.SOFT, confidence.OK), 0)
    leaked = []
    for query in queries:
        hits = retriever.search(query, k=8)
        t = confidence.tier(hits)
        tiers[t] += 1
        if t != confidence.LOW:
            leaked.append({'query': query, 'tier': t, 'best_dense': confidence.best_dense(hits),
                           'top': hits[0]['record']['name']})
    return {'n': len(queries), **tier_shares(tiers)}, leaked


def evaluate():
    recs = [json.loads(line) for line in retriever.CORPUS.read_text(encoding='utf-8').splitlines() if line.strip()]
    retriever.search('warm up', k=1)
    t0 = time.time()
    report = {'meta': {'records': len(recs), 'model': retriever.MODEL,
                       'min_dense': confidence.MIN_DENSE, 'soft_dense': confidence.SOFT_DENSE}}
    details = {}
    report['hand'], details['hand'] = run_ranked(evalsets.PAIRS, substring=True)
    report['named'], details['named'] = run_ranked(evalsets.named_queries(recs), substring=False)
    report['noisy'], details['noisy'] = run_ranked(evalsets.noisy_queries(recs), substring=False)
    report['ood'], details['ood'] = run_ood(evalsets.OOD)
    report['meta']['seconds'] = round(time.time() - t0, 1)
    return report, details


def fmt_ci(row, key):
    lo, hi = row[key + '_ci']
    return f"{row[key]:.3f} [{lo:.3f}, {hi:.3f}]"


def print_report(report, details):
    m = report['meta']
    print(f"corpus={m['records']} model={m['model']} gate: refuse<{m['min_dense']} hedge<{m['soft_dense']}")
    print(f"\n{'set':6} {'n':>5}  {'recall@1 [95% CI]':<22} {'recall@5 [95% CI]':<22} {'MRR [95% CI]':<22} refused hedged")
    for name in ('hand', 'named', 'noisy'):
        r = report[name]
        print(f"{name:6} {r['n']:>5}  {fmt_ci(r, 'recall@1'):<22} {fmt_ci(r, 'recall@5'):<22} "
              f"{fmt_ci(r, 'mrr'):<22} {r['refused_share']:.3f}   {r['hedged_share']:.3f}")
    o = report['ood']
    print(f"{'ood':6} {o['n']:>5}  off-topic queries refused: {o['refused_share']:.3f}   hedged: {o['hedged_share']:.3f}")
    print("\nhand-set queries not ranked first:")
    for x in details['hand']:
        print(f"  rank {x['rank']!s:>4}  {x['query'][:62]!r}  -> {x['top'][:44]}")
    if details['ood']:
        print("\noff-topic queries that were NOT refused:")
        for x in details['ood']:
            print(f"  {x['tier']:5} dense={x['best_dense']:.3f}  {x['query']!r} -> {x['top'][:44]}")


def check(report, baseline_path, tol):
    base = json.loads(pathlib.Path(baseline_path).read_text())
    failures = []
    for name, metrics in TRACKED.items():
        n = report[name]['n']
        allowed = max(tol, 1.5 / n)
        for key, direction in metrics:
            cur, ref = report[name][key], base[name][key]
            bad = cur < ref - allowed if direction == 'up' else cur > ref + allowed
            if bad:
                failures.append(f"{name}.{key}: {ref:.3f} -> {cur:.3f} (allowed +/-{allowed:.3f})")
    return failures


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--json', help='write the full report to this path')
    ap.add_argument('--check', help='compare with a baseline report and exit 1 on regression')
    ap.add_argument('--tol', type=float, default=0.02, help='minimum tolerance per metric (default 0.02)')
    args = ap.parse_args()

    report, details = evaluate()
    print_report(report, details)
    if args.json:
        out = pathlib.Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + '\n')
        print(f"\nwrote {out}")
    if args.check:
        failures = check(report, args.check, args.tol)
        if failures:
            print('\nREGRESSION vs baseline:')
            for line in failures:
                print('  ' + line)
            return 1
        print('\nno regression vs baseline')
    return 0


if __name__ == '__main__':
    sys.exit(main())
