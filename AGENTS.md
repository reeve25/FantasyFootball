# Shared Fantasy Football system

Read BRIEF.md and STATUS.md in this folder. They are the maintained instructions
for both assistants. Use ff.py as the only public engine entry point. Read
docs/TRADES.md only for trade discovery or final offer validation. Do not load
the full engine or snapshots into a conversation to answer an ordinary question.

## Ticket work

When working a ticket (T2, T3, ...), also read docs/FORECASTING.md and
docs/TICKETS.md at session start. Work exactly one ticket per session; do not
expand scope or pull in the next ticket early. A session only counts as done
when all three are true: the ticket's acceptance check has actually been run
(not just written), the resulting changes are committed, and STATUS.md has a
dated entry recording what happened -- done, blockers, and the exact next
prompt if the ticket didn't finish. An unfinished ticket gets split
(T<n>a/T<n>b) rather than left half-done and uncommitted.
