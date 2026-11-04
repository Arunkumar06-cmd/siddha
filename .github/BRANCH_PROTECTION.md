# Branch protection — main

Rules in force for `main`:

1. **Require a pull request before merging** — no direct pushes.
2. **Require 1 approving review** from the code owner (`.github/CODEOWNERS`).
3. **Require status checks to pass**: `quality` (ruff, byte-compile, pytest, gitleaks) and `docker`.
4. **Require conversation resolution** before merge.
5. **Do not allow bypassing the above** — no admin override except in a documented emergency
   (post-hotfix review within 24 h; record in `docs/decisions.md`).
6. **No force pushes, no deletion** of `main`.

## Merge policy
- Squash merge preferred (linear history).
- Commit message = PR title.
- Delete branch after merge.

## Who merges
- The code owner merges after CI is green and the review is resolved.
