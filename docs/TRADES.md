# Flock discrepancy and fair-trade workflow

Use for finding, constructing, widening, or optimizing trades, or an explicit
Flock comparison. Reeve wants a Flock **Fair Trade!** offer that raises the
expected PPG of the legal starting lineup: buy players Flock prices below their
supported lineup value and sell assets it prices above their lineup value.
This is an on-demand workflow, not a scan for every fantasy question.

The objective is Reeve's own team, not a symmetric win: search for and rank
offers by Reeve's expected lineup improvement and evidence strength first: a
modeled counterparty loss is shown as context, never grounds to drop a
candidate on its own, and it is Flock's verdict below (not the engine's
counterparty math) that stands in for the other manager's likely acceptance.
`ff.py discover` defaults to `--mode ours`: it ranks candidates by Reeve's own
modeled lineup gain and reports the counterparty delta per candidate without
excluding on it. `--mode mutual` restores the older screen (also requires a
non-negative counterparty delta, ranked by a blended ours+theirs score) as an
explicit, deliberately-chosen alternative, not the normal lens.

## Screen the real opportunity set

1. Refresh live Sleeper ownership/settings and the projection snapshot when
   stale. Record scoring, starter slots, roster capacity, current NFL week,
   completed games, trade timing, byes, and material availability changes. A
   fresh fetch does not make an old provider forecast fresh.
2. Open Flock's current-season **Redraft** rankings, verify PPR or other
   scoring controls if exposed, and cover Reeve's outgoing assets plus the
   opposing rosters' relevant QB/RB/WR/TE pool. Use full names and canonical
   Sleeper IDs. Record ranks or values and actual coverage; do not call a
   partial page view a league-wide scan or anchor on past-chat favorites.
3. Build a shortlist from Flock price versus projected marginal starter value,
   source disagreement, and current role/usage. Screen across positions and
   price tiers before narrowing. A rank gap is a lead, not a points estimate;
   ADP is secondary market context, not independent proof of an edge.
4. Construct plausible one-for-one, two-for-one, and balanced multi-player
   packages using each target's actual owner. Check the counterparty's needs
   and legal lineup; do not invent acceptance psychology. A consolidation may
   improve Reeve while the depth received helps the other manager.

## Establish a football edge

- Compare the same scoring and horizon. Label current-week forecasts,
  remaining-schedule forecasts, per-active-game season estimates, and true ROS
  projections separately. State the weeks averaged. Exclude already completed
  games and explain when a trade can first affect a lineup. Preseason totals
  divided by assumed games, or one favorable weekly matchup repeated through
  Week 17, are scenarios rather than verified ROS forecasts.
- Require at least two independent numerical supports to call a target
  evidence-backed. Separate forecasting origins matter: an ensemble and its
  members are not extra votes; two sites relaying the same forecast or two
  odds vendors carrying the same bookmakers are not independent confirmations.
  Keep source-specific lineup results visible when available. One-model leads
  can remain on the research shortlist but cannot establish the requested win.
- Use current multi-book markets for matching components and dates. Preserve
  books, timestamp, line range, odds and coverage. Partial yardage/reception
  props do not cover every scoring component, and a betting threshold is not
  automatically an expected mean. Missing or asymmetric prop coverage is
  unknown, never evidence that an uncovered player is worse. Weekly props can
  corroborate near-term volume; do not relabel them a season forecast or claim
  that "Vegas agrees" when markets are unavailable or materially conflicting.
- Verify role, injury, and availability with current official or strongly
  sourced reporting. Re-run or qualify stale projections after material news.
  Show a defensible downside case for uncertain workloads or concentrated TD
  assumptions; do not invent a universal haircut percentage.

## Calculate actual lineup improvement

Run the runtime's exact trade operation on complete constructed finalist
terms. Compare both teams' best legal weekly lineups before and after, then
average the weekly differences over the same remaining weeks. Show playoff
weeks separately. Use null/unavailable when decisive inputs are missing; never
fill absent weekly forecasts with zero or quietly substitute season averages.
If only current-week evidence exists, report a current-week result and leave
ROS unverified.

For every multi-player finalist, identify the actual changed starter slots:
the incoming starter, the outgoing starter(s), and any promoted bench player
or displaced current starter. A bench asset's raw PPG is not an automatic loss
from the starting lineup. Conversely, receiving a player projected above one
outgoing asset does not establish a gain if a second outgoing starter must be
replaced. Re-optimize the full eligible lineup, including both FLEX slots.

Include forced drops, IR eligibility, byes, and depth lost at each position.
Use the same legal weekly optimization for the counterparty. Unchanged K/DST
may cancel, but state their exclusion. A newly open roster spot has no
automatic free-agent value: credit an add only when the player is available,
the acquisition is feasible, and the same assumption is applied consistently.

Prefer at least +0.5 expected lineup points per week as a practical screening
margin, not statistical proof. Label smaller gains thin. Compare independent
projection scenarios and a reasonable downside case. If the edge reverses
under a supported alternative, describe the disagreement and keep the offer
conditional rather than claiming a robust win.

## Verify the exact Flock offer

Use the live calculator for every finalist. Verify league/team orientation,
current season, **Redraft**, and exposed scoring settings. Enter every player
on the correct side and dismiss any selection preview. The first result can
still be stale even after all selected-player chips are visible: Flock has
shown **Fair Trade!** immediately and changed it on asynchronous recalculation.
Take a subsequent state or screenshot after recalculation and confirm that
terms, displayed values, and verdict remain stable before recording a pass.
Record exact terms, verdict text, displayed values
or balance-bar direction when available, URL, and observation time. Recheck
after every package change; a prior verdict does not transfer to new terms.

Only the final explicit **Fair Trade!** verdict passes Reeve's acceptance gate.
The bar may lean either way. **You win!**, **They win!**, **You slightly win!**,
**You slightly lose!**, any other non-fair verdict, visually similar
totals, a rank/value sum, or a transient player suggestion do not pass. If the
site cannot show the complete verdict in the right format, label that offer
unverified. A Flock fairness label does not promise the manager will accept.

## Adjusting toward Fair Trade! without losing the point of the trade

When a real, plausible package comes back **You win!**/**You're robbing
them!** rather than **Fair Trade!**, adjust and recheck rather than stopping
at the first verdict or force-accepting a lopsided one. The loop, in order,
generic to any pair of teams and any starting package -- do not hardcode
which players or positions it applies to:

1. Construct for Reeve's own benefit first (a real lineup gain under our
   evaluator, from Reeve's actual roster, not an arbitrary pairing).
2. Check Flock's verdict on that exact package.
3. If not Fair Trade!, adjust the package using another *meaningful*,
   actually-rostered asset -- a different outgoing centerpiece, or a genuine
   second exchange where a gain on one side justifies a concession on the
   other -- and recheck.
4. Rerun our own evaluator on the exact adjusted assets (including any
   forced drops) after every adjustment that changes verdict-relevant terms;
   Flock fairness and our modeled gain are two separate readings of the same
   package, tracked side by side, never collapsed into one number.

Flock's displayed "OVR" per player is an observed data point about that
one player, not an established additive trade-value currency -- do not sum
or subtract OVR across players to predict a verdict, and two "You win!"
results at different OVR gaps do not bracket a fair threshold; only an
actually-observed Fair Trade! (or its absence) is evidence.

**Do not pad with bottom-bench throw-ins to chase a verdict change.**
Verified empirically (2026-09-13): adding a rostered player with a
near-zero modeled/lineup value to a losing side sometimes visibly shifts
Flock's balance bar and sometimes does nothing at all, with no reliable way
to predict which from our own projections alone -- confirmed by adding
several such players individually and in combination and observing the
verdict and displayed values before and after each one settled. Treat
padding as an unreliable, uninformative lever, not a real adjustment: prefer
swapping in a different meaningful centerpiece or building a genuine
two-sided exchange instead. If a construction reaches Fair Trade! only by
degrading Reeve's own modeled gain to near zero or negative, say so plainly
rather than reporting the fairness pass as if the trade were still worth it.

## Deliver the decision honestly

Lead with the best fully validated offer and at most two useful alternatives.
For each, give exact sends/receives and owner, final Flock verdict, changed
starters, Reeve's current-week and remaining-season lineup delta as available,
playoff delta, counterparty delta, forced drops, decisive evidence and source
times. Compact tables may separate horizons and sources without false
precision. Keep full research records local; do not bury the recommendation.

An actionable recommendation must pass both the Flock fairness gate and the
supported lineup-improvement gate. If none passes, say no validated trade was
found, distinguish rejected offers from unverified candidates, and name the
best research target with its missing evidence or maximum acceptable price.
Do not turn incomplete search coverage into a claim that no such trade exists.
Never submit a trade or change a roster without the user's explicit request.
