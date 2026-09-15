# Shared Fantasy Football system

Start every session by reading `BRIEF.md`, the current-only `STATUS.md`, and
`docs/DEV_MAP.md`. Run `git status --short --branch` before editing. Use `ff.py`
as the only public engine entry point. Load only the task-specific files routed
by `docs/DEV_MAP.md`; do not read snapshots, raw run artifacts, or the full
legacy engine routinely.

## Development discipline

- One agent edits one objective at a time. A second agent may review the
  resulting commit or staged diff, but must not edit the same checkout.
- Inspect the relevant symbols, tests, and existing diff before changing code.
- Keep the change to the stated objective. Stage exact hunks or paths; never use
  broad staging that can sweep in unrelated work.
- Run the focused test first, then `python ff.py selftest` for a finished code
  change. Acceptance must assert the expected non-empty result; exit code zero
  alone is insufficient. For scored backtest acceptance, use
  `python ff.py backtest --require-scored`.
- Review `git diff --cached` and `git diff --cached --check` before committing.
  Preserve unrelated and untracked work.

## Ticket work

When explicitly working a ticket (T2, T3, ...), also read
`docs/FORECASTING.md` and only the relevant section of `docs/TICKETS.md`. Work
one observable outcome at a time and run its real acceptance check. A finished
ticket has a passing non-vacuous acceptance result, a passing selftest, a
reviewed commit, and an updated current state in `STATUS.md`. Replace current
state; do not append a session narrative. If blocked, record the blocker and
exact next prompt in `STATUS.md` before committing the bounded work.
