## What & why
<!-- Problem, change, approach. Link issues. -->

## Verification
- [ ] `make lint` clean
- [ ] `make test` green
- [ ] Health endpoint OK if touched

## Anti-slop checklist
- [ ] No secrets in this diff
- [ ] Tests cover at least one unhappy path
- [ ] Failure paths of new external calls have circuit breaker/retry
- [ ] No `print()`/`console.log`/commented-out code committed
