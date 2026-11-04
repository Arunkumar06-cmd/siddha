# Contributing

1. Fork → branch off `main` (`git switch -c feat/<name>`).
2. Local gate: `make lint test` must be green.
3. Follow the anti-slop rules:
   - Every failure path of a new external call needs retry/timeout/circuit-breaker
   - No secrets, no `console.log`/`print`, no commented-out code
   - Tests must include at least one unhappy path
4. Small PRs (<500 LOC). One concern per PR. Squash merge.
5. Non-obvious decisions go in `docs/decisions.md` (ADR format).

## Coding standards
- Python 3.11+, stdlib-first, no new deps without justification (why + alternatives).
- `ruff check .` must pass; line length 110.
- Public functions need docstrings explaining *why*, not what.
