# Handoff: public model scorecard

Updated 2026-09-16. Replace on next handoff; do not append a session log.

## Pipeline

`ff.py model-scorecard` runs `advisor_runtime/public_model_scorecard.py`:

- Builds a point-in-time feature table (2018-2025 seasons) from nflverse:
  player stats, snap counts, participation, NGS, FTN charting, ffopportunity
  xFP, FantasyPros ECR (via nflverse), implied team totals. All rolling
  features are shifted one game; ECR is the latest snapshot before kickoff.
  Cached at `advisor_runtime/data/model_cache/public_features_v1.parquet`
  (`--force` rebuilds; gitignored, local-only).
- Walk-forward evaluates 2021-2025 (train on strictly earlier seasons) in
  exact league scoring, adding one source group at a time
  (`run_scorecard()` in that file, steps 1-5). A step's features are kept
  only if aggregate MAE drops and it wins >=3 of 5 seasons
  (`_season_wins`/`kept` gating).
- Writes `docs/model_scorecard.json` (steps, kept features, MAE/rank/ROS/
  interval metrics) and trains the final XGBoost model
  (`train_final_model`) to `advisor_runtime/models/public_projection_xgb.json`
  + `public_projection_metadata.json`.
- Final step is `5_consensus_ecr`, MAE 4.7101, rank correlation 0.6096,
  80% interval coverage 0.8056.

## Reproducibility check (this session)

Task instruction reported step 5 showing 4.7065 before the step-6 matchup
removal and 4.7101 after, with the concern that removing a later step
(6) should never change an earlier step's (5) score. Investigated:

1. **No uncontrolled randomness.** The only stochastic component is
   XGBoost training, which already passes a fixed `random_state=20260915`
   (`public_model_scorecard.py:373`). No other `random`/`np.random`/sampling
   call exists in the file. Confirmed by grep.
2. **Feature cache is stable and not the cause.** The cached parquet is
   gitignored and untouched between runs; it is not re-downloaded on a
   normal invocation (only `--force` rebuilds it).
3. **The premise did not hold under direct measurement.** Diffed
   `docs/model_scorecard.json` at commit `ccad3fb` (step 6 present) against
   commit `85a5e32` (step 6 removed): steps 1-5 are byte-identical between
   the two commits, including step 5's aggregate MAE (4.7101) and its
   2024 per-season MAE (4.7065) in both. There was no discrepancy to fix —
   4.7065 is (and always was) the 2024 **per-season** MAE for step 5, while
   4.7101 is the **aggregate** (all-season) MAE for step 5; these are two
   different numbers for the same step, not two different runs. The
   HANDOFF.md draft that prompted this task conflated them.
4. **Confirmed full determinism directly.** Ran `python ff.py
   model-scorecard` twice back-to-back today; the two output
   `docs/model_scorecard.json` files are byte-for-byte identical
   (`diff` exit 0). A third run (with the Task 2 code change below) again
   reproduced identical MAE/rank/coverage numbers for every step.

No seed or caching fix was needed — the pipeline was already reproducible.

## Per-step table (this session's run; all three runs identical)

| Step | Aggregate MAE | 2024 MAE | Rank corr | 80% coverage | ROS MAE @3/6/9 | Δ vs prior commit |
|---|---|---|---|---|---|---|
| 1 trailing_average | 5.2023 | 5.1476 | 0.5559 | 0.8043 | 3.6279/3.6777/3.5046 | unchanged |
| 2 ffopportunity | 4.7721 | 4.7723 | 0.5971 | 0.8061 | 2.9223/2.8624/2.8964 | unchanged |
| 3 implied_team_total (not kept) | 4.7746 | 4.7739 | 0.5969 | 0.8045 | 2.9318/2.8781/2.8937 | unchanged |
| 4 structural_usage | 4.7392 | 4.7433 | 0.6042 | 0.8065 | 2.8740/2.8379/2.8502 | unchanged |
| 5 consensus_ecr (final) | 4.7101 | 4.7065 | 0.6096 | 0.8056 | 2.7620/2.7325/2.7943 | unchanged |

"Δ vs prior commit" compares against commit `ccad3fb` (before step-6
removal) — confirms steps 1-5 never moved.

## Task 2: per-step ROS error reporting (done this session)

Every top-level step already wrote `ros_mae_at_checkpoint` (weeks 3/6/9) via
`score_feature_set()`. The one gap was inside step 4's per-source ablation
(`structural_ablation` in `run_scorecard()`): each candidate source's dict
recorded `weekly_mae`/`delta_mae`/`season_wins`/`kept`/`coverage` but not its
ROS checkpoint numbers, even though `score_feature_set` already computed them
in `candidate_score`. Added one field:
`structural_ablation[source]["ros_mae_at_checkpoint"] = candidate_score["ros_mae_at_checkpoint"]`
in `public_model_scorecard.py`. Re-ran the scorecard; all MAE/rank/coverage
numbers are unchanged (this only exposes data already computed, it changes no
scoring), and the new field is populated for every structural source
(player_stats, snap_counts, participation, nextgen_stats, ftn_charting) in
`docs/model_scorecard.json`.

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
3. **Matchup shrinkage:** removed permanently. It regressed 2024
   (4.7065 -> 4.7078 per-season MAE) for a negligible aggregate gain
   (4.7101 -> 4.7099). Do not re-add without new held-out evidence.

## Task 3: Feature-Tier Variants and Live Inference (done this session)

Implemented three feature tiers to handle incomplete live data during the season:
1. `full`: The final selected features (base + xfpo + structural + consensus).
2. `no_ftn_ngs`: Full features minus FTN charting and NGS metrics.
3. `opp_ecr`: Only ffopportunity and consensus ECR features.

**Tier performance (2021-2025 walk-forward):**
| Tier | Weekly MAE | Rank Corr | 80% Coverage | ROS MAE (pts/game) @3/6/9 |
|---|---|---|---|---|
| full | 4.7101 | 0.6096 | 0.8056 | 2.7620 / 2.7325 / 2.7943 |
| no_ftn_ngs | 4.7076 | 0.6101 | 0.8079 | 2.7661 / 2.7219 / 2.7985 |
| opp_ecr | 4.7211 | 0.6067 | 0.8068 | 2.7663 / 2.7213 / 2.8121 |

*Note: ROS MAE is measured in units of absolute points per game error.*

**Live Inference & Fallback Strategy:**
At inference time (`ff.py public-inference` and injected into `packet` when `--projection-source public_model` is requested), we build a point-in-time feature row for the requested week. 
- The inference logic (`select_tier` in `public_inference.py`) dynamically checks which features are present.
- It selects the richest tier whose features are fully present.
- **ffopportunity missing:** For 2026 weeks the ffopportunity release hasn't covered (e.g. week 2), *none* of our model tiers can be run. We cannot rebuild expected points from current play-by-play (pbp) ourselves because the underlying `nflverse` ffopportunity XGBoost model and its preprocessing pipeline are not available in `nflreadpy` or our codebase. In this case, inference correctly identifies the missing data, aborts public model evaluation with an explicit error reason, and the `packet` falls back.
- The packet JSON includes a `public_model_inference` block labeling the `tier_applied`, `freshness`, and `reason`.

## Task list

1. ~~Remove matchup shrinkage.~~ Done.
2. ~~Add ROS error at weeks 3/6/9 to every step's report.~~ Done.
3. ~~Build feature-tier variants and live tier selection.~~ Done this session (see above).
4. Same-sample head-to-head: trained model blend vs sleeper+espn on
   identical player-weeks. Wire the blend in as opt-in first; promote to
   default only if it wins (decision 1).
5. Wire the model's ROS distributions into trade, buy-low, drop valuation
   (currently those intents use other signals; no model ROS integration
   yet).

Next prompt: pick up Task 5 (ROS distributions into trade).
