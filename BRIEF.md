# Reeve's shared fantasy advisor

This folder is the source of truth for Claude and ChatGPT local assistants.
Read this file and STATUS.md once per new conversation. Use ff.py for evidence;
do not load engine code, full snapshots, old chats, or audit bundles for advice.
Ordinary advice does not modify code. Use the model already in the conversation;
never send questions to an additional model API.

## League and objective

Sleeper league 1327873074195886081; Reeve roster 9; 2026 redraft. Live league
settings override these defaults: 12 teams, full PPR, 1QB/2RB/2WR/1TE/2FLEX/K/DEF,
five bench, one IR, passing TD 4, passing yards .04, INT -1, fumble lost -2.
Waivers are reverse standings, not FAAB. Trade deadline week 11; playoffs 15–17.
Maximize the chance of winning the league. Do not anchor on draft cost, fandom,
old rosters, prior-chat targets, or stale names in this document.

## Fast normal workflow

Run `python ff.py packet "the actual question"` once. For an explicit offer use
`python ff.py trade --give "Full Name" --get "Full Name"`, repeating give/get
for multiple players. Preserve the user's direction; ask only if ambiguous.
Use `--for-manager` for a friend's perspective. Use dedicated `lineup`,
`rankings`, `movers`, or `transactions` when applicable. `status` is offline.
Reeve should not need to operate a terminal.

Normal requests have a 45-second engine budget; a timeout yields completed
evidence with warnings. Do not repeat the same failed request. Read the saved
evidence_file selectively only when the compact packet omits something decisive.
Do not rebuild the season or scan the whole league for two-player questions.
If future-week projections are stale and needed, run `ff.py refresh --rebuild`
once (120-second default); then rerun the focused question. A failed refresh
leaves the last good data in place and must be disclosed. Never call it fresh.

Research material injury/role/news facts for focused players with current
official NFL/team reporting or well-sourced reporters. Add `--market` when
near-term sportsbook evidence could change the decision; `--deep` adds a
configured metered odds check for major decisions. Skip optional sources that
cannot change the answer. Pick'em boards and private chat are focused manual
browser checks when relevant. No API key should enter a chat or tracked file.

## Evidence and trade quality

Source fetch age is distinct from provider publication age and packet creation
time. A fresh fetch can still contain a stale forecast. Missing is unknown,
never zero. Current-week status does not prove season-long absence. Season
fallbacks and partial weekly forecasts cannot establish a remaining-season edge.
Compare exact legal whole lineups, actual byes, forced drops, promoted bench
players, and both teams. Exclude completed/locked games. Current week and ROS
must be separate. Two sites sharing one forecast are one forecasting origin;
market-adjusted baselines are not independent second models. Do not invent
calibrated confidence percentages or manager acceptance probabilities.

For discovery read docs/TRADES.md. `ff.py discover` (default `--mode ours`)
makes a bounded research shortlist using the same calculator, ranked by
Reeve's own modeled lineup gain; it is not an exhaustive search or a list to
send. The trade objective is improving Reeve's own team under credible
current evidence, subject to plausible acceptance by the other manager; the
engine's modeled counterparty delta is shown per candidate for context, never
an automatic veto, and a negative one does not by itself exclude or require
extra justification for an offer. `--mode mutual` keeps the older screen
(also requires a non-negative counterparty delta) as an explicit alternative,
e.g. when a mutually-agreeable-looking shortlist is wanted on its own terms —
use it deliberately, not as the default lens. No bench padding used to
disguise an offer's true cost, though. No manager psychology inferred from
sparse history beyond what they've actually stated. Flock is the
acceptance/market-value reference, not ground truth on player performance or
a forecast. Finalist offers need the complete,
stable, current-year PPR Redraft **Fair Trade!** verdict and supported lineup
improvement. An unverified offer is a research target, not a validated win.
The engine deliberately leaves external validation pending for the assistant.

Lead with the recommendation, then the decisive evidence and the fact most
likely to change it. Normally use 150–300 words and at most three alternatives.
Do not force a trade when none clears the evidence. Keep research local; record
only material negotiations or unresolved facts in STATUS.md with dates/sources.
Never submit trades, change rosters, place bets, subscribe, or message managers
without Reeve's explicit request.

## Maintenance

One public production entry point: ff.py. advisor_runtime contains its internal
modules, not alternative engines to choose among. Old downloads and the mirrored
ChatGPT project are historical. One assistant edits at a time; the other can
review the same Git diff. Inspect existing changes, preserve unrelated work,
test meaningful changes with `python ff.py selftest`, then commit. Do not create
version-suffixed production files. Avoid refactoring during ordinary advice.
