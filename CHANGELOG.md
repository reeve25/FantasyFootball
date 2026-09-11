# Changes

## Shared-system consolidation — 2026-09-10

- Git baseline preserved before changes; ff.py is the public production entry.
- Explicit expensive refresh, subprocess deadlines, compact saved evidence.
- Parallel bounded live requests and weekly projection reads; shared atomic
  caches preserve their original fetch times and survive incomplete refreshes.
- Missing projections stay unknown, old health tags can clear with current
  metadata, complete ROS coverage required, future trade timing made explicit.
- Trade results identify evidence gaps; bounded discovery rejects counterparty
  harm and noncontributing padding. External Flock/news validation stays explicit.
- Shared BRIEF.md with short Claude and Codex entry instructions; no model APIs.
