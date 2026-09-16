# Handoff: public model scorecard

Updated 2026-09-15. Replace on next handoff; do not append a session log.

## Pipeline

`ff.py model-scorecard` runs `advisor_runtime/public_model_scorecard.py`:

- Builds a point-in-time feature table (2018-2025 seasons) from nflverse:
  player stats, snap counts, participation, NGS, FTN charting, ffopportunity
  xFP, FantasyPros ECR (via nflverse), implied team totals. All rolling
  features are shifted one game; ECR is the latest snapshot before kickoff.
  Cached at `advisor_runtime/data/model_cache/public_features_v1.parquet`
  (`--force` rebuilds).
- Walk-forward evaluates 2021-2025 (train on strictly earlier seasons) in
  exact league scoring, adding one source group at a time
  (`run_scorecard()` in that file, steps 1-6). A step's features are kept
  only if aggregate MAE drops and it wins >=3 of 5 seasons
  (`_season_wins`/`kept` gating).
- Step 6 was fitted matchup-opponent shrinkage (`_matchup_priors`,
  `tune_matchup_strength`): prior strength tuned on 2020
  (`SELECTION_SEASONS`) only, then scored on 2021-2025.
- Writes `docs/model_scorecard.json` (steps, kept features, MAE/rank/ROS/
  interval metrics) and trains the final XGBoost model
  (`train_final_model`) to `advisor_runtime/models/public_projection_xgb.json`
  + `public_projection_metadata.json`.
- Result before this session: best step was 5_consensus_ecr, MAE 4.7101;
  step 6 (matchup) was previously marked kept but only reduced MAE
  4.7101 -> 4.7099, a smaller improvement than its own 2024 season MAE
  regression (4.7065 -> 4.7078) — i.e. matchup shrinkage was net noise on
  held-out data. Commit 4186baf already reverted this once.

## Decisions already made (do not re-ask)

1. **Surfacing:** ship the trained public-model blend as skill-weighted with
   sleeper+espn, behind an opt-in flag first. Only make it the default once
   a same-sample head-to-head shows the blend beats sleeper+espn; record
   that evidence when it happens.
2. **Sparse in-season data:** train feature-tier variants — full; no
   FTN/NGS; opportunity+ECR only — score each on the 2021-2025 walk-forward,
   and at inference time use the richest tier whose features actually exist
   for that week. Label tier freshness in the packet. Also run the shipped
   `ffopportunity` model on 2026 play-by-play weeks the package release
   hasn't covered yet.
3. **Matchup shrinkage:** remove step 6. It increased MAE (4.7065 ->
   4.7099 on 2024) versus stopping at step 5. See Task 1 result below.

## Task list

1. Remove matchup shrinkage from the scorecard pipeline; re-run and record
   the result. **Done this session — see below.**
2. Add ROS error at weeks 3/6/9 to every step's report, not just the final
   one (`ros_mae_at_checkpoint` currently only meaningfully populated for
   some steps — check per-step calls in `run_scorecard`).
3. Build feature-tier variants (full / no-FTN-NGS / opportunity+ECR-only)
   and live tier selection at inference based on which features exist for
   the current week.
4. Same-sample head-to-head: trained model blend vs sleeper+espn on
   identical player-weeks. Wire the blend in as opt-in first; promote to
   default only if it wins (decision 1).
5. Wire the model's ROS distributions into trade, buy-low, drop valuation
   (currently those intents use other signals; no model ROS integration
   yet).

## This session

Did Task 1 only, per instruction. Removed the step-6 fitted matchup
adjustment from `public_model_scorecard.py` (`_matchup_priors`,
`tune_matchup_strength`, and the step-6 block in `run_scorecard`), since it
was already shown to be net-negative and commit 4186baf had reverted the
equivalent homemade version once already. Re-ran `python ff.py
model-scorecard`. See STATUS.md/docs/model_scorecard.json for the updated
result: final step is now `5_consensus_ecr`, MAE 4.7101 (was 4.7099 with
matchup kept — a negligible loss on the headline number, but the fitted
step was regressing 2024 specifically and added a full tuning/lookup layer
for no verified gain, so removing it is the correct simplification given
the codebase's own selection rule).

Next prompt: pick up Task 2 (per-step ROS error reporting) fresh, reading
this file and `docs/model_scorecard.json` first.
