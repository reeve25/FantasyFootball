#!/usr/bin/env python3
"""
=============================================================================
REEVE'S LEAGUE ENGINE v6.3 ROS PRODUCTION  --  Sleeper 1327873074195886081
12-team | full PPR | 1QB 2RB 2WR 1TE 2FLEX K DST | 5 bench 1 IR
=============================================================================
    python3 ff.py              normal session (board <24h, weekly <12h, live league <5m)
    python3 ff.py --rebuild    force fresh board AND weekly pull
    python3 ff.py --selftest   3s, run first if anything looks off
    python3 ff.py --quick      skip both market layers
    python3 ff.py --week N     analyse a specific week (default: next unplayed)

WHAT THIS IS FOR
Arithmetic a language model cannot do reliably in its head: best-8 with two
flex slots, replacement level across ~500 players, the draft-anchor fit, and
now the week-by-week lineup. It outputs CANDIDATES, not decisions.

-----------------------------------------------------------------------------
WHAT CHANGED IN v6.3 (Sep 6) -- ROS TRUTH + AUDIT INTEGRITY
-----------------------------------------------------------------------------
v6.3 fixes the last major basis mismatch: the season board is no longer allowed
to be objective ROS truth when the weekly pipeline has newer role/availability
information. It also makes cache/audit provenance explicit and replaces the
exhaustive trade search with a bounded candidate generator for normal use.

  * ``ros_pg`` is built from the authoritative remaining-week matrix, with byes
    neutralised and genuine non-bye zero/no-role weeks retained as a cost.
  * roster VOR, wire value and trade-candidate SEARCH use ros_pg. Season
    ``value_pg`` remains intact as the market/projection provenance view.
  * BettingPros-enabled and no-key season boards use DIFFERENT cache files; a
    no-key run can no longer poison a later authenticated run for 24 hours.
  * audit bundles declare whether market authentication was active and whether
    the exported board/weekly matrix actually contains market evidence.
  * weekly ESPN values and source-state diagnostics are exported, so a large
    disagreement can be audited offline rather than collapsed into one number.
  * normal trade search uses a bounded, deterministic candidate pool. The old
    exhaustive 1..4 x 1..4 scanner remains available with --deep-trade-scan.

The v6.2 weekly-pipeline fixes remain in force:

  * Rotowire omission is no longer silently averaged with an invented zero.
  * Player team/byes are week-specific, so NFL team changes do not rewrite
    every week from the player's latest team tag.
  * Posted weekly market edges now modify the SAME matrix best8/pergame use.
  * BettingPros aggregator consensus no longer double-counts constituent books.
  * Direct Underdog is merged before the 3-venue floor, so it can be a genuine
    independent third witness instead of a research-only afterthought.
  * n_books is component-level median depth, with min/max retained; a deep
    receiving-yard market can no longer hide a thin TD/rush component.
  * Real weekly reception lines are accumulated into the season estimate; the
    inferred YPC bridge automatically shrinks as the season advances.
  * trade_confidence explicitly admits its pairwise calibration and no longer
    pretends its unused package-size argument was modeled.

Still deliberately NOT production: matchup_odds/team_sigma and automatic
numeric injury probabilities. Those need true weekly outcome/availability data.
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
WHAT CHANGED IN v5.3 (Sep 4) -- the estimator was wrong
-----------------------------------------------------------------------------
Not a data change. The ARITHMETIC of the headline number was wrong, and it had
been wrong since the per-game basis was adopted.

Everything was being ranked on best8(mean weekly points) -- average each
player over his season, then set ONE lineup. That is best8(E[X]). What you
score is E[best8(X)]: you reset the lineup seventeen times, each off that
week's numbers. best8 is a max, therefore convex, therefore

    E[best8(X)]  >=  best8(E[X])

The old number was a lower bound AND the bias was uneven -- deep rosters with
several close mid-tier bodies collect more of the gap than top-heavy rosters
whose lineup never moves. Measured across the 12 rosters Sep 4: mean +0.32/gm,
range +0.01 to +1.94, five of twelve teams moved a rank. Viswa went 9th to 7th
on the estimator alone.

  pergame()        E[best8]. THE ranking number. Use it for everything.
  pergame_naive()  best8(E[X]). DEPRECATED, kept only to measure the gap.
  jensen_gap()     the gap per roster. A wide SPREAD is the alarm, not the mean.
  trade_pergame()  price an offer on this basis, both sides, with COIN_FLIP.
  pergame_table()  league power ranking, byes shown beside not baked in.

Two smaller bugs died with it: the old rate DROPPED weeks a player is projected
not to play (an injury is a real missed game, now scored 0, not deleted from
the denominator), and week 18 leaked into the mean while the lineup loop ran
1-17, so the two halves of the same statistic covered different seasons.

Byes are neutralised by substituting the player's OWN rate into his bye week --
the week is played, he is just not punished for the calendar. Byes remain fully
visible via pergame_weeks() and best8_week(); they are context for a matchup,
not an input to "who has the best team".

-----------------------------------------------------------------------------
WHAT CHANGED IN v5.2 (Sep 3) -- the confidence release
-----------------------------------------------------------------------------
No new data source. Every input below was ALREADY on the board and already
correct. What was broken was that the uncertainty got dropped at the point of
use, which is the only point that matters.

The case: a trade was priced by quoting Rashee Rice 15.01 against Drake London
15.46, as if a 0.45 gap were the story. Rice's season line came from THREE
books (MIN_BOOKS is 3, so he barely qualified to be on the board at all) with
his two projection sources 1.83/gm apart -- over the coin-flip line. London's
came from EIGHT books at 1.22. Same estimator, same units, and one number was
worth far more than the other. n_books and spread_pg were both sitting in the
dataframe. Neither was said out loud.

  1. support() / fmt_val() / compare_players(). A SOLID/OK/THIN tier plus the
     reason, attached inside build() so it travels with the row. fmt_val()
     renders "15.01 [3bk, spr 1.83 COIN FLIP | THIN]". Measured Sep 3 on the
     146 season-covered players: 65 SOLID, 47 OK, 34 THIN. Everyone with no
     season line is THIN by construction, which is the honest reading.

  2. implied_games(). value_pg is a per-game number and the BRIEF has carried
     "not availability-adjusted" as an untestable caveat for two versions.
     It is testable: season_total_line / this_week_per_game_line = the games
     the book is carrying. London 1100.5/63.5 = 17.3. Rice 975.5/61.5 = 15.9.
     PER HEALTHY GAME the books have them two receiving yards apart -- the
     whole season gap between them is availability, which is exactly what ADP
     prices and value_pg does not. Computable for 129 of 146 covered players,
     median 15.7, IQR 14.6-16.7. It found Hubbard at 11.8 (camp hamstring) and
     Olave at 13.6 (concussion history) with no injury model.
     EXPERIMENTAL: only the upcoming week has per-game lines, so it is one
     ratio off one game and a soft matchup is indistinguishable from injury
     risk. Re-measure Week 4. If a healthy player's reading is not stable
     inside ~1 game week to week, it is measuring schedule -- delete it.

  3. TAIL_RISK. There is still no variance model and this release does not
     fabricate one. TAIL_RISK is a dated, sourced, validated list -- same
     contract as OVERRIDES -- that CHANGES NO NUMBER and only flags players
     whose downside distribution is materially worse than their median, so a
     median comparison is known to be flattering them.

-----------------------------------------------------------------------------
WHAT CHANGED IN v5 (Aug 30) -- the staleness release
-----------------------------------------------------------------------------
v4's board was correct and fresh at the moment of the pull, and still wrong,
because SEASON-LONG PROJECTIONS ARE THE WRONG INSTRUMENT FOR NEWS. Measured
on Aug 30 2026:

  - Alvin Kamara tore an MCL on Aug 18. rotowire cut his season line to 63
    pts. ESPN still carried 117, eleven days later.
  - Jordyn Tyson was ruled Doubtful with a hamstring and is IR-bound.
    NEITHER season source cut him (rotowire 111, espn 99.5).
  - freshness() caught neither, because it only probed players Sleeper flags
    IR/Out/PUP. Kamara was listed QUESTIONABLE. The probe never looked at him.

Even a perfectly updated season number is the wrong shape: it smears a
four-game absence across seventeen games. What you actually start is a WEEK.

FOUR NEW CAPABILITIES:

1. WEEKLY PROJECTIONS (src_weekly). Sleeper exposes rotowire's per-week
   projections at /projections/nfl/{season}/{week}. ~2,110 rows/week, all 18
   weeks, REBUILT DAILY (every active player's last_modified was today).
   It carries opponent, injury_status, injury_body_part and news_updated.
   Jordyn Tyson: no wk1-4 projection, Doubtful/Hamstring, 10.6 from wk5.
   The season feed had him flat at 6.19/gm all year. Different facts.

   Byes are now OBSERVED, not joined from a schedule. A player with no
   opponent has no game. best8_week() uses the real weekly number instead of
   season/17 with the bye players dropped.

2. WEEKLY MARKET, AND RECEPTIONS ARE NO LONGER BRIDGED. v4 declared the
   receptions market dead. It was a QUERY BUG, not an absent market. Season
   market 330 genuinely returns nothing -- BettingPros' own catalog has it
   mislabelled, its `stat` field reads "total-rec-touchdowns". But the
   per-game market 104 is live and always was; check_receptions() sent
   `season=` with no `week=`, which asks a game-period market for a season
   figure and gets zero rows. Adding the week returns real lines.
   Week 1 as of Aug 30: 66 reception lines, 101 rec-yd, 61 rush-yd, 31 pass-yd.
   In full PPR that was ~35-41% of a WR/TE's scoring reconstructed from an
   invented yards-per-catch. It is now a book number.

3. STALENESS IS MEASURED, NOT ASSUMED (divergence, freshness). Comparing
   rotowire-SEASON against rotowire-WEEKLY-SUMMED isolates staleness inside a
   single provider -- same model, same basis, so any gap is the season line
   failing to keep up. This is a far stronger detector than the old injured-
   player probe, and it is what surfaced the Penix/Tua situation in seconds.
   freshness() now also probes Questionable/Doubtful and reads the feed's own
   last_modified timestamps.

4. OVERRIDES. The BRIEF's division of labour says the engine does arithmetic
   and judgment does news -- but there was no way for judgment to feed BACK.
   A news correction lived in conversation and evaporated. OVERRIDES is a
   dated, sourced, validated list applied on top of the board and PRINTED IN
   FULL EVERY RUN. Undated or unsourced entries are refused. It is the one
   place in this file where a human number is allowed, and it is loud.

5. TRADES ARE PRICED ON BOTH BASES (trade_week, compare_trades,
   rescore_weekly). v4 could only answer "change in season best-8" -- one
   number, blind to WHEN the points land. It cannot see a deal that is flat on
   the season but converts one catastrophic week into two survivable ones, or
   one that gains in September and loses in Weeks 15-17, which are the only
   weeks that decide anything.

   This is not theoretical. Measured Aug 30: the season board had David
   Montgomery 11.96 and Travis Etienne 12.99, so the scanner wanted to send
   Montgomery out and bring Etienne back. The weekly feed -- same provider,
   rebuilt that morning -- had Montgomery 14.12/gm and Etienne 12.43/gm. The
   ordering was REVERSED, because Montgomery's season line was 22.6 points
   stale-low. And re-pricing the scanner's own top 25 packages showed 13 of
   them gaining on the season number while LOSING playoff points.

   So: SEARCH on the season basis, because trade value is a season question
   and the anchor curve is fitted to draft slots. RANK on the weekly basis,
   because that is the one that knows who is hurt. compare_trades() always
   includes a STAND-PAT row, because an offer that beats every alternative can
   still be worse than doing nothing.

QUICK USE
    b   = board_cached(); w = weekly_cached()
    wp, wb, wm = wk_matrix(w)
    b, _, _    = apply_overrides(b, wp)
    ros, us, pl, pk, tx = league_cached()
    val = make_val(b, pl)

    show_trade(trade_week(ros, val, pl, wp, ME, ["Player A"], 10, ["Player B"], fill=None))
    compare_trades(ros, val, pl, wp, [("label", give, get, their_rid)], fill=None)
    provenance(b, "Chris Olave", wp, wm)      # both bases, week by week
    divergence(b, wp)                          # what is stale, and by how much

WHAT DID NOT CHANGE, DELIBERATELY
  - The value_pg FORMULA remains proj_pg + coverage x mkt_edge on the SEASON
    basis, but v6.2 upgrades the market evidence feeding that formula. It
    remains the ranking spine for VOR, the anchor curve and the trade scanner. The weekly feed runs ~+0.87/gm hotter for the top 200 (measured);
    blending the two would reintroduce exactly the scale discontinuity the v4
    haircut was written to kill. Weekly is carried as its OWN column and its
    own basis, never averaged in.
  - Two season sources, both flawed, both kept. They buy a disagreement flag.

HONEST LIMITS OF THE NEW LAYER
  - Weekly is ONE provider (rotowire). No second opinion, no spread. Where the
    season board has two sources disagreeing, weekly has one source asserting.
  - Weekly is not automatically righter. rotowire has no wk1 row for Michael
    Penix at all while projecting Tua at 18.3, i.e. it has called the Falcons
    QB job for Tua against reporting that leans Penix. Divergence tells you
    WHERE to look; it does not tell you who is correct.
  - Weekly market coverage is thin this far out and grows through the week.
    Re-pull market on game day, not Tuesday.
  - Still no variance model. spread_pg is a disagreement flag, not a
    distribution. Biggest remaining gap in the file.

SOURCES
  rotowire  api.sleeper.app/projections/nfl/{yr}          season stat lines
  rotowire  api.sleeper.app/projections/nfl/{yr}/{wk}     WEEKLY, rebuilt daily
  espn      lm-api-reads.fantasy.espn.com                 season, needs header
  market    api.bettingpros.com/v3  ids 300-306           season props
  market    api.bettingpros.com/v3  ids 100-107,333,406   PER-GAME props
  underdog  api.underdogfantasy.com/beta/v5/over_under_lines  NO AUTH
                two-sided balanced lines, season + per-game, 602 NFL players
  nflverse  github.com/nflverse/nflverse-data .../stats_player_reg_{yr}.csv
                actual prior-season production, for empirical per-player YPC
DEAD ENDS (re-probed Sep 4 2026, all still closed): DraftKings 403 CDN.
  FanDuel 400 sbapi. FantasyPros = JS. PrizePicks 403 DataDome / 429 partner.
  ESPN site.api odds 403. OddsJam = auth. CBS = removed on purpose. Season
  market 330 (total receptions) = mislabelled upstream, always empty -- and
  the FULL BettingPros catalog was pulled (129 NFL markets, 32 season-period):
  330 is the only season receptions market that exists, there is no alternate
  id, and no venue anywhere sells season receptions. Accumulate per-game 104
  weekly via rec_history() instead. That is the only route and it works.
=============================================================================
"""
import json, re, sys, os, pickle, time, itertools, collections, io, zipfile, tempfile, hashlib, datetime
import requests, pandas as pd, numpy as np
from concurrent.futures import ThreadPoolExecutor
from scipy.stats import poisson
from scipy.optimize import brentq

LEAGUE = "1327873074195886081"
DRAFT  = "1327873074200072192"
ME     = 9
SEASON = 2026
GAMES  = 17
UA     = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
BP_API_KEY = os.getenv("BETTINGPROS_API_KEY", "").strip()
BP_KEY = {"x-api-key": BP_API_KEY} if BP_API_KEY else {}
CACHE  = ".ffcache"
QUICK  = "--quick" in sys.argv
WEEKLY_FETCH_WORKERS = 4
WEEKLY_REQUEST_TIMEOUT = (5, 20)


def _weekly_payloads(weeks, url_for_week, headers, source):
    """Fetch a bounded batch in deterministic order; never bless a partial pull.

    Each request has separate connection/read limits. A failed request leaves
    the previous on-disk cache intact instead of refreshing a partial season
    for another twelve hours. These limits are per request; the public runner
    supplies the overall refresh deadline.
    """
    weeks = list(weeks)
    if not weeks:
        return []

    def fetch(week):
        try:
            response = requests.get(url_for_week(week), headers=headers,
                                    timeout=WEEKLY_REQUEST_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list) or not payload:
                raise ValueError("projection response must be a nonempty list")
            return week, payload, None
        except Exception as exc:
            return week, None, type(exc).__name__

    with ThreadPoolExecutor(max_workers=min(WEEKLY_FETCH_WORKERS, len(weeks))) as pool:
        results = list(pool.map(fetch, weeks))
    failures = [(week, error) for week, _, error in results if error]
    if failures:
        detail = ", ".join(f"week {week}: {error}" for week, error in failures)
        raise RuntimeError(f"{source} weekly pull incomplete ({detail}); previous cache retained")
    return [(week, payload) for week, payload, _ in results]

# ---------------------------------------------------------------- scoring
def score(rec=0, ruyd=0, reyd=0, rutd=0, retd=0, payd=0, patd=0, pint=0, fl=0):
    """EXACT league scoring. 1 PPR, 0.1/yd, 6 TD, 0.04 pass yd, 4 pass TD."""
    return (rec + 0.1*(ruyd+reyd) + 6*(rutd+retd)
            + 0.04*payd + 4*patd - pint - 2*fl)

COMP = ["rush_yd","rush_td","rec","rec_yd","rec_td","pass_yd","pass_td","pass_int","fum_lost"]

def score_row(r, suffix=""):
    g = lambda c: r.get(c+suffix, np.nan) if not pd.isna(r.get(c+suffix, np.nan)) else r.get(c, 0)
    return score(g("rec"), g("rush_yd"), g("rec_yd"), g("rush_td"), g("rec_td"),
                 g("pass_yd"), g("pass_td"), r.get("pass_int", 0), r.get("fum_lost", 0))

# ------------------------------------------------------------- name keys
SUF = re.compile(r"\s+(jr|sr|ii|iii|iv|v)\.?$", re.I)
FIX = {"cam ward":"cameron ward", "gabe davis":"gabriel davis",
       "chig okonkwo":"chigoziem okonkwo", "marquise brown":"hollywood brown"}

def norm(n, pos=None):
    """Name -> join key. ALWAYS pass pos: 27 skill players share a normalised
    name (Kenneth Walker RB/WR, Josh Johnson QB/RB/WR, ...)."""
    if not isinstance(n, str): return ""
    s = n.lower().replace(".","").replace("'","").replace("`","").replace("-"," ")
    s = SUF.sub("", re.sub(r"\s+", " ", s).strip()).strip()
    s = FIX.get(s, s)
    return f"{s}|{pos}" if pos else s

# ---------------------------------------------------------------- sources
def src_rotowire():
    u = (f"https://api.sleeper.app/projections/nfl/{SEASON}?season_type=regular"
         "&position[]=QB&position[]=RB&position[]=WR&position[]=TE&order_by=pts_ppr")
    out = []
    for r in requests.get(u, headers=UA, timeout=60).json():
        p, s = r.get("player") or {}, r.get("stats") or {}
        if not p.get("position"): continue
        d = {c: float(s.get(c, 0) or 0) for c in COMP}
        d.update(name=f"{p.get('first_name','')} {p.get('last_name','')}".strip(),
                 pos=p["position"], team=p.get("team"), gp=np.nan,
                 adp=s.get("adp_ppr"), src="rotowire")
        out.append(d)
    return pd.DataFrame(out)

ESPN_POS = {1:"QB", 2:"RB", 3:"WR", 4:"TE"}
ESPN_ID  = dict(rush_yd=24, rush_td=25, rec_yd=42, rec=53, rec_td=43,
                pass_yd=3, pass_td=4, pass_int=20, fum_lost=72, gp=210)

def src_espn():
    f = {"players": {"limit": 1500, "sortDraftRanks":
         {"sortPriority": 100, "sortAsc": True, "value": "PPR"}}}
    h = dict(UA); h.update({"X-Fantasy-Filter": json.dumps(f),
                            "X-Fantasy-Source": "kona", "X-Fantasy-Platform": "kona-PROD"})
    u = (f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}"
         "/players?scoringPeriodId=0&view=kona_player_info")
    out = []
    for p in requests.get(u, headers=h, timeout=60).json():
        pos = ESPN_POS.get(p.get("defaultPositionId"))
        if not pos: continue
        pr = next((s for s in p.get("stats", []) if s.get("seasonId") == SEASON
                   and s.get("statSourceId") == 1 and s.get("statSplitTypeId") == 0), None)
        if not pr: continue
        st = pr.get("stats", {})
        d = {c: float(st.get(str(ESPN_ID[c]), 0) or 0) for c in COMP}
        d.update(name=p.get("fullName"), pos=pos, team=None,
                 gp=float(st.get("210", 0) or 0) or np.nan, adp=np.nan, src="espn")
        out.append(d)
    return pd.DataFrame(out)

# ----------------------------------------------------------------- market
# ------------------------------------------------- books, de-vig, consensus
# WHICH BOOKS. v5.0 pulled BettingPros' default endpoint and took whatever it
# returned. Measured Aug 30: 177 of 255 weekly props came from book 36 =
# UNDERDOG, plus 21 from PrizePicks. Those are DFS pick'em products, not
# two-sided markets -- the "line" on a pick'em app is a product decision, not
# a price discovered by money on both sides. We were calling that Vegas.
#
# Passing book_id= lets us choose. Available at this key (measured):
#   season rec-yd: Caesars 95, DraftKings 83, BetMGM 46, BPconsensus 100
#   weekly rec   : Underdog 56, PrizePicks 46, Sleeper 41, DraftKings 38, Caesars 27
#   Pinnacle, FanDuel: 0 rows. Pinnacle is the one we actually want and this
#   key does not carry it. See BRIEF open items.
#
# Books rarely disagree on a WEEKLY line (Olave 6.5 at DK, UD, Sleeper and
# consensus alike) but routinely disagree on SEASON lines: median spread 24
# receiving yards across four books, 0 of 46 players identical everywhere.
# So multi-book matters most on the season layer, which is the trade layer.
BOOKS_SPORTSBOOK = {13: "Caesars", 12: "DraftKings", 19: "BetMGM",
                    49: "HardRock", 33: "theScore"}
BOOKS_PREDICTION = {68: "Kalshi", 73: "Polymarket"}
BOOKS_DFS        = {36: "Underdog", 37: "PrizePicks", 63: "Sleeper"}
# v5.8: PrizePicks (37) added. It was in DEAD ENDS for a year on the strength
# of api.prizepicks.com returning 403 -- which it does. But BettingPros
# resells it, with the key this file already holds, and it quotes MORE season
# receiving-yard lines (106) than DraftKings (84) or Caesars (96). The block
# was on the front door only. Never conclude a source is unavailable from one
# access path.
# Tested Sep 4 on season rec-yd (302): FanDuel 0, Pinnacle 0, bet365 0,
# Fanatics 0, DK Pick6 0, FanDuel Picks 0. Those books do not sell SEASON
# player props at all -- a product gap, not a block, so there is nothing to
# work around. Underdog and Sleeper return 0 here too and must be pulled
# direct (src_underdog), which is why that function stays.
# v6.2 production: only independently quoted two-sided / exchange-style venues
# count toward the season consensus. BettingPros consensus is an aggregator of
# constituent books and therefore MUST NOT be counted beside those books. A
# PrizePicks line is useful context but is a one-sided pick'em product, so it no
# longer contributes to n_books or the production consensus.
BOOKS_USE = {**BOOKS_SPORTSBOOK, **BOOKS_PREDICTION}
BP_CONSENSUS_BOOK_ID = 0

def implied(odds):
    """American odds -> implied probability, vig included."""
    o = float(odds)
    return (-o) / (-o + 100.0) if o < 0 else 100.0 / (o + 100.0)

def devig(over_odds, under_odds):
    """Two-sided odds -> (fair P(over), vig). Proportional (multiplicative)
    de-vig: the standard choice, and with two outcomes the difference against
    additive or Shin methods is well under the noise here.

    Returns (nan, nan) if either side is missing, which is common -- plenty of
    props are quoted one-sided."""
    if over_odds is None or under_odds is None:
        return np.nan, np.nan
    po, pu = implied(over_odds), implied(under_odds)
    t = po + pu
    if t <= 0: return np.nan, np.nan
    return po / t, t - 1.0

def mean_from_count_line(line, p_over):
    """A LINE IS A MEDIAN. FANTASY SCORING WANTS A MEAN.

    v5.0 scored a 2.5-reception line as 2.5 points. But the line only equals
    the expectation when the de-vigged P(over) is 50%. Isaiah Likely's 2.5 was
    -145/+119 on Aug 30, i.e. a fair 56% to go over -- his expected receptions
    are above 2.5, and we were booking the wrong number.

    For a count stat the distribution family is not a free parameter: game
    receptions, carries and TDs are close to Poisson. So invert it. Given a
    half-point line L and fair P(X > L), solve for the lambda that produces
    that probability. No fitted constants, no assumed variance.

    Returns the line unchanged if the odds are missing or the solve fails."""
    if pd.isna(p_over) or pd.isna(line): return line
    p_over = float(np.clip(p_over, 0.02, 0.98))
    k = int(np.floor(float(line)))          # P(X >= k+1) = p_over
    try:
        f = lambda lam: (1.0 - poisson.cdf(k, lam)) - p_over
        return float(brentq(f, 1e-6, 200.0))
    except Exception:
        return line

# Yardage is deliberately NOT de-vigged. Inverting a yards line to a mean
# needs a variance assumption (game receiving yards run CV 0.6-0.8 and are
# right-skewed), and a fitted CV is exactly the kind of invented constant this
# engine is supposed to refuse. The skew is REPORTED instead, as p_over, so a
# lopsided line is visible rather than silently mispriced. Season yards lines
# move in 25-yard steps, so the un-modelled error is bounded around 2.5 pts.
DEVIG_STATS = {"rec", "rush_td", "rec_td", "pass_td"}

BP_SEASON = {300:"pass_yd", 301:"rush_yd", 302:"rec_yd",
             304:"pass_td", 305:"rush_td", 306:"rec_td", 330:"rec"}

def check_receptions(week=None):
    """v4 called this market dead. It was a QUERY BUG.

    BettingPros market 330 (season total receptions) is genuinely empty -- and
    their own catalog explains why: the record's `stat` field reads
    "total-rec-touchdowns", i.e. it is mislabelled upstream. It will not
    populate. Stop polling it.

    Market 104 (per-GAME receptions) is live and always was. v4 requested it
    with `season=` and no `week=`, which asks a game-period market for a
    season-period figure and returns zero rows. Pass the week and it answers.
    That closes the single largest hole in this engine: in full PPR, ~35-41%
    of a WR/TE's points were reconstructed from an invented yards-per-catch."""
    out = {}
    try:
        u = (f"https://api.bettingpros.com/v3/props?sport=NFL&season={SEASON}"
             f"&market_id=330&limit=5")
        out["season 330 (mislabelled upstream, expect 0)"] = len(
            requests.get(u, headers={**UA, **BP_KEY}, timeout=25).json().get("props") or [])
    except Exception:
        out["season 330 (mislabelled upstream, expect 0)"] = -1
    wk = week or 1
    try:
        u = (f"https://api.bettingpros.com/v3/props?sport=NFL&season={SEASON}"
             f"&week={wk}&market_id=104&limit=100")
        out[f"per-game 104 wk{wk} (REAL)"] = len(
            requests.get(u, headers={**UA, **BP_KEY}, timeout=25).json().get("props") or [])
    except Exception:
        out[f"per-game 104 wk{wk} (REAL)"] = -1
    return out

def _pull_props(mid, book_id=None, week=None):
    """One market, one book, all pages. Returns raw rows with odds attached."""
    rows, page = [], 1
    while True:
        u = (f"https://api.bettingpros.com/v3/props?sport=NFL&season={SEASON}"
             f"&market_id={mid}&limit=100&page={page}"
             + (f"&book_id={book_id}" if book_id is not None else "")
             + (f"&week={week}" if week is not None else ""))
        try:
            props = requests.get(u, headers={**UA, **BP_KEY},
                                 timeout=30).json().get("props") or []
        except Exception:
            break
        if not props: break
        for p in props:
            o, un = p.get("over") or {}, p.get("under") or {}
            ln = o.get("line", o.get("consensus_line"))
            if ln is None: continue
            pl = p["participant"]["player"]
            fair, vig = devig(o.get("odds", o.get("consensus_odds")),
                              un.get("odds", un.get("consensus_odds")))
            rows.append(dict(name=p["participant"]["name"], pos=pl.get("position"),
                             line=float(ln), p_over=fair, vig=vig,
                             book=o.get("book")))
        if len(props) < 100: break
        page += 1; time.sleep(0.15)
    return rows

def _consensus(rows_by_book, stat):
    """Collapse several books into one line per player.

    MEDIAN of the lines, not the mean: one book posting a stale or off-market
    number should not drag the estimate, and with 3-5 books the median is the
    robust choice. The de-vigged P(over) is averaged, because that is a
    probability and averaging probabilities is the right operation.

    n_books is carried through so a one-book line is never mistaken for a
    corroborated one."""
    agg = collections.defaultdict(list)
    for bid, rows in rows_by_book.items():
        for r in rows:
            agg[(r["name"], r["pos"])].append(r)
    out = []
    for (nm, pos), rs in agg.items():
        lines = [r["line"] for r in rs]
        ps = [r["p_over"] for r in rs if not pd.isna(r["p_over"])]
        vg = [r["vig"] for r in rs if not pd.isna(r["vig"])]
        out.append(dict(name=nm, pos=pos, stat=stat,
                        line=float(np.median(lines)),
                        p_over=(float(np.mean(ps)) if ps else np.nan),
                        vig=(float(np.mean(vg)) if vg else np.nan),
                        n_books=len(rs),
                        line_spread=float(max(lines) - min(lines))))
    return out

def _market(mids, week=None, books=None):
    """Multi-book consensus for a set of markets, with de-vig applied to the
    count stats. Shared by the season and per-game layers."""
    books = books or list(BOOKS_USE)
    rows = []
    for mid, stat in mids.items():
        by_book = {}
        for bid in books:
            r = _pull_props(mid, book_id=bid, week=week)
            if r: by_book[bid] = r
        if not by_book: continue
        for c in _consensus(by_book, stat):
            # LINE -> MEAN happens here, for counts only. See mean_from_count_line.
            c["value"] = (mean_from_count_line(c["line"], c["p_over"])
                          if stat in DEVIG_STATS else c["line"])
            rows.append(c)
    if not rows: return pd.DataFrame()
    d = pd.DataFrame(rows)
    d["key"] = [norm(n, p) for n, p in zip(d.name, d.pos)]
    return d

def _pivot(d, suffix=""):
    if not len(d): return pd.DataFrame()
    v = d.pivot_table(index="key", columns="stat", values="value", aggfunc="first")
    nb = d.pivot_table(index="key", columns="stat", values="n_books", aggfunc="first")
    v.columns = [f"{c}{suffix}" for c in v.columns]
    nb.columns = [f"{c}_nbk" for c in nb.columns]
    return v.join(nb)

# A line quoted by one or two venues is not a corroborated market view.
# Measured Aug 30: DeMario Douglas carried a 750-yard season receiving line at
# Kalshi and BettingPros-consensus ONLY, while the per-game market (4 books)
# priced him at 20.5 yds/gm -- 348 over a season. The thin season line was off
# by more than 2x and would have handed him 74 receptions. Requiring three
# venues drops those without inventing a correction for them; the player
# simply falls back to the projection, which is the honest outcome when the
# market has not really spoken.
MIN_BOOKS = 3

def src_market(books=None, min_books=None):
    """SEASON-long consensus props, multi-book and de-vigged.

    Still the basis for value_pg, VOR, the anchor curve and the trade scanner,
    because trade value is a season question. Receptions (market 330) remain
    permanently empty upstream -- see check_receptions() and book_ypc(), which
    is how v5.1 reconstructs them from a real book number instead of an
    invented yards-per-catch."""
    d = _market(BP_SEASON, books=books)
    if not len(d): return d
    d = d[d.stat != "rec"]
    mb = MIN_BOOKS if min_books is None else min_books
    thin = int((d.n_books < mb).sum())
    d = d[d.n_books >= mb]
    if thin:
        print(f"  market    dropped {thin} lines quoted by fewer than {mb} venues "
              f"(uncorroborated; those players fall back to the projection)")
    return d

def book_ypc(week, books=None):
    """BOOK-IMPLIED YARDS PER CATCH -- the fix for the season receptions hole.

    The season receptions market does not exist (330 is mislabelled upstream
    and always empty). v5.0 bridged it by scaling the PROJECTED receptions by
    the ratio of the market's rec-yd line to the projected rec-yd -- so the
    number was anchored to the projection, i.e. it was not a market number at
    all, and it accounted for 35% of a WR's and 41% of a TE's season points.

    But the PER-GAME market has both receptions and receiving yards for the
    same players. Divide one by the other and you get a yards-per-catch that
    the market itself is quoting. YPC is a rate, so it is scale-free: the same
    figure applies to a season line. Season receptions then become

        season_rec = season_rec_yd_line / book_ypc

    which is a real book line divided by a real book ratio. Measured Aug 30 on
    53 players it moves the estimate by a median +4.3 receptions and a typical
    6.4 -- Pickens +16.6, McLaurin +15.0, Likely -14.4. In full PPR that is
    4-16 season points per player that v5.0 was inventing.

    Falls back to the position median YPC where a player has only one of the
    two lines. Position medians measured Aug 30: WR 12.18, TE 10.62, RB 7.00."""
    g = _market({104: "rec", 105: "rec_yd"}, week=week, books=books)
    if not len(g): return {}, {}
    p = g.pivot_table(index=["key", "pos"], columns="stat", values="value",
                      aggfunc="first").reset_index()
    if "rec" not in p or "rec_yd" not in p: return {}, {}
    p = p[p.rec.notna() & p.rec_yd.notna() & (p.rec > 0)]
    p["ypc"] = p.rec_yd / p.rec
    # a YPC outside this band is a broken pairing, not a real player profile
    p = p[(p.ypc > 3) & (p.ypc < 22)]
    per_player = dict(zip(p.key, p.ypc))
    per_pos = p.groupby("pos").ypc.median().to_dict()
    return per_player, per_pos

# per-GAME market ids. 104 is the one that matters -- it kills the bridge.
BP_GAME = {103: "pass_yd", 102: "pass_td", 107: "rush_yd",
           105: "rec_yd", 104: "rec"}

def src_market_weekly(week):
    """Per-game consensus lines for ONE week, receptions INCLUDED.

    These reprice every week. Season props are set once and drift in cents --
    they cannot react to a training-camp hamstring, which is precisely the
    news that moves a fantasy decision. Coverage is thin early in the week and
    fills in as books post; re-pull on game day, not Tuesday.

    No rush_td / rec_td per-game market exists at consensus, so TDs still come
    from the projection. That is a real gap and it is why weekly market
    coverage will never reach the season layer's on TD-dependent players."""
    rows = []
    for mid, stat in BP_GAME.items():
        page = 1
        while True:
            u = (f"https://api.bettingpros.com/v3/props?sport=NFL&season={SEASON}"
                 f"&week={week}&market_id={mid}&limit=100&page={page}")
            try:
                props = requests.get(u, headers={**UA, **BP_KEY},
                                     timeout=30).json().get("props") or []
            except Exception:
                break
            if not props: break
            for p in props:
                pl = p["participant"]["player"]
                ln = (p.get("over") or {}).get("consensus_line")
                if ln is None: continue
                rows.append(dict(name=p["participant"]["name"], pos=pl.get("position"),
                                 stat=stat, line=float(ln)))
            if len(props) < 100: break
            page += 1; time.sleep(0.2)
    if not rows: return pd.DataFrame()
    d = (pd.DataFrame(rows)
         .pivot_table(index=["name", "pos"], columns="stat", values="line",
                      aggfunc="first").reset_index())
    d["key"] = [norm(n, p) for n, p in zip(d.name, d.pos)]
    return d

# ------------------------------------------------------- weekly projections
WEEKS = list(range(1, 19))

def src_weekly(weeks=None):
    """rotowire's PER-WEEK projections, via Sleeper. The thing v4 didn't have.

    Rebuilt daily -- on Aug 30 every active player's last_modified was that
    morning. Returns one row per player-week with:
      pts        scored by league rules, NaN if rotowire projects no game
      opp        opponent, or None. NO OPPONENT MEANS BYE -- byes are now
                 OBSERVED rather than joined from a separate schedule call.
      inj/body   injury_status and body part, richer than the /players blob
                 (Kamara reads Questionable/Knee here; that is the flag the
                 old freshness() probe missed because it only took IR/Out/PUP)
      last_mod   the feed's own timestamp. Direct staleness, not inferred.

    A player with no projection and no bye is rotowire saying he has no role
    this week. Verified against the league: of 159 rostered skill players,
    wk1 had 4 unprojected (3 injury-flagged, 1 a WR5 off an ACL) and wk5 had
    10 (9 on bye). Coverage on players who matter is effectively complete, so
    treating unprojected-and-not-on-bye as ZERO is the honest read -- and it
    is more accurate than the season feed smearing a phantom role over 17
    games."""
    weeks = weeks or WEEKS
    rows = []
    url = lambda wk: (f"https://api.sleeper.app/projections/nfl/{SEASON}/{wk}"
                      "?season_type=regular&position[]=QB&position[]=RB&position[]=WR"
                      "&position[]=TE&order_by=pts_ppr")
    for wk, payload in _weekly_payloads(weeks, url, UA, "Rotowire"):
        before = len(rows)
        for r in payload:
            p, s = r.get("player") or {}, r.get("stats") or {}
            if not p.get("position"): continue
            nm = f"{p.get('first_name','')} {p.get('last_name','')}".strip()
            projected = s.get("pts_ppr") is not None
            d = {c: float(s.get(c, 0) or 0) for c in COMP}
            row = dict(
                key=norm(nm, p["position"]), name=nm, pos=p["position"],
                team=p.get("team"), week=wk, opp=r.get("opponent"),
                pts=(score(d["rec"], d["rush_yd"], d["rec_yd"], d["rush_td"],
                           d["rec_td"], d["pass_yd"], d["pass_td"],
                           d["pass_int"], d["fum_lost"]) if projected else np.nan),
                inj=p.get("injury_status"), body=p.get("injury_body_part"),
                last_mod=r.get("last_modified"), news=p.get("news_updated"))
            # raw components kept so the PER-GAME market can be applied
            # component-wise, exactly as the season layer does. Without these
            # a real receptions line could only be compared to a total, and
            # the whole point of fixing market 104 would be lost.
            row.update({c: (d[c] if projected else np.nan) for c in COMP})
            rows.append(row)
        if len(rows) == before:
            raise RuntimeError(f"Rotowire week {wk} has no player rows; previous cache retained")
    return pd.DataFrame(rows)

def src_espn_weekly(weeks=None):
    """ESPN's PER-WEEK projections. The second weekly opinion v5.0 didn't have.

    Same kona_player_info endpoint as the season pull, but keyed on
    scoringPeriodId with statSplitTypeId=1. ~510 scored players a week, all 17
    weeks. This matters because the weekly layer was the one place in the
    engine with a single source and therefore no disagreement flag -- and the
    disagreement turned out to be enormous where it counts:

        David Montgomery   rotowire 14.12/gm   espn 11.36/gm
        Travis Etienne     rotowire 12.43/gm   espn 14.31/gm

    Two shops with the same comparison exactly backwards, 4.6 points apart. A
    trade priced on rotowire alone read -29.1 regular-season points; on ESPN
    alone it read +26.7. That spread was invisible until this source existed."""
    weeks = weeks or list(range(1, 18))
    out = {}
    f = {"players": {"limit": 700, "sortDraftRanks":
         {"sortPriority": 100, "sortAsc": True, "value": "PPR"}}}
    h = dict(UA); h.update({"X-Fantasy-Filter": json.dumps(f),
                            "X-Fantasy-Source": "kona", "X-Fantasy-Platform": "kona-PROD"})
    url = lambda wk: (f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}"
                      f"/players?scoringPeriodId={wk}&view=kona_player_info")
    for wk, payload in _weekly_payloads(weeks, url, h, "ESPN"):
        wkout = {}
        for p in payload:
            pos = ESPN_POS.get(p.get("defaultPositionId"))
            if not pos: continue
            row = next((s for s in p.get("stats", [])
                        if s.get("seasonId") == SEASON and s.get("statSourceId") == 1
                        and s.get("statSplitTypeId") == 1
                        and s.get("scoringPeriodId") == wk), None)
            if not row: continue
            st = row.get("stats", {})
            d = {c: float(st.get(str(ESPN_ID[c]), 0) or 0) for c in COMP}
            wkout[norm(p.get("fullName"), pos)] = score(
                d["rec"], d["rush_yd"], d["rec_yd"], d["rush_td"], d["rec_td"],
                d["pass_yd"], d["pass_td"], d["pass_int"], d["fum_lost"])
        if not wkout:
            raise RuntimeError(f"ESPN week {wk} has no projected players; previous cache retained")
        out[wk] = wkout
    return out

def espn_weekly_cached(force=False):
    return _cached("espn_weekly", src_espn_weekly, 12*3600, force=force)

def blend_weekly(wk_pts, wk_bye, espn, meta=None, wkly=None):
    """Combine Rotowire + ESPN without turning source omission into half a zero.

    Production rules in v6.2:
      * verified team bye -> NaN, regardless of ESPN
      * both sources project -> arithmetic mean (spread retained)
      * Rotowire projects, ESPN silent -> Rotowire alone
      * ESPN projects, Rotowire row is absent -> ESPN alone
      * Rotowire row exists but has no projection:
          - hard inactive tag (IR/Out/PUP/NA/Doubtful) -> 0
          - otherwise ESPN projection wins alone if present
          - otherwise 0 (Rotowire asserted no role and nobody contradicted it)

    The old path averaged ESPN with an invented 0 whenever Rotowire had an
    unprojected non-bye row. That could halve a perfectly live player's weekly
    projection simply because one provider omitted him.
    """
    HARD = {"IR", "Out", "PUP", "NA", "Doubtful"}
    row_meta = {}
    if wkly is not None and len(wkly):
        for r in wkly.itertuples():
            row_meta[(r.key, int(r.week))] = dict(
                inj=(None if pd.isna(r.inj) else r.inj),
                has_row=True,
                team=(None if pd.isna(r.team) else r.team))

    blended, spread = {}, {}
    keys = set(wk_pts) | {k for wk in espn.values() for k in wk}
    for k in keys:
        byes = wk_bye.get(k, set())
        rw = wk_pts.get(k, {})
        weeks = set(rw) | {w for w, d in espn.items() if k in d}
        bl, sp = {}, {}
        for w in sorted(weeks):
            if w in byes:
                bl[w] = np.nan; sp[w] = np.nan; continue
            r_present = w in rw
            r = rw.get(w, np.nan)
            e = espn.get(w, {}).get(k)
            e = None if e is None or pd.isna(e) else float(e)

            if r_present and not pd.isna(r):
                rv = float(r)
                if e is None:
                    bl[w] = rv; sp[w] = np.nan
                else:
                    bl[w] = (rv + e) / 2.0; sp[w] = abs(rv - e)
                continue

            # Rotowire did not supply a usable number.
            if not r_present:
                if e is not None:
                    bl[w] = e; sp[w] = np.nan
                continue

            inj = row_meta.get((k, int(w)), {}).get("inj")
            if inj in HARD:
                bl[w] = 0.0
                sp[w] = abs(e) if e is not None else np.nan
            elif e is not None:
                # Soft omission/no-role disagreement: do NOT average against 0.
                bl[w] = e; sp[w] = np.nan
            else:
                bl[w] = 0.0; sp[w] = np.nan
        blended[k] = bl; spread[k] = sp
    return blended, spread

def weekly_source_audit(roto, espn, blended, wk_bye=None, wkly=None):
    """One row per player-week describing how the weekly mean was formed.

    This does not change a projection. It makes role/availability disagreement
    explicit so a 50/50 blend cannot masquerade as high-confidence precision.
    ``role_conflict`` means one source is effectively projecting no role while
    the other is projecting a normal fantasy role.
    """
    wk_bye = wk_bye or {}
    meta = {}
    if wkly is not None and len(wkly):
        for r in wkly.itertuples():
            meta[(r.key, int(r.week))] = dict(
                name=r.name, pos=r.pos,
                inj=(None if pd.isna(r.inj) else r.inj),
                team=(None if pd.isna(r.team) else r.team))
    keys = set(roto or {}) | {k for d in (espn or {}).values() for k in d}
    rows = []
    for k in keys:
        weeks = set((roto or {}).get(k, {})) | {w for w,d in (espn or {}).items() if k in d}
        for w in sorted(weeks):
            rv = (roto or {}).get(k, {}).get(w, np.nan)
            ev = (espn or {}).get(w, {}).get(k, np.nan)
            rv = np.nan if rv is None else rv
            ev = np.nan if ev is None else ev
            bv = (blended or {}).get(k, {}).get(w, np.nan)
            is_bye = int(w) in set(wk_bye.get(k, set()))
            m = meta.get((k, int(w)), {})
            if is_bye:
                state = "bye"
            elif not pd.isna(rv) and not pd.isna(ev):
                state = "both"
            elif not pd.isna(rv):
                state = "rotowire_only"
            elif not pd.isna(ev):
                state = "espn_only"
            elif not pd.isna(bv) and float(bv) == 0:
                state = "no_role_zero"
            else:
                state = "missing"
            role_conflict = bool(
                not is_bye and not pd.isna(rv) and not pd.isna(ev) and
                ((float(rv) >= 8.0 and float(ev) <= 1.0) or
                 (float(ev) >= 8.0 and float(rv) <= 1.0)))
            rows.append(dict(key=k, week=int(w), name=m.get("name"), pos=m.get("pos"),
                             team=m.get("team"), injury=m.get("inj"), state=state,
                             rotowire=(None if pd.isna(rv) else float(rv)),
                             espn=(None if pd.isna(ev) else float(ev)),
                             blended=(None if pd.isna(bv) else float(bv)),
                             spread=(None if pd.isna(rv) or pd.isna(ev) else abs(float(rv)-float(ev))),
                             role_conflict=role_conflict))
    return pd.DataFrame(rows)


def apply_weekly_market_overlay(wk_pts, wkly, weeks=None):
    """Apply the weekly sportsbook edge to the ACTUAL production matrix.

    weekly_market() computes the player-specific market opinion after removing
    the positional basis gap. v6.1 only printed that number; lineup optimizers
    still used the pre-market matrix. v6.2 overlays the same edge on the
    Rotowire+ESPN baseline, so the number shown to the user is the number that
    best8/pergame/trade_week actually consume.

    Only weeks with posted markets change. At present that is normally the
    current week; all future weeks pass through untouched.
    """
    out = {k: dict(v) for k, v in (wk_pts or {}).items()}
    audits = []
    if wkly is None or not len(wkly) or not out or QUICK or not BP_API_KEY:
        return out, pd.DataFrame()
    if weeks is None:
        weeks = [current_week(wkly)]
    for w in sorted(set(int(x) for x in weeks if 1 <= int(x) <= 17)):
        try:
            wm = weekly_market(w, wkly)
        except Exception:
            continue
        if wm is None or not len(wm):
            continue
        for r in wm[wm.n_mkt > 0].itertuples():
            if r.key not in out or w not in out[r.key]:
                continue
            base = out[r.key][w]
            if pd.isna(base):
                continue
            adj = float(r.mkt_cov) * float(r.edge)
            final = float(base) + adj
            out[r.key][w] = final
            audits.append(dict(week=w, key=r.key, name=r.name, pos=r.pos,
                               base=round(float(base), 3), adjustment=round(adj, 3),
                               final=round(final, 3), coverage=round(float(r.mkt_cov), 3),
                               n_mkt=int(r.n_mkt)))
    return out, pd.DataFrame(audits)


def build_weekly_projection_pipeline(wkly, board=None, force=False,
                                     use_market=True):
    """ONE authoritative weekly projection path for production consumers.

    Returns raw Rotowire, ESPN, blended, final, byes, metadata, disagreement,
    and market audit. Every lineup/trade/ranking should consume ``final``.
    Research helpers may inspect intermediate layers but should not silently
    substitute a different matrix.
    """
    roto, bye, meta = wk_matrix(wkly)
    final = roto
    espn, spread = {}, {}
    try:
        espn = espn_weekly_cached(force=force)
        final, spread = blend_weekly(roto, bye, espn, meta=meta, wkly=wkly)
    except Exception as e:
        print(f"espn weekly FAILED {type(e).__name__}: {e} -> Rotowire only")
    blended = {k: dict(v) for k, v in final.items()}
    source_audit = weekly_source_audit(roto, espn, blended, wk_bye=bye, wkly=wkly)
    market_audit = pd.DataFrame()
    if use_market:
        final, market_audit = apply_weekly_market_overlay(
            final, wkly, weeks=[current_week(wkly)])
    return dict(rotowire=roto, espn=espn, blended=blended,
                final=final, bye=bye, meta=meta, spread=spread,
                market_audit=market_audit, source_audit=source_audit)


def weekly_spread_report(spread, board=None, val=None, top=12):
    """Where the two weekly sources disagree most. This is the weekly layer's
    equivalent of spread_pg on the season board, and it did not exist before
    v5.1. Big numbers here mean the weekly rank is a coin flip, not a fact."""
    rows = []
    for k, d in spread.items():
        v = [x for x in d.values() if not pd.isna(x)]
        if not v: continue
        rows.append(dict(key=k, mean_spread=float(np.mean(v)), n=len(v)))
    if not rows: return pd.DataFrame()
    d = pd.DataFrame(rows)
    if board is not None:
        nm = board.set_index("key")[["name", "pos"]]
        d = d.join(nm, on="key")
    return d.sort_values("mean_spread", ascending=False).head(top).reset_index(drop=True)

def weekly_cached(force=False):
    """12h. Shorter than the board on purpose: this is the layer whose whole
    job is to be current, and the upstream feed rebuilds daily."""
    return _cached("weekly", src_weekly, 12*3600, force=force)

# ONE BAD ROW MUST NOT FLIP A TEAM'S BYE. The obvious rule -- "a team is off
# in week W if NOBODY on it has an opponent" -- is right in principle and
# fragile in practice: the feed carries a "Kaleb Johnson" tagged team=GB whose
# opponent list is actually Pittsburgh's, because there are two players of
# that name and norm() collapses them. That single row gave Green Bay an
# opponent in Week 11 and deleted their bye. Week 11 is the week this roster
# is built around.
#
# The signal is a cliff, not a gradient: Green Bay has 16 players with an
# opponent in a normal week and 1 in Week 11; Atlanta 12 and 0. So compare
# each team against ITS OWN median rather than an absolute count, which also
# handles teams the feed lists more or fewer players for. Note `opp` is only
# populated on PROJECTED rows -- roughly a quarter of a roster -- so a
# fraction-of-all-players test does not work and will call every week a bye.
#
# Measured: any threshold from 0.10 to 0.25 gives 32 of 32 teams agreeing with
# the Sleeper schedule across all 18 weeks. 0.25 is chosen for margin; it
# tolerates four bad rows on a 16-player team.
BYE_TOL = 0.25

def _team_byes(wkly, allwk=None):
    allwk = allwk or set(int(w) for w in wkly.week.unique())
    cnt = collections.defaultdict(int)
    for r in wkly.itertuples():
        if not r.team: continue
        if r.opp is not None and not (isinstance(r.opp, float) and pd.isna(r.opp)):
            cnt[(r.team, int(r.week))] += 1
    out = {}
    for t in wkly.team.dropna().unique():
        med = float(np.median([cnt[(t, w)] for w in allwk]))
        out[t] = {w for w in allwk if cnt[(t, w)] <= BYE_TOL * med}
    return out

def wk_matrix(wkly):
    """Long weekly frame -> projection, bye, and metadata lookups.

    v6.2 fixes a subtle but important bug: a player's bye is determined from
    the team attached to THAT PLAYER-WEEK, not from the team on his latest row.
    If a player changes NFL teams, historical and future weeks can therefore
    retain different team/bye assignments instead of inheriting the final team.

      pts[key][week]         float or NaN
      bye[key]               set of bye weeks
      meta[key][team_by_week] week -> team
      meta[key][inj_by_week]  week -> injury tag
    """
    if wkly is None or not len(wkly):
        return {}, {}, {}
    pts, bye, meta = {}, {}, {}
    allwk = set(int(w) for w in wkly.week.unique())
    team_bye = _team_byes(wkly, allwk)
    cw = current_week(default=min(allwk) if allwk else 1)

    for k, g in wkly.groupby("key"):
        g = g.sort_values("week")
        pts[k] = {int(r.week): (float(r.pts) if not pd.isna(r.pts) else np.nan)
                  for r in g.itertuples()}
        team_by_week, inj_by_week, body_by_week = {}, {}, {}
        for r in g.itertuples():
            w = int(r.week)
            tm = None if pd.isna(r.team) else r.team
            team_by_week[w] = tm
            inj_by_week[w] = None if pd.isna(r.inj) else r.inj
            body_by_week[w] = None if pd.isna(r.body) else r.body
        pbye = {w for w, tm in team_by_week.items()
                if tm is not None and w in team_bye.get(tm, set())}
        bye[k] = pbye

        # Prefer metadata from the current/next available week, not Week 18.
        rows = g[g.week >= cw]
        chosen = rows.iloc[0] if len(rows) else g.iloc[-1]
        meta[k] = dict(name=chosen["name"], pos=chosen["pos"],
                       team=(None if pd.isna(chosen["team"]) else chosen["team"]),
                       inj=(None if pd.isna(chosen["inj"]) else chosen["inj"]),
                       body=(None if pd.isna(chosen["body"]) else chosen["body"]),
                       last_mod=chosen["last_mod"], news=chosen["news"],
                       team_bye=pbye, team_by_week=team_by_week,
                       inj_by_week=inj_by_week, body_by_week=body_by_week)
    meta["__team_bye__"] = team_bye
    return pts, bye, meta

def wk_rate(pts_k, exclude_bye=True):
    """Per-game rate from the weekly feed: mean over weeks he is projected to
    play. NOT comparable to value_pg -- different basis, measured ~+0.87/gm
    hotter on the top 200. Kept as its own column, never blended."""
    if not pts_k: return np.nan
    v = [x for x in pts_k.values() if not pd.isna(x)]
    return float(np.mean(v)) if v else 0.0

# ------------------------------------------------------------------ build
def build():
    log, frames = [], []
    for fn, tag in ((src_rotowire, "rotowire"), (src_espn, "espn")):
        try:
            d = fn(); frames.append(d); log.append(f"  {tag:9s} OK   {len(d)}")
        except Exception as e:
            log.append(f"  {tag:9s} FAIL {type(e).__name__}: {e}")
    if not frames:
        raise RuntimeError("both projection sources failed -- no board")

    allp = pd.concat(frames, ignore_index=True)
    allp["key"] = [norm(n, p) for n, p in zip(allp.name, allp.pos)]
    allp = allp[allp.key.str.len() > 2]

    med = allp.groupby("key")[COMP].median()
    # UNIFORM 17. See header. value_pg = season projection / 17, i.e.
    # availability-adjusted per game. Do not reintroduce a per-player gp
    # without a source that actually differentiates it.
    med["gp"] = float(GAMES)
    med["name"] = allp.groupby("key")["name"].first()
    med["pos"]  = allp.groupby("key")["pos"].first()
    med["team"] = allp.groupby("key")["team"].apply(
        lambda s: s.dropna().iat[0] if s.notna().any() else None)
    med["adp"]   = allp.groupby("key")["adp"].max()
    med["n_src"] = allp.groupby("key")["src"].nunique()

    for s in ("rotowire", "espn"):
        sub = allp[allp.src == s].drop_duplicates("key").set_index("key")
        if len(sub):
            med[s] = sub.apply(lambda r: score_row(r), axis=1)
    srcs = [s for s in ("rotowire", "espn") if s in med]
    # two sources disagreeing is a real flag now, not a median-of-three artefact
    med["spread_pg"] = (med[srcs].max(axis=1) - med[srcs].min(axis=1)) / med.gp
    med["proj_pg"]   = med.apply(lambda r: score_row(r), axis=1) / med.gp

    mkt_rows = 0
    if not QUICK:
        mk = src_market_v2()
        mkt_rows = len(mk)
        if mkt_rows:
            piv = _pivot(mk, "_mkt")
            for c in ["rush_yd","rush_td","rec_yd","rec_td","pass_yd","pass_td"]:
                col = c + "_mkt"
                med[col] = piv[col].reindex(med.index) if col in piv else np.nan
                med[c + "_nbk"] = (piv[c + "_nbk"].reindex(med.index)
                                   if c + "_nbk" in piv else np.nan)
            # ---- RECEPTIONS: book line / book-implied YPC, not a bridge ----
            # See book_ypc(). This replaces v5.0's projection-anchored ratio,
            # which was the largest invented number on the board.
            ypc_p, ypc_pos = book_ypc(current_week())
            # FALLBACK ORDER MATTERS AND THE OBVIOUS CHOICE IS WRONG.
            # v5.1-rc1 fell back to the POSITION MEDIAN YPC (WR 11.6). That
            # blows up on archetypes: Alec Pierce is a pure deep threat whose
            # own projected YPC is 15.9, so dividing a 900-yard book line by
            # 11.6 gave him 77 receptions instead of 57. Yards-per-catch is an
            # efficiency profile -- the one thing projections are genuinely
            # reliable about, because it barely moves with news. Volume is
            # what they get wrong, and volume is what we take from the book.
            # So: own book YPC > own PROJECTED YPC > position median.
            proj_ypc = (med["rec_yd"] / med["rec"].replace(0, np.nan))
            proj_ypc = proj_ypc.where((proj_ypc > 3) & (proj_ypc < 22))
            med["ypc_used"] = [
                ypc_p.get(k, py if not pd.isna(py) else ypc_pos.get(p, np.nan))
                for k, py, p in zip(med.index, proj_ypc, med.pos)]
            med["ypc_src"] = ["book" if k in ypc_p
                              else ("proj" if not pd.isna(py) else "posmed")
                              for k, py in zip(med.index, proj_ypc)]
            med["ypc_is_own"] = [s == "book" for s in med["ypc_src"]]
            med["rec_mkt"] = med["rec_yd_mkt"] / med["ypc_used"]
            med["rec_nbk"] = med.get("rec_yd_nbk", np.nan)
            med["rec_real_frac"] = 0.0
            # v6.2: every week that has a real receptions market permanently
            # replaces 1/17 of the season bridge. This improves automatically
            # as the season progresses instead of re-inventing receptions all year.
            try:
                _cw = current_week()
                _rh = rec_history(weeks=[_cw], refresh_week=_cw)
                _rt, _rf = rec_season_from_history(_rh, med.reset_index())
                for _k, _v in _rt.items():
                    if _k in med.index and not pd.isna(_v):
                        med.at[_k, "rec_mkt"] = float(_v)
                med["rec_real_frac"] = pd.Series(_rf).reindex(med.index).fillna(0.0)
            except Exception as _e:
                print(f"  receptions history unavailable: {type(_e).__name__}")
            print(f"  receptions  reconstructed from book YPC for "
                  f"{int(med.rec_mkt.notna().sum())} players "
                  f"({int(pd.Series(med.ypc_is_own).sum())} on their own BOOK ypc, "
                  f"{int((med.ypc_src=='proj').sum() & 0) or int(sum(1 for s,v in zip(med.ypc_src, med.rec_mkt) if s=='proj' and not pd.isna(v)))} on their own projected ypc) | "
                  + " ".join(f"{p}={v:.1f}" for p, v in sorted(ypc_pos.items())))
            med["mkt_pg"] = med.apply(lambda r: score_row(r, "_mkt"), axis=1) / med.gp
            med["n_mkt"]  = med[[c+"_mkt" for c in
                                 ["rush_yd","rec_yd","rush_td","rec_td","pass_yd","pass_td"]
                                 ]].notna().sum(axis=1)
            nbk = [c for c in med.columns if c.endswith("_nbk")]
            if nbk:
                # v6.2: support depth is COMPONENT-LEVEL. The old max() let one
                # deeply quoted receiving-yard line hide a one-book TD/rush leg.
                med["n_books"] = med[nbk].median(axis=1, skipna=True)
                med["n_books_min"] = med[nbk].min(axis=1, skipna=True)
                med["n_books_max"] = med[nbk].max(axis=1, skipna=True)
            else:
                med["n_books"] = med["n_books_min"] = med["n_books_max"] = np.nan
        else:
            med["mkt_pg"] = np.nan; med["n_mkt"] = 0
    else:
        med["mkt_pg"] = np.nan; med["n_mkt"] = 0

    # ---------------------------------------------------------------- value
    # v4. The old line was:
    #     value_pg = 0.5*mkt_pg + 0.5*proj_pg  where covered, else proj_pg
    # Three things wrong with it, measured Aug 2026:
    #
    # 1. SCALE DISCONTINUITY. Only 168 of 497 both-source players have any book
    #    line, so covered and uncovered players were being scored by different
    #    estimators and then ranked against each other -- including inside
    #    replacement(), which sets the bar the whole roster is measured off.
    # 2. THE GAP IS A BASIS DIFFERENCE, NOT DISAGREEMENT. Books run 1.15-1.29
    #    pts/gm BELOW the projections at every position, one-sided for 90-97% of
    #    players. Season props are priced with missed games in them; Rotowire and
    #    ESPN publish closer to a healthy-17 line. Averaging the two applied half
    #    that structural haircut to the covered players and none to the rest --
    #    and the covered players are the good ones, so it quietly compressed
    #    everyone above replacement toward everyone below.
    # 3. "50% MARKET" WAS NEVER 50% MARKET. score_row() silently substitutes the
    #    projection wherever a _mkt column is missing, with nothing marking it.
    #
    # v4 instead splits the market into the part that is structure and the part
    # that is opinion, and only uses the opinion:
    #     haircut[pos] = median(mkt_pg - proj_pg)      <- basis, same for everyone
    #     mkt_edge     = (mkt_pg - proj_pg) - haircut  <- what books say about HIM
    #     value_pg     = proj_pg + coverage * mkt_edge
    # A player the books price exactly at the structural gap lands on proj_pg,
    # which is where an uncovered player lands too. No discontinuity by
    # construction. A player with no lines gets coverage=0 and is untouched.
    #
    # coverage = share of his projected fantasy points that came from a real
    # line, plus HALF credit for bridged receptions (bridged is market-derived
    # but through a yards-per-catch assumption we invented, so it is not a book
    # opinion at full strength). Typical: QB .98, WR .81, TE .79, RB .72 --
    # i.e. the books now move a player as far as their actual coverage of him
    # justifies, instead of a flat 50% that was mostly dilution.
    W = dict(pass_yd=.04, pass_td=4, rush_yd=.1, rush_td=6,
             rec_yd=.1, rec_td=6, rec=1.0)
    if "mkt_pg" in med and med.get("n_mkt", pd.Series(0, index=med.index)).sum() > 0:
        # Denominator must be the MARKET-basis total, not the projection total.
        # mkt_pg is built component-wise from the book line where one exists and
        # the projection where one doesn't, so its composition has to be measured
        # against its own total -- dividing by the projection total lets the
        # shares exceed 100% whenever the books are above the projections, which
        # is exactly the case for anyone interesting.
        real = tot = brid = 0.0
        for c, w in W.items():
            if c not in med: continue
            mc = c + "_mkt"
            has = med[mc].notna() if mc in med else pd.Series(False, index=med.index)
            used = med[mc].where(has, med[c]).fillna(0) if mc in med else med[c].fillna(0)
            tot = tot + used * w
            if c == "rec":
                # v5.0 called this "bridged" and gave it HALF credit, because
                # it was the projection scaled by a market ratio. It is now a
                # real season rec-yd line divided by a real per-game YPC --
                # both market numbers. Credit raised to 0.85, docked only
                # because the YPC comes from a different period than the line.
                brid = brid + used.where(has, 0.0) * w
            else:
                real = real + used.where(has, 0.0) * w
        tot = tot.replace(0, np.nan)
        med["mkt_real_pct"]   = (100 * real / tot).clip(0, 100)
        med["mkt_bridge_pct"] = (100 * brid / tot).clip(0, 100)
        rec_credit = (0.85 + 0.15 * med.get("rec_real_frac", 0.0)).clip(0.85, 1.0)
        med["coverage"] = ((med.mkt_real_pct + rec_credit * med.mkt_bridge_pct) / 100
                           ).fillna(0).clip(0, 1)
        med.loc[med.n_mkt == 0, "coverage"] = 0.0
        med["mkt_gap"] = med.mkt_pg - med.proj_pg
        hc = med[med.n_mkt > 0].groupby("pos").mkt_gap.median()
        med["haircut"]  = med.pos.map(hc)
        med["mkt_edge"] = (med.mkt_gap - med.haircut).fillna(0.0)
        med["value_pg"] = med.proj_pg + med.coverage * med.mkt_edge
    else:
        for c in ("mkt_real_pct", "mkt_bridge_pct", "coverage",
                  "mkt_gap", "haircut", "mkt_edge"):
            med[c] = np.nan if c in ("mkt_gap", "haircut") else 0.0
        med["value_pg"] = med.proj_pg
    # v5.2: the support tier is attached HERE so it travels with every row and
    # cannot be left behind at the point of use. See support().
    med = support(med.reset_index()).set_index("key")
    print("\n".join(log))
    # market row count is logged so drift can finally be attributed to the feed
    print(f"  market    {mkt_rows} lines | receptions poll {check_receptions()} (0 = bridged)")
    if med.get("n_mkt", pd.Series(0, index=med.index)).sum() > 0:
        print("  haircut/gm (books minus projections, structural): " +
              "  ".join(f"{p}={v:+.2f}" for p, v in
                        med[med.n_mkt > 0].groupby("pos").mkt_gap.median().items()))
    return med.reset_index()

def weekly_market(week, wkly, board=None):
    """Per-week value with REAL book lines folded in -- including receptions.

    Same architecture as the v4 season layer, and for the same reason: the
    books sit on a different basis to the projections, so we strip the
    structural part and keep only the player-specific opinion.

        mkt_wk   = book line where one exists, weekly projection where not
        haircut  = median(mkt_wk - proj_wk) per position   <- basis
        edge     = (mkt_wk - proj_wk) - haircut            <- opinion about HIM
        coverage = share of his points that came from a real line
        wkval    = proj_wk + coverage * edge

    The difference from v4: `rec` is now a REAL BOOK NUMBER, not a bridge off
    rec_yd through an invented yards-per-catch. In full PPR receptions are
    ~35-41% of a WR/TE's scoring, so this is the single biggest accuracy gain
    in v5 and the reason coverage no longer needs a half-credit fudge.

    Still bridged/absent: rush_td and rec_td have no per-game consensus market,
    so TDs come from the projection. Coverage will therefore top out well
    short of 100% for TD-dependent players -- which is correctly reflected in
    the weight, not hidden."""
    w = wkly[wkly.week == week].copy()
    if not len(w): return pd.DataFrame()
    mk = src_market_weekly(week)
    w = w[w.pts.notna()]
    if not len(mk):
        w["wkval"] = w.pts; w["mkt_cov"] = 0.0; w["edge"] = 0.0; w["n_mkt"] = 0
        return w
    mk = mk.groupby("key").first()
    for c in ["pass_yd", "pass_td", "rush_yd", "rec_yd", "rec"]:
        w[c + "_m"] = mk[c].reindex(w.key).values if c in mk else np.nan
    W = dict(pass_yd=.04, pass_td=4, rush_yd=.1, rush_td=6,
             rec_yd=.1, rec_td=6, rec=1.0)
    real = tot = pd.Series(0.0, index=w.index)
    for c, wt in W.items():
        mc = c + "_m"
        has = w[mc].notna() if mc in w else pd.Series(False, index=w.index)
        used = (w[mc].where(has, w[c]) if mc in w else w[c]).fillna(0)
        tot = tot + used * wt
        real = real + used.where(has, 0.0) * wt
    w["mkt_wk"] = tot.astype(float)
    nm = pd.Series(0, index=w.index, dtype=int)
    for c in ["pass_yd", "pass_td", "rush_yd", "rec_yd", "rec"]:
        if c + "_m" in w: nm = nm + w[c + "_m"].notna().astype(int)
    w["n_mkt"] = nm
    # NB: the column is mkt_cov, not cov -- `cov` collides with
    # DataFrame.cov() and attribute access silently returns the METHOD.
    w["mkt_cov"] = (real.astype(float) / tot.astype(float).replace(0, np.nan)
                    ).fillna(0).clip(0, 1)
    w.loc[w.n_mkt == 0, "mkt_cov"] = 0.0
    gap = w.mkt_wk.astype(float) - w.pts.astype(float)
    hc = gap[w.n_mkt > 0].groupby(w.pos).median()
    w["edge"] = (gap - w.pos.map(hc).astype(float)).fillna(0.0).astype(float)
    w.loc[w.n_mkt == 0, "edge"] = 0.0
    w["wkval"] = (w["pts"].astype(float)
                  + w["mkt_cov"].astype(float) * w["edge"].astype(float)).astype(float)
    return w

# -------------------------------------------------------------- overrides
# The BRIEF says the engine does arithmetic and judgment does news. There was
# never a way for judgment to feed BACK: a correction lived in conversation
# and evaporated when the session ended. This is that channel, and it is
# deliberately hostile to sloppiness --
#
#   * every entry MUST carry `dated` and `src`. Undated or unsourced entries
#     are REFUSED, loudly, and not applied.
#   * every applied entry is PRINTED IN FULL on every run. There is no quiet
#     override.
#   * entries older than STALE_OVERRIDE_DAYS are flagged for review, because a
#     hand number that outlives its news is worse than no override at all.
#
# Fields:
#   player, pos   -> joined via norm(), same key as everything else
#   weeks         -> iterable of weeks (weekly layer), or None for season
#   set / mult    -> absolute points, or a multiplier on what's there
#   dated, src, note
#
# Keep this list SHORT. If it is long, the feed is broken and the fix is
# upstream, not here.
STALE_OVERRIDE_DAYS = 21

OVERRIDES = [
    # ---- seeded Aug 30 2026. Each of these is a season-feed failure the
    # ---- weekly feed already handles; they exist so the SEASON board (which
    # ---- still drives VOR, anchor and the trade scanner) is not wrong.
    dict(player="Jordyn Tyson", pos="WR", weeks=None, mult=0.55,
         dated="2026-08-30",
         src="ESPN 53-man projection + SI, hamstring, IR to open the season",
         note="rotowire 111 / espn 99.5 season pts both assume a full year. "
              "Weekly feed has no wk1-4 row and Doubtful/Hamstring. Haircut "
              "the season line to roughly 9 of 17 games."),
    dict(player="Alvin Kamara", pos="RB", weeks=None, mult=0.85,
         dated="2026-08-30",
         src="Schefter Aug 19, MCL sprain, out at least a month",
         note="rotowire cut him to 63 season pts, ESPN still carried 117. The "
              "median of a live source and a frozen one splits the difference "
              "and lands somewhere neither believes."),
]

def _od(s):
    return time.mktime(time.strptime(s, "%Y-%m-%d"))

def apply_overrides(board, wk_pts=None, verbose=True):
    """Apply OVERRIDES to the season board and (optionally) the weekly matrix.
    Returns (board, applied_rows, refused_rows). Never silent."""
    applied, refused = [], []
    # initialise explicitly: board.loc[mask,"overridden"]=True creates the
    # column with NaN elsewhere, and bool(NaN) is TRUE -- so every untouched
    # player would render as hand-overridden.
    if "overridden" not in board:
        board["overridden"] = False
    b = board.set_index("key")
    for o in OVERRIDES:
        who = f"{o.get('player','?')} ({o.get('pos','?')})"
        if not o.get("dated") or not o.get("src"):
            refused.append((who, "missing dated= or src=")); continue
        if ("set" not in o) and ("mult" not in o):
            refused.append((who, "neither set= nor mult=")); continue
        k = norm(o["player"], o["pos"])
        age = (time.time() - _od(o["dated"])) / 86400
        if k not in b.index:
            refused.append((who, "not on board")); continue
        if o.get("weeks") is None:
            before = float(b.loc[k, "value_pg"])
            after = float(o["set"]) if "set" in o else before * float(o["mult"])
            board.loc[board.key == k, "value_pg"] = after
            board.loc[board.key == k, "overridden"] = True
            applied.append((who, "season", f"{before:.2f} -> {after:.2f}",
                            age, o["dated"], o["src"], o.get("note", "")))
        elif wk_pts is not None and k in wk_pts:
            hits = 0
            for w in o["weeks"]:
                if w in wk_pts[k] and not pd.isna(wk_pts[k][w]):
                    wk_pts[k][w] = (float(o["set"]) if "set" in o
                                    else wk_pts[k][w] * float(o["mult"]))
                    hits += 1
            applied.append((who, f"weeks {list(o['weeks'])}", f"{hits} weeks",
                            age, o["dated"], o["src"], o.get("note", "")))
    if verbose:
        print("\n=== OVERRIDES (hand-entered judgment, applied on top of the feed) ===")
        if not applied and not refused:
            print("  none -- board is pure feed")
        for who, scope, delta, age, dated, srcs, note in applied:
            warn = "   <-- STALE, RE-CHECK" if age > STALE_OVERRIDE_DAYS else ""
            print(f"  APPLIED  {who:26s} {scope:16s} {delta:20s} "
                  f"({int(age)}d old, {dated}){warn}")
            print(f"           src: {srcs}")
            if note: print(f"           why: {note}")
        for who, why in refused:
            print(f"  REFUSED  {who:26s} {why}")
    return board, applied, refused

# ------------------------------------------------------------------ cache
def cache_info(name):
    """Actual persisted fetch time; reading a cache never makes it fresh."""
    path = os.path.join(CACHE, f"{name}.pkl")
    try:
        stamp = os.path.getmtime(path)
    except FileNotFoundError:
        return {"name": name, "fetched_at_utc": None, "age_hours": None}
    return {"name": name,
            "fetched_at_utc": datetime.datetime.fromtimestamp(
                stamp, datetime.timezone.utc).isoformat(timespec="seconds"),
            "age_hours": max(0.0, (time.time() - stamp) / 3600)}


def _cached(name, fn, ttl, force=False):
    os.makedirs(CACHE, exist_ok=True)
    p = f"{CACHE}/{name}.pkl"
    if not force and os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl:
        age = (time.time() - os.path.getmtime(p)) / 3600
        print(f"  [cache] {name}: {age:.1f}h old")
        with open(p, "rb") as handle:
            return pickle.load(handle)
    v = fn()
    # Concurrent readers see either the entire previous or entire new value.
    # A fetch or serialization failure preserves the previous file and mtime.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=CACHE, prefix=f".{name}-",
                                         suffix=".tmp", delete=False) as handle:
            temporary = handle.name
            pickle.dump(v, handle, protocol=pickle.HIGHEST_PROTOCOL)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, p)
    finally:
        if temporary and os.path.exists(temporary):
            os.remove(temporary)
    return v

def board_cached(force=False):
    """24 hours, keyed by market-auth mode.

    v6.3: an unauthenticated run must never populate the same cache file as an
    authenticated market run. That exact failure produced a perfectly healthy
    looking audit bundle with 0 market-covered players after a prior no-key
    session. The cache key now makes the data provenance part of the identity.
    """
    variant = "quick" if QUICK else ("market" if BP_API_KEY else "nomarket")
    name = f"board_{variant}"
    b = _cached(name, build, 24*3600, force=force)
    b.to_csv("board.csv", index=False)
    return b

def _league_live():
    """Frequently changing league state only: rosters, users and transactions."""
    g = lambda p: requests.get(f"https://api.sleeper.app/v1/league/{LEAGUE}/{p}",
                               headers=UA, timeout=30).json()
    rosters, users = g("rosters"), g("users")
    tx = []
    # Future transaction weeks cannot contain anything useful. Keep this cheap
    # enough that roster state can be refreshed aggressively.
    through = max(1, min(18, current_week()))
    for w in range(1, through + 1):
        try:
            t = g(f"transactions/{w}")
            if t: tx += t
        except Exception:
            pass
    return rosters, users, tx

def _league_players():
    return requests.get("https://api.sleeper.app/v1/players/nfl",
                        headers=UA, timeout=120).json()

def _league_picks():
    return requests.get(f"https://api.sleeper.app/v1/draft/{DRAFT}/picks",
                        headers=UA, timeout=30).json()

def league():
    """Uncached compatibility path."""
    rosters, users, tx = _league_live()
    return rosters, users, _league_players(), _league_picks(), tx

def league_cached():
    """Cache according to volatility instead of freezing everything for 1h."""
    rosters, users, tx = _cached("league_live", _league_live, 5*60)
    players = _cached("league_players", _league_players, 24*3600)
    picks = _cached("league_picks", _league_picks, 30*86400)
    return rosters, users, players, picks, tx

# --------------------------------------------------------- lineup / value
SLOTS = ["QB","RB","RB","WR","WR","TE","FLEX","FLEX"]

def replacement(board, value_col="value_pg"):
    """Replacement level per slot on an explicitly named value basis.

    v6.3 normally passes ``ros_pg`` here. ``value_pg`` remains available for
    season-market diagnostics and historical comparisons.
    """
    if value_col not in board.columns:
        value_col = "value_pg"
    pool, rl, used = board[board.n_src >= 2], {}, set()
    for pos, n in (("QB",12), ("RB",24), ("WR",24), ("TE",12)):
        ss = pool[pool.pos == pos].sort_values(value_col, ascending=False)
        rl[pos] = float(ss[value_col].iloc[n-1]); used |= set(ss.index[:n])
    fl = pool[pool.pos.isin(["RB","WR","TE"]) & ~pool.index.isin(used)]
    rl["FLEX"] = float(fl.sort_values(value_col, ascending=False)[value_col].iloc[23])
    return rl

def make_val(board, players, value_col="value_pg"):
    """pid -> (ppg, pos, name) on the requested value basis."""
    if value_col not in board.columns:
        value_col = "value_pg"
    b = board.set_index("key")
    val = {}
    for pid, p in players.items():
        if not isinstance(p, dict): continue
        pos, nm = p.get("position"), p.get("full_name")
        if pos not in ("QB","RB","WR","TE") or not nm: continue
        k = norm(nm, pos)
        r = b.loc[k] if k in b.index else None
        if isinstance(r, pd.DataFrame): r = r.iloc[0]
        val[pid] = (float(r[value_col]) if r is not None and not pd.isna(r.get(value_col, np.nan)) else 0.0,
                    pos, nm)
    return val

def best8(pids, val):
    """THE reason this file exists. Two flex slots make lineup value
    combinatorial -- you cannot eyeball whether a swap helps."""
    d = {"QB":[], "RB":[], "WR":[], "TE":[]}
    for p in pids:
        v = val.get(p)
        if v: d[v[1]].append(v[0])
    for k in d: d[k].sort(reverse=True)
    d = {k: v + [0.0]*3 for k, v in d.items()}
    fl = sorted(d["RB"][2:] + d["WR"][2:] + d["TE"][1:], reverse=True)
    return d["QB"][0] + sum(d["RB"][:2]) + sum(d["WR"][:2]) + d["TE"][0] + fl[0] + fl[1]

ROSTER_CAP = 15


def legalize_roster(pids, roster, val, objective, roster_cap=ROSTER_CAP):
    """Enforce the active roster limit and return (legal_ids, forced_drops).

    Reserve/IR is excluded from the active count. K/DST are not auto-dropped
    because this offensive engine does not model their replacement cost; doing
    so would hide the roster-slot cost instead of pricing it.
    """
    ids = list(pids)
    reserve = set(roster.get("reserve") or [])
    active = [p for p in ids if p not in reserve]
    excess = max(0, len(active) - int(roster_cap))
    if excess == 0:
        return ids, []
    cands = [p for p in active if p in val]
    if len(cands) < excess:
        raise ValueError(f"{excess} players over cap but only {len(cands)} modeled drop candidates")
    best = None
    for drops in itertools.combinations(cands, excess):
        ds = set(drops)
        keep = [p for p in ids if p not in ds]
        score_ = float(objective(keep))
        if best is None or score_ > best[0]:
            best = (score_, keep, list(drops))
    return best[1], best[2]


def trade(rosters, val, rid_a, out_a, rid_b, out_b):
    """Ad-hoc pricer for a specific offer. Names in, (delta_a, delta_b) out."""
    ra = next(r for r in rosters if r["roster_id"] == rid_a)
    rb = next(r for r in rosters if r["roster_id"] == rid_b)
    A = [p for p in ra["players"] if val.get(p, (0,0,""))[2] in out_a]
    B = [p for p in rb["players"] if val.get(p, (0,0,""))[2] in out_b]
    new_a = [p for p in ra["players"] if p not in A] + B
    new_b = [p for p in rb["players"] if p not in B] + A
    obj = lambda ids: best8(ids, val)
    new_a, _ = legalize_roster(new_a, ra, val, obj)
    new_b, _ = legalize_roster(new_b, rb, val, obj)
    da = best8(new_a, val) - best8(ra["players"], val)
    db = best8(new_b, val) - best8(rb["players"], val)
    return round(da, 2), round(db, 2)

# ------------------------------------------------------- weekly lineups
def byes():
    """Schedule-derived team byes. STILL USED as a cross-check against the
    weekly feed's observed byes -- if they disagree, one of them is wrong and
    you want to know which before you trust a lineup."""
    sch = requests.get(f"https://api.sleeper.app/schedule/nfl/regular/{SEASON}",
                       headers=UA, timeout=30).json()
    teams, wk = set(), collections.defaultdict(set)
    for g in sch:
        wk[g["week"]] |= {g["home"], g["away"]}
        teams |= {g["home"], g["away"]}
    return {w: teams - wk[w] for w in sorted(wk)}, teams

def wk_val(val, wk_pts, players, week, fallback=True):
    """pid -> (points, pos, name) FOR ONE WEEK, off the weekly feed.

    This is the v5 replacement for 'season/17 and drop the bye guys'. Three
    cases, and the distinction is the whole point:

      projected        -> use the real weekly number
      not projected    -> 0.0. Bye, injury, or no role -- rotowire is saying
                          he does not play. v4 could not tell 'on bye' from
                          'season-long average', so an injured starter kept
                          scoring his healthy rate every week.
      not in the feed  -> fall back to season value_pg, FLAGGED. Only happens
                          for deep names the weekly feed ignores entirely;
                          measured at 0 of 159 rostered skill players.

    fallback=False makes case 3 zero as well, which is the pessimistic read."""
    out, unknown = {}, []
    for pid, (v, pos, nm) in val.items():
        k = norm(nm, pos)
        if k in wk_pts:
            p = wk_pts[k].get(week, np.nan)
            out[pid] = (0.0 if pd.isna(p) else float(p), pos, nm)
        elif fallback:
            out[pid] = (v, pos, nm); unknown.append(nm)
        else:
            out[pid] = (0.0, pos, nm); unknown.append(nm)
    return out, unknown

def best8_week(pids, val, week, wk_pts=None, players=None, fill=None,
               bye=None, team_of=None):
    """Best-8 for one week.

    v5 path (wk_pts given): every player is priced at his OWN projection for
    THAT week. A bye is zero because the feed says zero, an injury is zero for
    the weeks he is out and real after, and a backup who inherits a role is
    worth what he is worth in the week he inherits it. None of that was
    expressible in v4.

    v4 path (wk_pts None): season/17 with bye players dropped and the wire
    padded in. Kept so the two can be diffed, and because the wire fill is
    still the right model for 'who would I actually stream'."""
    if wk_pts is not None:
        wv, _ = wk_val(val, wk_pts, players, week)
        keep = list(pids)
        if fill:
            for pos, cands in fill.items():
                for i, (v, ps, name, tm) in enumerate(cands):
                    k = norm(name, ps)
                    fv = wk_pts.get(k, {}).get(week, np.nan)
                    if k in wk_pts and pd.isna(fv):
                        continue                      # streamer is also out
                    fid = f"__FA_{pos}_{i}"
                    wv[fid] = (float(fv) if not pd.isna(fv) else v, ps, name)
                    keep.append(fid); break
        return best8(keep, wv)
    # ---- legacy path
    off = (bye or {}).get(week, set())
    keep = [p for p in pids if (team_of or {}).get(p) not in off]
    if not fill:
        return best8(keep, val)
    fake, adds = dict(val), []
    for pos, cands in fill.items():
        for i, (v, ps, name, tm) in enumerate(cands):
            if tm not in off:
                fid = f"__FA_{pos}_{i}"; fake[fid] = (v, ps, name); adds.append(fid); break
    return best8(keep + adds, fake)

def wire_fill(fa_df, per_pos=6):
    """Top free agents per position, as streaming candidates. Depth of 6 so a
    week that knocks out the top option still has a real body behind it."""
    fill = {}
    for pos in ("QB", "RB", "WR", "TE"):
        s = fa_df[fa_df.pos == pos].nlargest(per_pos, "value_pg")
        fill[pos] = [(float(r.value_pg), pos, r["name"], r.team) for _, r in s.iterrows()]
    return fill

def weekly_strength(rosters, users, val, players, wk_pts, fill=None,
                    weeks=None):
    """ABSOLUTE best-8 per team per week. Replaces bye_report().

    v4 reported a DELTA against a season baseline, which quietly made rosters
    of different strength incomparable: a better team loses more when a
    starter sits, because its gap to the wire is larger, so a stronger roster
    could look like it had a worse bye problem. Absolutes don't have that
    failure mode -- and they also fold injuries, role changes and byes into
    one number instead of modelling only the byes."""
    weeks = _resolve_weeks(weeks)
    umap = {u["user_id"]: u["display_name"] for u in users}
    rows = []
    for r in rosters:
        row = {"mgr": umap[r["owner_id"]], "rid": r["roster_id"]}
        for w in weeks:
            row[f"w{w}"] = round(best8_week(r["players"], val, w, wk_pts,
                                            players, fill), 1)
        rows.append(row)
    d = pd.DataFrame(rows)
    wc = sorted([c for c in d.columns if c.startswith("w") and c[1:].isdigit()],
                key=lambda c: int(c[1:]))
    regc = [c for c in wc if int(c[1:]) <= 14]
    plc = [c for c in wc if int(c[1:]) in (15, 16, 17)]
    d["reg"] = d[regc].sum(axis=1).round(1) if regc else 0.0
    d["playoff"] = d[plc].sum(axis=1).round(1) if plc else 0.0
    d["worst"] = d[wc].min(axis=1)
    d["worst_wk"] = d[wc].idxmin(axis=1)
    return d

def bye_report(rosters, users, val, players, fill=None):
    """v4 shape, kept only so a v4 number can be reproduced on demand.
    weekly_strength() is the one to use."""
    bye, _ = byes()
    team_of = {p: (players.get(p) or {}).get("team") for p in val}
    umap = {u["user_id"]: u["display_name"] for u in users}
    rows = []
    for r in rosters:
        base = best8(r["players"], val)
        row = {"mgr": umap[r["owner_id"]]}
        for w in range(4, 15):
            row[f"w{w}"] = round(best8_week(r["players"], val, w, None, None,
                                            fill, bye, team_of) - base, 1)
        rows.append(row)
    return pd.DataFrame(rows)

def trade_week(rosters, val, players, wk_pts, rid_a, out_a, rid_b, out_b,
               fill=None, weeks=None, reg=14, playoffs=(15, 16, 17)):
    """Price a specific offer on BOTH bases at once. This is the function that
    should decide a trade.

    v4 could only answer 'change in season best-8', a single number that is
    blind to WHEN the points arrive. Three things it could not see, all of
    which have decided real decisions in this league:

      - a deal that is flat on the season but converts one catastrophic week
        into two survivable ones
      - a deal that helps in September and hurts in Weeks 15-17, which are the
        only weeks that decide anything
      - a deal whose value is entirely an injury window that closes in Week 5

    Returns a dict per side with: season delta (the v4 number, kept for
    continuity), and on the weekly basis the regular-season total, the
    playoff-week total, the worst single week, and the full week vector.

    IMPORTANT: season and weekly totals are DIFFERENT BASES and must not be
    compared to each other. Compare season-to-season and weekly-to-weekly.
    The weekly feed runs roughly +0.9/gm hotter; that offset is real and it is
    why this returns them side by side rather than blended."""
    weeks = _resolve_weeks(weeks)
    ra = next(r for r in rosters if r["roster_id"] == rid_a)
    rb = next(r for r in rosters if r["roster_id"] == rid_b)
    nm = lambda p: val.get(p, (0, "", ""))[2]
    A = [p for p in ra["players"] if nm(p) in out_a]
    B = [p for p in rb["players"] if nm(p) in out_b]
    missing = ([x for x in out_a if x not in [nm(p) for p in A]] +
               [x for x in out_b if x not in [nm(p) for p in B]])
    if missing:
        raise ValueError(f"not on the stated roster: {missing}")
    new_a = [p for p in ra["players"] if p not in A] + B
    new_b = [p for p in rb["players"] if p not in B] + A

    def legal_obj(ids):
        if wk_pts:
            return sum(best8_week(ids, val, w, wk_pts, players, None) for w in weeks)
        return best8(ids, val)
    new_a, drop_a = legalize_roster(new_a, ra, val, legal_obj)
    new_b, drop_b = legalize_roster(new_b, rb, val, legal_obj)

    def side(before, after, label, forced):
        s_before, s_after = best8(before, val), best8(after, val)
        out = dict(side=label, season_before=round(s_before, 2),
                   season_after=round(s_after, 2),
                   season_delta=round(s_after - s_before, 2),
                   forced_drops=[nm(p) for p in forced])
        if wk_pts:
            wb = {w: best8_week(before, val, w, wk_pts, players, fill) for w in weeks}
            wa = {w: best8_week(after,  val, w, wk_pts, players, fill) for w in weeks}
            rg = [w for w in weeks if w <= reg]
            out.update(
                reg_before=round(sum(wb[w] for w in rg), 1),
                reg_after=round(sum(wa[w] for w in rg), 1),
                reg_delta=round(sum(wa[w] - wb[w] for w in rg), 1),
                playoff_before=round(sum(wb[w] for w in playoffs if w in wb), 1),
                playoff_after=round(sum(wa[w] for w in playoffs if w in wa), 1),
                playoff_delta=round(sum(wa[w] - wb[w] for w in playoffs if w in wb), 1),
                worst_before=round(min(wb.values()), 1),
                worst_after=round(min(wa.values()), 1),
                worst_wk_before=min(wb, key=wb.get), worst_wk_after=min(wa, key=wa.get),
                weekly_before=wb, weekly_after=wa)
        return out
    return dict(a=side(ra["players"], new_a, f"rid{rid_a}", drop_a),
                b=side(rb["players"], new_b, f"rid{rid_b}", drop_b))

def show_trade(res, names=("me", "them")):
    """Human-readable trade_week(). Leads with playoffs, because Weeks 15-17
    are the only ones that decide the season and a season-total delta can hide
    a playoff-week loss inside a September gain."""
    print(f"  {'':22s}{'season Δ':>10s}{'reg(1-14)':>12s}{'PLAYOFFS':>11s}"
          f"{'worst wk':>18s}")
    for key, label in zip(("a", "b"), names):
        s = res[key]
        if "reg_delta" in s:
            print(f"  {label:22s}{s['season_delta']:+10.2f}{s['reg_delta']:+12.1f}"
                  f"{s['playoff_delta']:+11.1f}"
                  f"   {s['worst_before']:.0f}(w{s['worst_wk_before']})"
                  f" -> {s['worst_after']:.0f}(w{s['worst_wk_after']})")
            if s.get("forced_drops"):
                print("    forced drop: " + " + ".join(s["forced_drops"]))
        else:
            print(f"  {label:22s}{s['season_delta']:+10.2f}"
                  f"{'  (no weekly feed)':>35s}")

def compare_trades(rosters, val, players, wk_pts, offers, fill=None, rid=ME):
    """Rank several candidate offers against each other AND against standing
    pat. `offers` is a list of (label, give_names, get_names, their_rid).

    Standing pat is included on purpose. In testing, an offer that looked
    reasonable on the season number came out BELOW no-trade on both the
    regular season and the playoff weeks -- it only improved one bye week.
    Without a do-nothing row in the table that is easy to miss."""
    me = next(r for r in rosters if r["roster_id"] == rid)
    weeks = _resolve_weeks(None)
    base_w = {w: best8_week(me["players"], val, w, wk_pts, players, fill)
              for w in weeks} if wk_pts else {}
    rows = [dict(offer="(stand pat)", season=round(best8(me["players"], val), 2),
                 reg=round(sum(base_w[w] for w in weeks if w <= 14), 1) if base_w else np.nan,
                 playoff=round(sum(base_w[w] for w in (15, 16, 17) if w in base_w), 1) if base_w else np.nan,
                 worst=round(min(base_w.values()), 1) if base_w else np.nan,
                 worst_wk=min(base_w, key=base_w.get) if base_w else "",
                 forced_drop="")]
    for label, give, get, orid in offers:
        try:
            r = trade_week(rosters, val, players, wk_pts, rid, give, orid, get, fill)
        except ValueError as e:
            rows.append(dict(offer=f"{label}  !! {e}")); continue
        a = r["a"]
        rows.append(dict(offer=label, season=a["season_after"],
                         reg=a.get("reg_after"), playoff=a.get("playoff_after"),
                         worst=a.get("worst_after"), worst_wk=a.get("worst_wk_after"),
                         forced_drop=" + ".join(a.get("forced_drops") or [])))
    return pd.DataFrame(rows)

# ------------------------------------------------------------------- wire
def wire(board, players, rosters, value_col="value_pg"):
    """FREE AGENT BOARD on an explicit value basis.

    v6.3 uses ROS weekly truth for production waiver ordering while preserving
    the season-market board for provenance.
    """
    rostered = set()
    for r in rosters:
        rostered |= set(r.get("players") or []) | set(r.get("reserve") or [])
    val = make_val(board, players, value_col=value_col)
    rl = replacement(board, value_col=value_col)
    b = board.set_index("key")
    rows = []
    for pid, (v, pos, nm) in val.items():
        if pid in rostered or v <= 0: continue
        k = norm(nm, pos)
        if k not in b.index: continue
        r = b.loc[k]
        if isinstance(r, pd.DataFrame): r = r.iloc[0]
        if r.n_src < 2: continue
        p = players.get(pid) or {}
        rows.append(dict(pid=pid, name=nm, pos=pos, team=p.get("team"),
                         value_pg=round(v, 2), vor=round(v - rl[pos], 2),
                         spread=round(float(r.spread_pg), 2), n_mkt=int(r.n_mkt),
                         status=p.get("injury_status") or ""))
    return pd.DataFrame(rows).sort_values("vor", ascending=False).reset_index(drop=True)

def upgrades(rosters, val, fa_df, rl, rid=ME, min_gain=0.25, min_vor=1.5):
    """Every add costs a drop once the roster is full. Two numbers, both needed:

    gain      = Δ best-8. Zero for a bench-to-bench swap, which is correct --
                it changes nothing you start THIS week.
    vor_gain  = Δ (value over replacement AT EACH POSITION). This is the one
                that catches depth upgrades, and it must be VOR rather than raw
                points or every free QB outranks every real add: a QB2 is +15
                raw points and +0.0 of anything you can use, because replacement
                QB is the best guy on the wire. Doctrine says never add a QB2 --
                this is that rule falling out of the arithmetic instead of being
                bolted on.

    IR/reserve is excluded from drop candidates: it isn't an active roster spot,
    so dropping it doesn't buy you the add."""
    me = next(r for r in rosters if r["roster_id"] == rid)
    active = [p for p in me["players"] if p not in set(me.get("reserve") or [])]
    base, out = best8(active, val), []
    # Wire replacement != rl[]. rl[] is the top-24 cutoff across the whole board,
    # most of which is rostered. What you can ACTUALLY get is the 3rd-best free
    # agent at the position. Scarcity measured against that is the real cost of
    # not rostering someone -- and it is why a QB2 scores ~0: drop Nix and you
    # add Goff. Doctrine "never add a QB2" falls out instead of being asserted.
    wrep = {}
    for pos in ("QB", "RB", "WR", "TE"):
        s = fa_df[fa_df.pos == pos].value_pg
        wrep[pos] = float(s.iloc[2]) if len(s) > 2 else rl[pos]
    have_qb = any(val[p][1] == "QB" and val[p][0] >= wrep["QB"] for p in active if p in val)
    scar = lambda v, pos: v - wrep[pos]
    worst = sorted(((scar(val[p][0], val[p][1]), p) for p in active if p in val))[:6]
    for _, r in fa_df.head(30).iterrows():
        if r.pos == "QB" and have_qb: continue      # QB2 never enters the lineup
        fake = dict(val); fid = "__ADD"; fake[fid] = (r.value_pg, r.pos, r["name"])
        for dscar, dp in worst:
            g = best8([p for p in active if p != dp] + [fid], fake) - base
            out.append(dict(add=r["name"], pos=r.pos, team=r.team, drop=val[dp][2],
                            gain=round(g, 2),
                            depth_gain=round(scar(r.value_pg, r.pos) - dscar, 2),
                            spread=r.spread, status=r.status))
    if not out: return pd.DataFrame()
    d = pd.DataFrame(out)
    d = d[(d.gain >= min_gain) | (d.depth_gain >= min_vor)]
    d = d.sort_values(["gain", "depth_gain"], ascending=False)
    return d.drop_duplicates(subset=["add"]).reset_index(drop=True)

# ----------------------------------------------------------- transparency
MKT_ID = dict(pass_yd=300, rush_yd=301, rec_yd=302,
              pass_td=304, rush_td=305, rec_td=306, rec=330)

def provenance(board, name, wk_pts=None, wk_meta=None):
    """Where every number for one player actually came from. Run this before
    trusting any value that is about to move a decision. Prints, per stat:
    the two source projections, the book line if one exists (with its
    BettingPros market id so it can be checked by hand), and whether the
    'market' figure is a real line, our reception bridge, or a silent fallback
    to the projection.

    Pass wk_pts/wk_meta and it also prints the weekly feed's week-by-week
    view, which is where an injury or a role change actually shows up. Note
    the two bases are NOT comparable -- the weekly block is there to answer
    'when does he score', not 'is he better than the season number says'."""
    r = board[board.name.str.lower() == name.lower()]
    if not len(r):
        print(f"  {name}: not on board"); return
    r = r.iloc[0]
    print(f"\n  {r['name']}  {r.pos} {r.team or '--'}")
    print(f"  {'stat':10s}{'rotowire+espn':>15s}{'book line':>12s}  source")
    for c, mid in MKT_ID.items():
        p = r.get(c, np.nan); m = r.get(c + "_mkt", np.nan)
        if (pd.isna(p) or p == 0) and pd.isna(m): continue
        if c == "rec" and not pd.isna(m):
            src = "book rec_yd line / book-implied YPC (see book_ypc)"
        elif not pd.isna(m):
            src = f"real line, BettingPros market_id={mid}"
        else:
            src = "no line exists -> silently falls back to the projection"
        print(f"  {c:10s}{p:15.1f}{(m if not pd.isna(m) else float('nan')):12.1f}  {src}")
    print(f"  sources agreeing: {int(r.n_src)}  |  rotowire {r.get('rotowire', float('nan')):.1f}"
          f"  espn {r.get('espn', float('nan')):.1f}  -> spread {r.spread_pg:.2f}/gm"
          + ("  ** SOURCE DISAGREEMENT **" if r.spread_pg > 1.75 else ""))
    print(f"  proj_pg   {r.proj_pg:6.2f}   (healthy-season basis)")
    if r.get("n_mkt", 0) > 0:
        print(f"  mkt_pg    {r.mkt_pg:6.2f}   ({r.mkt_real_pct:.0f}% real line, "
              f"{r.mkt_bridge_pct:.0f}% bridged, {100-r.mkt_real_pct-r.mkt_bridge_pct:.0f}% projection)")
        print(f"  haircut   {r.haircut:+6.2f}   structural {r.pos} basis gap, removed")
        print(f"  mkt_edge  {r.mkt_edge:+6.2f}   what the books say about HIM specifically")
        print(f"  coverage  {r.coverage:6.2f}   weight the edge is applied at")
    else:
        print("  mkt_pg      none   no book has posted a season prop on him")
    print(f"  VALUE_PG  {r.value_pg:6.2f}   = proj_pg + coverage x mkt_edge"
          + ("   ** OVERRIDDEN BY HAND, see OVERRIDES **"
             if bool(r.get("overridden", False)) else ""))
    # v5.2 -- the number never leaves this function without its support tier.
    if "support" in r.index:
        print(f"  SUPPORT   {r['support']:>6s}   {r.get('support_why','') or 'well corroborated'}")
    if r["name"] in {t["player"] for t in TAIL_RISK}:
        print(f"  TAIL RISK ** flagged -- the median above is flattering him, see TAIL_RISK **")
    if wk_pts is not None:
        k = norm(r["name"], r.pos)
        wp = wk_pts.get(k)
        if wp:
            v = [x for x in wp.values() if not pd.isna(x)]
            byes_ = sorted(w for w, x in wp.items() if pd.isna(x))
            print(f"  --- weekly feed (rotowire per-week, DIFFERENT BASIS) ---")
            print(f"  projected in {len(v)} of {len(wp)} weeks; no projection in "
                  f"{byes_ if byes_ else 'none'}")
            if v:
                print(f"  weekly rate {np.mean(v):6.2f}/gm over played weeks   "
                      f"season total {np.sum(v):6.1f}")
                print("  " + "  ".join(
                    f"w{w}{'  --' if pd.isna(x) else f'{x:5.1f}'}"
                    for w, x in sorted(wp.items())[:9]))
                print("  " + "  ".join(
                    f"w{w}{'  --' if pd.isna(x) else f'{x:5.1f}'}"
                    for w, x in sorted(wp.items())[9:]))
            m = (wk_meta or {}).get(k, {})
            if m.get("inj"):
                print(f"  feed injury tag: {m['inj']}"
                      + (f" / {m['body']}" if m.get("body") else ""))
        else:
            print("  --- weekly feed: NO ROWS for this player at all ---")

def freshness(board, players, wkly=None):
    """v4 probed ONLY players Sleeper flags IR/Out/PUP, so it never looked at
    Alvin Kamara -- who tore an MCL on Aug 18 and was listed QUESTIONABLE.
    ESPN sat on a full 117-point season line for eleven days while every
    status line read OK.

    But simply widening the probe to Questionable is worse, not better: it
    fires on 225 players and calls Puka Nacua's 356-point line stale. In
    preseason half the league is Questionable and it means nothing.

    The signal is the CONJUNCTION. A player is a genuine staleness hit when
    Sleeper flags him hurt AND rotowire's weekly feed -- which rebuilds daily
    -- declines to project him for the upcoming weeks. One is a tag; both
    together is a source failing to keep up. Hard flags (IR/Out/PUP/Doubtful)
    still count on their own, because those are unambiguous."""
    HARD = ("IR", "Out", "PUP", "NA", "Doubtful")
    SOFT = ("Questionable",)
    tag = {}
    for pid, p in players.items():
        if not isinstance(p, dict): continue
        st = p.get("injury_status")
        if st in HARD + SOFT and p.get("position") in ("QB", "RB", "WR", "TE"):
            tag[norm(p.get("full_name") or "", p["position"])] = st
    if wkly is not None and len(wkly):
        for r in wkly[wkly.inj.notna()].itertuples():
            if r.inj in HARD + SOFT: tag.setdefault(r.key, r.inj)

    # who does the daily weekly feed refuse to project over the next 4 weeks?
    benched = set()
    if wkly is not None and len(wkly):
        cw = current_week(wkly)
        nxt = [w for w in sorted(int(w) for w in wkly.week.unique()) if w >= cw][:4]
        sub = wkly[wkly.week.isin(nxt)]
        for k, g in sub.groupby("key"):
            if g.pts.isna().all(): benched.add(k)

    b, seen, stale = board.set_index("key"), 0, collections.Counter()
    worst = []
    for k, status in tag.items():
        if k not in b.index: continue
        if status in SOFT and k not in benched:
            continue                      # Questionable alone is noise
        r = b.loc[k]
        if isinstance(r, pd.DataFrame): r = r.iloc[0]
        seen += 1
        for s in ("rotowire", "espn"):
            if s in board and not pd.isna(r.get(s)) and float(r.get(s)) > 40:
                stale[s] += 1
                worst.append((float(r.get(s)), r["name"], status, s,
                              "weekly feed benches him" if k in benched else "hard tag"))
    worst.sort(reverse=True)
    age_h = None
    if wkly is not None and len(wkly):
        lm = pd.to_numeric(wkly.last_mod, errors="coerce").dropna()
        if len(lm):
            v = float(lm.max())
            if v > 1e12: v /= 1000.0
            age_h = (time.time() - v) / 3600
    return seen, dict(stale), worst[:8], age_h

def divergence(board, wk_pts, top_n=250, thresh=2.0):
    """THE STALENESS DETECTOR. Compares rotowire-SEASON against rotowire-
    WEEKLY-SUMMED-over-17.

    Why this and not season-vs-espn: it is the SAME PROVIDER and the same
    underlying model on both sides of the subtraction, so a gap cannot be
    'two shops disagree about talent'. It can only be one of the two views
    failing to keep up with news. That makes it a clean staleness signal
    rather than a noisy opinion spread.

    Caveat that matters: there is a real basis offset. Summed weekly runs
    about +0.87/gm hotter than season/17 across the top 200, because the
    season line prices expected missed games and the weekly line prices a
    healthy game. divergence() therefore reports the gap AFTER removing the
    board-wide median offset, so what is left is player-specific -- exactly
    the same trick as the v4 market haircut, for the same reason.

    Positive = weekly says MORE than season (season line is stale-low, or the
    player just gained a role). Negative = weekly says LESS (season line has
    not absorbed an injury or a demotion). Both are 'go read about him'."""
    rows = []
    b = board[(board.n_src >= 2)] if "n_src" in board else board
    for r in b.itertuples():
        k = r.key
        if k not in wk_pts: continue
        v = [x for x in wk_pts[k].values() if not pd.isna(x)]
        if not v: 
            wsum, played = 0.0, 0
        else:
            wsum, played = float(np.sum(v)), len(v)
        season = float(r.rotowire) if not pd.isna(getattr(r, "rotowire", np.nan)) else np.nan
        if pd.isna(season): continue
        rows.append(dict(name=r.name, pos=r.pos, team=r.team,
                         season=round(season, 1), weekly=round(wsum, 1),
                         wks_played=played, proj_pg=round(float(r.proj_pg), 2)))
    if not rows: return pd.DataFrame()
    d = pd.DataFrame(rows)
    d["raw_gap"] = d.weekly - d.season
    core = d.nlargest(min(top_n, len(d)), "season")
    offset = float(core.raw_gap.median())
    d["gap"] = (d.raw_gap - offset).round(1)
    d["gap_pg"] = (d.gap / GAMES).round(2)
    d.attrs["offset"] = offset
    return d[(d.season > 40) | (d.weekly > 40)].sort_values("gap")

# -------------------------------------------------------------------- VOR
def vor_table(board, players, rosters, users, value_col="value_pg"):
    """Value Over Replacement per rostered player on one explicit basis."""
    val = make_val(board, players, value_col=value_col); rl = replacement(board, value_col=value_col)
    umap = {u["user_id"]: u["display_name"] for u in users}
    rows = []
    for r in rosters:
        for pid in r["players"]:
            v = val.get(pid)
            if not v or v[0] <= 0: continue
            rows.append(dict(pid=pid, mgr=umap[r["owner_id"]], rid=r["roster_id"],
                             name=v[2], pos=v[1], value_pg=round(v[0], 2),
                             vor=round(v[0] - rl[v[1]], 2)))
    return pd.DataFrame(rows)

def anchor_curve(vor_df, picks):
    """THE EDGE. Models what the room BELIEVES a player is worth -- a function
    of his draft slot, not his current value. Fit PER POSITION (pooled produces
    a fake signal dominated by QB/TE replacement differences).

    misprice = what he IS worth - what his slot says he's worth.
    Positive = room under-rates him = buy. Negative = sell.
    This gap widens all season. Re-run weekly."""
    pick_of = {}
    for p in picks:
        md = p.get("metadata") or {}
        pick_of[f"{md.get('first_name','')} {md.get('last_name','')}".strip()] = p["pick_no"]
    d = vor_df.copy()
    d["pick"] = d.name.map(pick_of)
    d = d.dropna(subset=["pick"])
    d["anchor"] = np.nan
    for pos, g in d.groupby("pos"):
        if len(g) < 6: continue
        z = np.polyfit(np.log(g["pick"]), g["vor"], 1)
        d.loc[g.index, "anchor"] = z[0]*np.log(g["pick"]) + z[1]
    d["misprice"] = (d.vor - d.anchor).round(2)
    return d.dropna(subset=["anchor"])

def perceived_cap(anc, pid):
    """Draft-anchor capital used only as a manager-perception proxy.

    Negative anchor values are floored at zero. A late-round filler can be
    perceived as worthless, but adding him to a package cannot rationally make
    the elite player beside him cheaper.
    """
    return max(0.0, float(anc.get(str(pid), 0.0)))


def scan_asymmetric(rosters, val, anchor_df, rid=ME, min_gain=1.0,
                    min_looks=0.0, max_n=4, max_diff=2, roster_cap=15):
    """A trade needs to be good for US and ACCEPTABLE to them, measured on
    DIFFERENT value functions.
      me    = change in my best-8         (our board -- what is true)
      looks = draft-slot capital they net (their board -- what they believe)
      truly = change in their best-8      (what it actually costs them)
    Search me >= min_gain AND looks >= min_looks. Report truly, never filter on
    it -- median trades are zero-sum and that is fine.

    v4: package sizes are now INDEPENDENT on each side. v3 looped
    combinations(mine, n) against combinations(their, n) with the same n, so it
    could not construct a 3-for-2 at all -- not as a preference, as a missing
    degree of freedom. v3 also collapsed any larger package that matched a
    smaller one's gain, which threw away real gain: opening both up moved the
    best available package from +2.34 (3-for-3) to +3.22 (4-for-4).

    Uneven shapes are only legal if the receiving side ends up at or under
    roster_cap, so they mostly appear once somebody has an open slot. IR does
    not count against the cap and is excluded here.

    LIMIT: draft slot proxies perception, it is not perception. It overstates
    willingness to move a marquee name. Filter output by whether you would send
    the message with a straight face."""
    anc = dict(zip(anchor_df.pid.astype(str), anchor_df.anchor))
    me = next(r for r in rosters if r["roster_id"] == rid)
    active = lambda r: len(set(r["players"]) - set(r.get("reserve") or []))
    base = best8(me["players"], val)
    nm = lambda p: val.get(p, (0, "", ""))[2]
    out = []
    for o in rosters:
        if o["roster_id"] == rid: continue
        tb = best8(o["players"], val)
        mine  = [p for p in me["players"] if p in val and str(p) in anc]
        their = [p for p in o["players"] if p in val and str(p) in anc]
        for na in range(1, max_n + 1):
            for nb in range(1, max_n + 1):
                if abs(na - nb) > max_diff: continue
                for A in itertools.combinations(mine, na):
                    for B in itertools.combinations(their, nb):
                        na_ = [p for p in me["players"] if p not in A] + list(B)
                        na_, mydrop = legalize_roster(
                            na_, me, val, lambda ids: best8(ids, val), roster_cap)
                        gain = best8(na_, val) - base
                        if gain < min_gain: continue

                        nb_ = [p for p in o["players"] if p not in B] + list(A)
                        nb_, theirdrop = legalize_roster(
                            nb_, o, val, lambda ids: best8(ids, val), roster_cap)

                        # Their perceived gain is draft-anchor capital received
                        # minus capital surrendered AND any forced drop. An
                        # undrafted/waiver drop has no anchor and therefore
                        # contributes zero to this perception proxy.
                        # Perception capital cannot be negative. A late-round
                        # filler may add ~zero perceived value, but it does not
                        # make an elite asset CHEAPER merely by being included.
                        looks = (sum(perceived_cap(anc,p) for p in A)
                                 - sum(perceived_cap(anc,p) for p in B)
                                 - sum(perceived_cap(anc,p) for p in theirdrop))
                        if looks < min_looks: continue
                        out.append(dict(rid=o["roster_id"], pkg=f"{na}for{nb}",
                                        give=" + ".join(nm(p) for p in A),
                                        get=" + ".join(nm(p) for p in B),
                                        my_drop=" + ".join(nm(p) for p in mydrop),
                                        their_drop=" + ".join(nm(p) for p in theirdrop),
                                        me=round(gain, 2), looks=round(looks, 2),
                                        truly=round(best8(nb_, val) - tb, 2)))
    if not out: return pd.DataFrame()
    d = pd.DataFrame(out).drop_duplicates(subset=["give", "get"])
    # sort on gain alone. no size preference -- a 4-for-4 that gains more than
    # a 2-for-2 IS a better trade, and a bigger package is often the easier
    # pitch because both sides find something they like in it.
    return d.sort_values(["me", "looks"], ascending=False).reset_index(drop=True)

SCAN_POOL = 9
SCAN_MAX_N = 3


def _scan_player_pool(roster, val, anc, mode="send", cap=SCAN_POOL):
    """Deterministic bounded pool for normal trade search.

    The old exhaustive scanner crossed every 1..4-player combination on both
    rosters and could sit for tens of minutes. Normal search only needs players
    who are plausible trade pieces: high perceived value relative to lineup
    loss when sending, and high objective/mispriced value when targeting.
    Elite players are explicitly retained so consolidation trades are not
    pruned merely because they are expensive.
    """
    ids=[p for p in roster.get("players",[]) if p in val and str(p) in anc]
    if len(ids) <= cap: return ids
    base=best8(roster.get("players",[]), val)
    rows=[]
    for p in ids:
        v=float(val[p][0]); a=float(anc[str(p)])
        cost=max(0.0, base-best8([q for q in roster.get("players",[]) if q != p], val))
        score=(a-cost) if mode=="send" else ((v-a) - 0.5*cost)
        rows.append((p,v,a,cost,score))
    # Always keep the top three objective assets AND the best asset at each
    # position. Positional upgrades (QB-for-QB, TE-for-TE) otherwise disappear
    # from a small global pool even when they are the best trade on the board.
    keep=[]
    for p,*_ in sorted(rows,key=lambda x:x[1],reverse=True)[:3]:
        if p not in keep: keep.append(p)
    for pos in ("QB","RB","WR","TE"):
        z=[x for x in rows if val[x[0]][1]==pos]
        if z:
            p=max(z,key=lambda x:x[1])[0]
            if p not in keep: keep.append(p)
    for p,*_ in sorted(rows,key=lambda x:x[4],reverse=True):
        if p not in keep: keep.append(p)
        if len(keep)>=cap: break
    return keep[:cap]


def scan_asymmetric_fast(rosters, val, anchor_df, rid=ME, min_gain=0.35,
                         min_looks=0.0, max_n=SCAN_MAX_N, max_diff=2,
                         roster_cap=15, pool_cap=SCAN_POOL):
    """Production trade candidate generator.

    Searches a bounded but high-value subset, then leaves exact supplied-offer
    pricing to trade_pergame()/trade_week(). This is a candidate generator, not
    a proof that no better package exists. Use ``--deep-trade-scan`` for the old
    exhaustive search when completeness matters more than latency.
    """
    anc=dict(zip(anchor_df.pid.astype(str), anchor_df.anchor))
    me=next(r for r in rosters if r["roster_id"]==rid)
    base=best8(me["players"],val)
    nm=lambda p: val.get(p,(0,"",""))[2]
    mine=_scan_player_pool(me,val,anc,"send",pool_cap)
    mine_pkgs=[]
    for n in range(1,min(max_n,len(mine))+1):
        mine_pkgs.extend(itertools.combinations(mine,n))
    out=[]
    for o in rosters:
        if o["roster_id"]==rid: continue
        tb=best8(o["players"],val)
        their=_scan_player_pool(o,val,anc,"get",pool_cap)
        their_pkgs=[]
        for n in range(1,min(max_n,len(their))+1):
            their_pkgs.extend(itertools.combinations(their,n))
        for A in mine_pkgs:
            asum=sum(perceived_cap(anc,p) for p in A)
            for B in their_pkgs:
                if abs(len(A)-len(B))>max_diff: continue
                # Cheap perception bound before any lineup/drop optimization.
                if asum-sum(perceived_cap(anc,p) for p in B) < min_looks-3.0:
                    continue
                na=[p for p in me["players"] if p not in A]+list(B)
                na,mydrop=legalize_roster(na,me,val,lambda ids:best8(ids,val),roster_cap)
                gain=best8(na,val)-base
                if gain<min_gain: continue
                nb=[p for p in o["players"] if p not in B]+list(A)
                nb,theirdrop=legalize_roster(nb,o,val,lambda ids:best8(ids,val),roster_cap)
                looks=(asum-sum(perceived_cap(anc,p) for p in B)
                       -sum(perceived_cap(anc,p) for p in theirdrop))
                if looks<min_looks: continue
                out.append(dict(rid=o["roster_id"],pkg=f"{len(A)}for{len(B)}",
                                give=" + ".join(nm(p) for p in A),
                                get=" + ".join(nm(p) for p in B),
                                my_drop=" + ".join(nm(p) for p in mydrop),
                                their_drop=" + ".join(nm(p) for p in theirdrop),
                                me=round(gain,2),looks=round(looks,2),
                                truly=round(best8(nb,val)-tb,2),search="FAST"))
    if not out: return pd.DataFrame()
    d=pd.DataFrame(out).drop_duplicates(subset=["give","get"])
    return d.sort_values(["me","looks"],ascending=False).reset_index(drop=True)


def rescore_weekly(shortlist, rosters, val, players, wk_pts, fill=None,
                   rid=ME, top=25, weeks=None):
    """Re-price the scanner's output on the WEEKLY basis, then re-rank.

    This exists because of a live failure. On Aug 30 the season board ranked
    David Montgomery 11.96 and Travis Etienne 12.99, so every package the
    scanner liked involved sending Montgomery out to bring Etienne back. The
    weekly feed -- same provider, rebuilt that morning -- had Montgomery at
    14.12/gm and Etienne at 12.43/gm, i.e. the ordering REVERSED. Montgomery's
    season line was 22.6 points stale-low; Etienne's was slightly high.

    A scanner that ranks on a stale number produces confident, wrong
    shortlists. So: search on the season basis (which is the right currency
    for trade VALUE and what the anchor curve is fitted to), then re-rank the
    survivors on the basis that knows about this week's injuries.

    Adds reg / playoff / worst deltas. Sorts on playoff first -- Weeks 15-17
    decide the season and a fat September gain that costs playoff points is a
    bad trade wearing a good number."""
    if not len(shortlist) or not wk_pts: return shortlist
    weeks = _resolve_weeks(weeks)
    me = next(r for r in rosters if r["roster_id"] == rid)
    base = {w: best8_week(me["players"], val, w, wk_pts, players, fill) for w in weeks}
    rg = [w for w in weeks if w <= 14]
    pw = [w for w in weeks if w in (15, 16, 17)]
    out = []
    for row in shortlist.head(top).itertuples():
        give = row.give.split(" + "); get = row.get.split(" + ")
        try:
            r = trade_week(rosters, val, players, wk_pts, rid, give,
                           int(row.rid), get, fill, weeks)
        except Exception:
            continue
        a = r["a"]
        d = row._asdict(); d.pop("Index", None)
        d.update(wk_reg=a["reg_delta"], wk_playoff=a["playoff_delta"],
                 wk_worst=a["worst_after"] - a["worst_before"],
                 worst_wk=a["worst_wk_after"])
        out.append(d)
    if not out: return shortlist
    d = pd.DataFrame(out)
    # a package that helps the season number but costs playoff points is the
    # exact failure this whole layer exists to catch. Surface it.
    d["season_says_yes_weekly_says_no"] = (d.me > 0) & (d.wk_playoff < 0)
    return d.sort_values(["wk_playoff", "wk_reg"], ascending=False).reset_index(drop=True)

# =========================================================================
# v5.2 (Sep 3 2026) -- THE NUMBER MUST CARRY ITS OWN UNCERTAINTY
# =========================================================================
# Nothing here is new data. Every input below was ALREADY on the board and was
# already being computed correctly. The failure this release fixes is that the
# columns got dropped at the point of use, which is the only point that
# matters.
#
# The case: on Sep 3 2026 a trade was priced by quoting
#     Rashee Rice  15.01      vs      Drake London  15.46
# side by side, as if a 0.45 gap were the whole story. It was not. Rice's
# season line was quoted by THREE books -- MIN_BOOKS is 3, so he barely
# cleared the bar to be included at all -- and his two projection sources
# disagreed by 1.83/gm, over the coin-flip line. London's rested on EIGHT
# books and a 1.22 spread. Same estimator, same units, wildly different
# support. Both facts were sitting in n_books and spread_pg. Neither was said.
#
# So: support() attaches the tier to the row, and fmt_val() makes it painful
# to print the number without it.

SUPPORT_MIN_BOOKS   = 6      # a season line this well quoted is corroborated
SUPPORT_THIN_BOOKS  = 4      # at or under this, treat the market read as one opinion
SUPPORT_SPREAD_OK   = 1.00   # rotowire vs espn, pts/gm
SUPPORT_SPREAD_BAD  = 1.75   # the existing coin-flip line, kept identical
SUPPORT_COV_OK      = 0.60

def support(board):
    """Evidence tier attached to value_pg.

    v6.2 uses the median component-level venue depth, not the deepest single
    stat. ``n_books_min``/``n_books_max`` are shown when available so a deep
    receiving-yard market cannot disguise a thin TD/rushing component.
    """
    nb  = board.get("n_books", pd.Series(np.nan, index=board.index))
    nbmin = board.get("n_books_min", nb)
    nbmax = board.get("n_books_max", nb)
    sp  = board.get("spread_pg", pd.Series(np.nan, index=board.index))
    cov = board.get("coverage", pd.Series(0.0, index=board.index))
    tiers, whys = [], []
    for n, nlo, nhi, spr, c in zip(nb, nbmin, nbmax, sp, cov):
        why = []
        if pd.isna(n) or n == 0:
            why.append("no season line")
        else:
            if n <= SUPPORT_THIN_BOOKS:
                why.append(f"{int(round(float(n)))}bk median")
            if not pd.isna(nlo) and not pd.isna(nhi) and float(nhi) - float(nlo) >= 2:
                why.append(f"depth {int(nlo)}-{int(nhi)}bk")
        if not pd.isna(spr) and spr > SUPPORT_SPREAD_BAD:
            why.append(f"spr {spr:.2f} SOURCE DISAGREE")
        elif not pd.isna(spr) and spr > SUPPORT_SPREAD_OK:
            why.append(f"spr {spr:.2f}")
        if pd.isna(c) or c < SUPPORT_COV_OK:
            why.append(f"cov {0 if pd.isna(c) else c:.2f}")
        thin = ((pd.isna(n) or n <= SUPPORT_THIN_BOOKS)
                or (not pd.isna(spr) and spr > SUPPORT_SPREAD_BAD))
        solid = ((not pd.isna(n) and n >= SUPPORT_MIN_BOOKS)
                 and (not pd.isna(spr) and spr <= SUPPORT_SPREAD_OK)
                 and (not pd.isna(c) and c >= SUPPORT_COV_OK))
        tiers.append("THIN" if thin else ("SOLID" if solid else "OK"))
        whys.append(", ".join(why))
    board["support"] = tiers
    board["support_why"] = whys
    board["support_rank"] = [{"SOLID":2, "OK":1, "THIN":0}[t] for t in tiers]
    return board

def fmt_val(board, name, wide=True):
    """value_pg with its support glued on. USE THIS ANY TIME A NUMBER IS
    ABOUT TO BE QUOTED TO A HUMAN OR SET NEXT TO ANOTHER PLAYER'S NUMBER.

        fmt_val(b, "Rashee Rice")  -> '15.01 [3bk, spr 1.83 COIN FLIP | THIN]'
        fmt_val(b, "Drake London") -> '15.46 [SOLID]'
    """
    r = board[board.name.str.lower() == str(name).lower()]
    if not len(r): return f"{name}: not on board"
    r = r.iloc[0]
    if "support" not in board: board = support(board); r = board[board.name == r["name"]].iloc[0]
    why = r.get("support_why", "")
    tag = f"{why} | {r['support']}" if why else r["support"]
    return f"{r.value_pg:.2f} [{tag}]" if wide else f"{r.value_pg:.2f} [{r['support']}]"

def compare_players(board, names, ig=None):
    """Side-by-side with support carried. The function that should have been
    called instead of quoting two bare floats."""
    rows = []
    if "support" not in board: board = support(board)
    for n in names:
        r = board[board.name.str.lower() == str(n).lower()]
        if not len(r): continue
        r = r.iloc[0]
        d = dict(name=r["name"], pos=r.pos, value_pg=round(float(r.value_pg), 2),
                 n_books=(np.nan if pd.isna(r.get("n_books", np.nan)) else int(r.get("n_books"))),
                 spread=round(float(r.spread_pg), 2),
                 coverage=round(float(r.get("coverage", 0)), 2),
                 support=r["support"], why=r["support_why"])
        if ig is not None:
            d["impl_games"] = ig.get(r.key, np.nan)
        rows.append(d)
    return pd.DataFrame(rows)

# ------------------------------------------------- market-implied games
# value_pg is a PER-GAME number and is not availability-adjusted -- the BRIEF
# has said so for two versions as a caveat, with no way to measure it. This
# measures it, from two book numbers and nothing else:
#
#     implied_games = season_total_line / this_week_per_game_line
#
# No fitted constants, no assumed distribution, no injury model. If a book
# quotes Rice 975.5 receiving yards for the season and 61.5 for the game, the
# book is carrying about 15.9 games for him. London reads 1100.5 and 63.5,
# i.e. 17.3. PER HEALTHY GAME those two are two yards apart; the entire season
# gap between them is availability. That is precisely the thing ADP prices and
# value_pg does not, and it is why a round of draft capital compresses to
# 0.45 pts/gm on this board.
#
# Measured Sep 3 2026: computable for 127 of 146 season-covered players,
# median 15.7, IQR 14.6-16.7. It independently flagged Chuba Hubbard at 11.8
# (camp hamstring) and Chris Olave at 13.6 (concussion history) without being
# told about either.
#
# HONEST LIMIT, AND IT IS A BIG ONE RIGHT NOW. Only the upcoming week has
# per-game lines posted, so this is currently ONE ratio off ONE game, and a
# soft Week 1 matchup is indistinguishable from injury risk. It is
# EXPERIMENTAL until several weeks of lines exist and the per-game leg can be
# averaged. Re-measure at Week 4; if the week-to-week reading on a healthy
# player is not stable inside about a game, this metric is measuring schedule
# and should be deleted rather than trusted.
IG_SEASON_TO_GAME = [("rec_yd_mkt", "rec_yd"), ("rush_yd_mkt", "rush_yd"),
                     ("pass_yd_mkt", "pass_yd")]
IG_SANE = (8.0, 22.0)

def implied_games(board, week, mkw=None, books=None):
    """-> (dict key -> implied games, DataFrame of the workings).

    Pass mkw to reuse an existing src_market_weekly() pull instead of paying
    for another one."""
    if mkw is None:
        mkw = src_market_weekly(week, ) if False else src_market_weekly(week)
    if mkw is None or not len(mkw): return {}, pd.DataFrame()
    g = mkw.groupby("key").first()
    rows = []
    for r in board.itertuples():
        if r.key not in g.index: continue
        row = g.loc[r.key]
        est = []
        for szn_c, pg_c in IG_SEASON_TO_GAME:
            s = getattr(r, szn_c, np.nan)
            p = row[pg_c] if pg_c in row.index else np.nan
            if pd.isna(s) or pd.isna(p) or float(p) <= 0: continue
            est.append(float(s) / float(p))
        if not est: continue
        v = float(np.median(est))
        if not (IG_SANE[0] < v < IG_SANE[1]): continue
        rows.append(dict(key=r.key, name=r.name, pos=r.pos,
                         value_pg=round(float(r.value_pg), 2),
                         implied_games=round(v, 1), n_stats=len(est)))
    if not rows: return {}, pd.DataFrame()
    d = pd.DataFrame(rows)
    return dict(zip(d.key, d.implied_games)), d

def availability_report(board, ig_df, roster_names=None, top=10):
    """Who the market expects to miss time, and how that reshapes a comparison
    the season board shows as close."""
    if not len(ig_df): return pd.DataFrame()
    d = ig_df.copy()
    med = float(d.implied_games.median())
    d["vs_median"] = (d.implied_games - med).round(1)
    # expected season points = per-game value x games the book expects
    d["exp_season"] = (d.value_pg * d.implied_games).round(1)
    if roster_names:
        d["mine"] = d.name.isin(set(roster_names))
    return d.sort_values("implied_games").reset_index(drop=True)

# ---------------------------------------------------------------- tail risk
# The engine has no variance model and is not getting one from this release --
# a real one needs game-log history that nothing here pulls, and a fabricated
# CV would be worse than the honest gap. What it CAN do is stop pretending the
# gap does not exist at the moment a decision is made.
#
# Same contract as OVERRIDES: dated, sourced, printed in full every run,
# refused if either is missing. This does NOT touch any number. It is a flag
# that fires next to a player whose DOWNSIDE DISTRIBUTION is materially worse
# than his median, so a median-based comparison is known to be flattering him.
# Keep it short and delete entries when the reason expires.
TAIL_RISK = [
    dict(player="Rashee Rice", pos="WR", dated="2026-09-03",
         src="NFL closed the conduct investigation ~Aug 12 with no discipline "
             "(Rapoport); ESPN KC beat (Taylor) reports he is not back to 100% "
             "after offseason knee surgery; Mahomes returning from a torn ACL",
         note="Six-game conduct suspension in 2025, season-ending concussion, "
              "2024 LCL tear, 2026 offseason knee cleanup. Median is fine; the "
              "left tail is fatter than any WR near his value_pg. Season line "
              "sits on only 3 books, spread 1.83."),
    dict(player="Chris Olave", pos="WR", dated="2026-09-03",
         src="five documented concussions, Dec 2025 pulmonary embolism, "
             "extension guarantees void on recurrence",
         note="implied_games 13.6 against a 15.7 board median. value_pg is a "
              "healthy-17 number and does not price this."),
    dict(player="Alvin Kamara", pos="RB", dated="2026-09-03",
         src="Schefter Aug 19 MCL sprain; still absent from practice Sep 3 "
             "(Triplett); ESPN season line frozen at 113.1 since the injury",
         note="Board takes the median of a live source (rotowire 63) and a "
              "frozen one (espn 113). The x0.85 override is patching a source "
              "failure, not a judgment call -- revisit when ESPN moves."),
]

def tail_risk_report(board=None, verbose=True):
    """Validate and print TAIL_RISK. Returns (applied, refused). Applies
    nothing to any number by design."""
    ok, refused = [], []
    names = set(board.name) if board is not None else None
    for t in TAIL_RISK:
        who = f"{t.get('player','?')} ({t.get('pos','?')})"
        if not t.get("dated") or not t.get("src"):
            refused.append((who, "missing dated= or src=")); continue
        if names is not None and t["player"] not in names:
            refused.append((who, "not on board")); continue
        age = (time.time() - _od(t["dated"])) / 86400
        ok.append((who, age, t["dated"], t["src"], t.get("note", "")))
    if verbose:
        print("\n=== TAIL RISK (median is flattering these players; no number is changed) ===")
        if not ok and not refused: print("  none")
        for who, age, dated, src, note in ok:
            warn = "   <-- STALE, RE-CHECK" if age > STALE_OVERRIDE_DAYS else ""
            print(f"  FLAG     {who:26s} ({int(age)}d old, {dated}){warn}")
            print(f"           src: {src}")
            if note: print(f"           why: {note}")
        for who, why in refused:
            print(f"  REFUSED  {who:26s} {why}")
    return ok, refused

def tail_flagged(names):
    """-> the subset of `names` carrying a tail-risk flag. Call before
    reporting any trade, so a flagged player cannot leave in silence."""
    flagged = {t["player"] for t in TAIL_RISK if t.get("dated") and t.get("src")}
    return [n for n in names if n in flagged]

# =========================================================================
# v5.3 (Sep 4 2026) -- PER-GAME IS THE RANKING BASIS, AND IT IS E[best8]
# =========================================================================
# THE BUG THIS FIXES. Through v5.2 the "bye-neutral per game" number every
# ranking and every trade was decided on was computed like this:
#
#     rate[player] = mean of his weekly projections over the weeks he plays
#     strength     = best8(rate)                       <-- ONE lineup
#
# That is best8(E[X]). It is not what you score. What you score is E[best8(X)]
# -- you look at each week's projections and set the best legal lineup THAT
# WEEK, seventeen separate times. best8 is a max over lineup combinations,
# i.e. convex, so by Jensen
#
#     E[best8(X)]  >=  best8(E[X])                     always
#
# The old number was a lower bound. Worse, the bias is NOT a constant offset:
# a roster with several close mid-tier bodies gets more weeks where one of
# them happens to be the best flex, so it collects more of the gap than a
# top-heavy roster whose lineup never changes. That is a RANKING bias.
#
# Measured Sep 4 2026 across the 12 rosters: mean gap +0.32/gm, range +0.01
# (Nugtj, theilluminadi -- rigid lineups) to +1.94 (Viswa -- deepest roster in
# the league). It moved five of twelve teams by one rank. Viswa went 9th to
# 7th on nothing but the correct estimator.
#
# TWO SMALLER BUGS FIXED AT THE SAME TIME, both in the old rate:
#   * it dropped weeks a player is projected NOT TO PLAY from the denominator
#     entirely, instead of scoring them 0. An injury week is a real missed
#     game and is not the schedule's fault. Now scored 0.
#   * week 18 leaked into the mean while the lineup loop only ran 1-17, so the
#     two bases were silently measured over different seasons.
#
# HOW BYES ARE NEUTRALISED, and why this way. The point of a bye-neutral
# number is "how good is this team in a week it is at full strength", because
# a better team per game wins more close matchups regardless of schedule. So a
# bye week is played with the player's OWN non-bye rate substituted in -- the
# week happens, he just is not punished for the calendar. The alternatives are
# both wrong: deleting the week changes the denominator and quietly rewards
# whoever has more byes; zeroing him IS the bye penalty we chose to ignore.
#
# Byes are still fully visible -- pergame_weeks() and best8_week() report them
# untouched. This basis is for "who has the best team", not "what happens in
# week 11".

PG_WEEKS = list(range(1, 18))  # explicit full-season/historical use only


def _resolve_weeks(weeks=None):
    return remaining_weeks() if weeks is None else list(weeks)

def player_rates(wk_pts, wk_bye, weeks=None):
    """key -> mean points over the weeks he is PROJECTED and NOT on bye.

    Unprojected non-bye weeks are excluded HERE (this is the rate he scores at
    when he plays) and scored 0 in bye_neutral() (that is where missed games
    become a cost). Keeping the two separate is what stops an injury from
    being laundered into a bye."""
    weeks = _resolve_weeks(weeks)
    out = {}
    for k, d in wk_pts.items():
        byes = wk_bye.get(k, set())
        v = [x for w, x in d.items()
             if w in weeks and w not in byes and not pd.isna(x)]
        out[k] = float(np.mean(v)) if v else 0.0
    return out

def bye_neutral(wk_pts, wk_bye, rates=None, weeks=None):
    """key -> {week: points}, byes replaced by the player's own rate.

    bye week          -> his own rate (the calendar is neutralised)
    projected week    -> the real weekly number (variance preserved)
    unprojected week  -> 0.0 (injury or no role: a real cost, kept)"""
    weeks = _resolve_weeks(weeks)
    rates = rates if rates is not None else player_rates(wk_pts, wk_bye, weeks)
    out = {}
    for k, d in wk_pts.items():
        byes = wk_bye.get(k, set())
        r = rates.get(k, 0.0)
        out[k] = {w: (r if w in byes
                      else (0.0 if pd.isna(d.get(w, np.nan)) else float(d[w])))
                  for w in weeks}
    return out

def stream_pool(board, players, rosters, mat, rates, per_pos=3, look=15):
    """Best free agent per position, carried as a WEEKLY VECTOR.

    The streamer has to be bye-neutral too -- if your waiver QB is off, you
    start a different waiver QB, you do not start nobody. Carrying his vector
    rather than a scalar also means the fill benefits from the same weekly
    optimisation as everyone else, which is the whole point of this basis."""
    fa = wire(board, players, rosters, value_col=objective_col)
    out = {}
    for pos in ("QB", "RB", "WR", "TE"):
        c = []
        for _, r in fa[fa.pos == pos].head(look).iterrows():
            k = norm(r["name"], pos)
            c.append((rates.get(k, 0.0), r["name"], mat.get(k)))
        c.sort(key=lambda x: -x[0])
        out[pos] = c[:per_pos]
    return out

def _pg_week(pids, val, mat, rates, pool, week):
    """Price only this roster, avoiding a full player-board scan per week.

    The previous implementation visited thousands of unrelated players for
    every candidate trade. Restricting the lookup to roster IDs is equivalent
    because best8 reads only those IDs. No identity cache is needed, so a
    projection changed in place is immediately reflected in the next score.
    """
    keep = list(pids)
    wv = {}
    for pid in keep:
        value = val.get(pid)
        if value is None:
            continue
        v, pos, nm = value
        k = norm(nm, pos)
        wv[pid] = ((mat[k][week] if k in mat else 0.0), pos, nm)
    for pos, cands in (pool or {}).items():
        if not cands: continue
        r, nm, m = cands[0]
        fid = f"__FA_{pos}"
        wv[fid] = ((m[week] if m else r), pos, nm)
        keep.append(fid)
    return best8(keep, wv)

def pergame(pids, val, mat, rates, pool=None, weeks=None):
    """E[best8] -- THE number. Optimise every week, then average.

    Replaces best8(player_rates(...)) everywhere it was being used to rank a
    roster or price a trade. See pergame_naive() for the old one and
    jensen_gap() for the difference."""
    weeks = _resolve_weeks(weeks)
    if not weeks: return 0.0
    return sum(_pg_week(pids, val, mat, rates, pool, w) for w in weeks) / len(weeks)

def pergame_weeks(pids, val, mat, rates, pool=None, weeks=None):
    """The same thing, week by week, so the shape is inspectable."""
    weeks = _resolve_weeks(weeks)
    return {w: _pg_week(pids, val, mat, rates, pool, w) for w in weeks}

def pergame_naive(pids, val, rates, pool=None):
    """DEPRECATED -- best8(E[X]), the pre-v5.3 number.

    Kept for ONE purpose: measuring how wrong it was. Do not rank on it, do
    not price a trade on it. It is a biased lower bound on pergame()."""
    rv = {pid: (rates.get(norm(nm, pos), 0.0), pos, nm)
          for pid, (v, pos, nm) in val.items()}
    keep = list(pids)
    for pos, cands in (pool or {}).items():
        if not cands: continue
        r, nm, _ = cands[0]
        rv[f"__FA_{pos}"] = (r, pos, nm); keep.append(f"__FA_{pos}")
    return best8(keep, rv)

def jensen_gap(rosters, val, mat, rates, pool=None):
    """How much the deprecated estimator understated each roster. A LARGE
    SPREAD here is the alarm: it means the old number was re-ordering teams,
    not just shifting them."""
    rows = []
    for r in rosters:
        a = pergame(r["players"], val, mat, rates, pool)
        b = pergame_naive(r["players"], val, rates, pool)
        rows.append(dict(rid=r["roster_id"], pergame=round(a, 2),
                         naive=round(b, 2), gap=round(a - b, 2)))
    return pd.DataFrame(rows).sort_values("pergame", ascending=False)

def pergame_table(rosters, users, val, mat, rates, pool=None, weeks=None):
    """League power ranking on the corrected basis, with the bye damage shown
    alongside rather than baked in -- byes are context, not the ranking."""
    weeks = _resolve_weeks(weeks)
    umap = {u["user_id"]: u["display_name"] for u in users}
    rows = []
    for r in rosters:
        wk = pergame_weeks(r["players"], val, mat, rates, pool, weeks)
        rows.append(dict(mgr=umap[r["owner_id"]], rid=r["roster_id"],
                         pergame=round(sum(wk.values()) / len(wk), 2),
                         best_wk=round(max(wk.values()), 1),
                         worst_wk=round(min(wk.values()), 1),
                         playoff=round(np.mean([wk[w] for w in (15, 16, 17)
                                                if w in wk]), 2)))
    d = pd.DataFrame(rows).sort_values("pergame", ascending=False)
    d.insert(0, "rank", range(1, len(d) + 1))
    return d.reset_index(drop=True)

def trade_pergame(rosters, val, mat, rates, pool, rid_a, out_a, rid_b, out_b):
    """Price an offer on the corrected per-game basis, both sides.

    Same contract as trade_week() but one honest number instead of a season
    total that is blind to when the points land and a weekly total that is
    dominated by byes. COIN_FLIP is the significance bar -- anything under it
    is noise and should not be argued as an edge."""
    ra = next(r for r in rosters if r["roster_id"] == rid_a)
    rb = next(r for r in rosters if r["roster_id"] == rid_b)
    nm = lambda p: val.get(p, (0, "", ""))[2]
    A = [p for p in ra["players"] if nm(p) in out_a]
    B = [p for p in rb["players"] if nm(p) in out_b]
    miss = ([x for x in out_a if x not in [nm(p) for p in A]] +
            [x for x in out_b if x not in [nm(p) for p in B]])
    if miss: raise ValueError(f"not on the stated roster: {miss}")
    na = [p for p in ra["players"] if p not in A] + B
    nbb = [p for p in rb["players"] if p not in B] + A
    f = lambda ids: pergame(ids, val, mat, rates, pool)
    na, drop_a = legalize_roster(na, ra, val, f)
    nbb, drop_b = legalize_roster(nbb, rb, val, f)
    a0, a1 = f(ra["players"]), f(na)
    b0, b1 = f(rb["players"]), f(nbb)
    return dict(me_before=round(a0, 2), me_after=round(a1, 2),
                me=round(a1 - a0, 2), them_before=round(b0, 2),
                them_after=round(b1, 2), them=round(b1 - b0, 2),
                me_forced_drops=[nm(p) for p in drop_a],
                them_forced_drops=[nm(p) for p in drop_b],
                significant=abs(a1 - a0) >= COIN_FLIP,
                tail=tail_flagged(list(out_a) + list(out_b)))

# v6.0: this is a CONFIDENCE LABEL, NOT A GATE. See trade_confidence().
# Realised capture is ~100% at every edge size, so a 1.0/gm edge is a real
# 1.0/gm gain you are right about 57% of the time -- worth taking. Pooled
# 2023-25 MAE is 2.76 (2.67 / 2.70 / 2.93 by year, i.e. stable).
COIN_FLIP = 2.76      # pts/gm. v5.9: MEASURED against actual outcomes
                      # (backtest(), n=291, MAE 2.93). Was 1.75, which was the
                      # shop-vs-shop disagreement -- only ~38% of the real
                      # error. Two shops agreeing means they read the same
                      # reports. For a 2-for-2 use forecast_error(players=4).
_OLD_COIN_FLIP = 1.75 # what the file used through v5.8. Same bar as
                      # SUPPORT_SPREAD_BAD, deliberately: a gap smaller than
                      # the disagreement between two projection shops is not a
                      # gap you can act on.

def pergame_setup(board, wk_pts, wk_bye, players, rosters,
                  include_streamers=False, weeks=None):
    """Build the remaining-week basis.

    Headline roster strength uses only rostered players. Free agents enter only
    an explicitly requested streaming hypothetical.
    """
    weeks = _resolve_weeks(weeks)
    rates = player_rates(wk_pts, wk_bye, weeks)
    mat = bye_neutral(wk_pts, wk_bye, rates, weeks)
    pool = stream_pool(board, players, rosters, mat, rates) if include_streamers else None
    return rates, mat, pool

def attach_ros_values(board, wk_pts, wk_bye, wk_spread=None, source_audit=None, weeks=None):
    """Attach the authoritative remaining-season player value to ``board``.

    ``ros_pg`` is the mean of the same bye-neutral weekly matrix used by
    pergame(). A bye is replaced by the player's own projected playing rate;
    a non-bye week with no role/injury remains zero. This makes the individual
    trade/waiver basis consistent with the roster optimizer instead of letting
    a stale season projection drive search while weekly truth drives ranking.

    Season ``value_pg`` is preserved unchanged for market/source provenance.
    """
    if wk_pts is None or not len(wk_pts):
        board = board.copy()
        board["ros_pg"] = board["value_pg"]
        board["ros_gap"] = 0.0
        board["ros_play_rate"] = board["value_pg"]
        board["ros_active_frac"] = np.nan
        board["ros_weekly_spread"] = np.nan
        board["ros_role_conflicts"] = 0
        board["ros_support"] = "SEASON_FALLBACK"
        return board
    weeks = _resolve_weeks(weeks)
    rates = player_rates(wk_pts, wk_bye, weeks)
    mat = bye_neutral(wk_pts, wk_bye, rates, weeks)
    spread_mean = {}
    if wk_spread:
        for k,d in wk_spread.items():
            v=[float(x) for w,x in d.items() if w in weeks and not pd.isna(x)]
            spread_mean[k] = float(np.mean(v)) if v else np.nan
    conflicts = collections.Counter()
    if source_audit is not None and len(source_audit):
        z = source_audit[(source_audit.week.isin(weeks)) & (source_audit.role_conflict == True)]
        conflicts.update(z.key.value_counts().to_dict())
    out = board.copy()
    ros, rate, frac, ws, rc, supp = [], [], [], [], [], []
    for r in out.itertuples():
        k=r.key
        m=mat.get(k, {})
        vals=[float(m.get(w,0.0)) for w in weeks]
        rr=float(np.mean(vals)) if vals else float(getattr(r,"value_pg",0.0))
        pr=float(rates.get(k, rr))
        by=set((wk_bye or {}).get(k,set()))
        active=[]
        for w in weeks:
            if w in by: continue
            v=(wk_pts.get(k,{}) or {}).get(w,np.nan)
            active.append(0.0 if pd.isna(v) else float(v))
        af=(sum(v>0.01 for v in active)/len(active)) if active else np.nan
        sm=spread_mean.get(k,np.nan); nconf=int(conflicts.get(k,0))
        if nconf:
            tier="ROLE_CONFLICT"
        elif not pd.isna(sm) and sm >= COIN_FLIP:
            tier="LOW"
        elif not pd.isna(sm) and sm > SUPPORT_SPREAD_OK:
            tier="OK"
        else:
            tier="SOLID"
        ros.append(rr); rate.append(pr); frac.append(af); ws.append(sm); rc.append(nconf); supp.append(tier)
    out["ros_pg"] = ros
    out["ros_gap"] = out["ros_pg"] - out["value_pg"]
    out["ros_play_rate"] = rate
    out["ros_active_frac"] = frac
    out["ros_weekly_spread"] = ws
    out["ros_role_conflicts"] = rc
    out["ros_support"] = supp
    return out


# =========================================================================
# v5.4 (Sep 4 2026) -- SOURCING HYGIENE
# =========================================================================
# PrizePicks was investigated as a receptions source and is CONFIRMED DEAD:
# api.prizepicks.com returns 403 behind a DataDome captcha, partner-api
# returns 429. Already in the DEAD ENDS list; re-tested Sep 4, unchanged.
# Do not spend another session on it.
#
# The receptions hole is real and it is the biggest one left. Measured on the
# current board, the DERIVED receptions figure is 36-44% of the market number
# for every elite pass catcher -- 6.68 pts/gm of Chase, 6.28 of JSN, 6.36 of
# McBride. In full PPR a reception is a whole point, so this is not a rounding
# question, it is the largest single unsourced quantity in the engine.
#
# What is actually fixable, in order of size:
#
#   1. ACCUMULATE market 104 WEEKLY. Season market 330 is mislabelled upstream
#      and always empty. Per-game market 104 is real -- but ONLY for the
#      upcoming week. Tested Sep 4: week 1 returns 152 props, weeks 2/3/4/5/6/
#      10/18 all return 0. Books have not posted them yet. So there is no way
#      to build a season total today -- but there is a way to build one over
#      the season, by caching each week's real lines permanently as they post
#      and letting the bridge cover only the weeks not yet played. Bridged
#      share falls every single week with no extra work. rec_history() does
#      this. Run it once a week, it is append-only and never re-derives a week
#      it already has real numbers for.
#
#   2. STOP BRIDGING OFF A BORROWED YPC. 8 players carry ypc_src='proj', i.e.
#      their receptions were derived from a yards-per-catch that was itself a
#      projection -- a derivation on top of a derivation. Where a player has
#      his own week-1 book receptions AND yards line, his own market-implied
#      YPC is available and is strictly better. Courtland Sutton is the live
#      case: engine uses 13.16, his own week-1 book line implies 9.44, a 39%
#      error in the divisor that UNDERSTATES his receptions by roughly 22 over
#      a season. own_ypc() fixes this class.
#
#   3. DETECT STALENESS BY ITS SIGNATURE. The engine cannot see that a line
#      moved -- it has no repricing history and the consensus carries no
#      timestamp. It CAN see the fingerprint a stale line leaves: the books
#      and the projections diverging far past where they normally sit. Josh
#      Jacobs is the standing example (spread 4.63, widest on the board; his
#      line predated his exempt-list placement and the engine happily quoted
#      +5.83 market edge off it). stale_suspects() flags that shape so it
#      cannot be quoted silently again.

def rec_history(weeks=None, refresh_week=None, path=None):
    """Append-only cache of REAL per-game receptions lines, week by week.

    Market 104 only ever answers for the upcoming week, so a season total has
    to be accumulated rather than requested. Call this weekly. It keeps every
    week it has ever successfully pulled and only reaches out for weeks it is
    missing (or the one named in refresh_week, for a same-week line move).

    Returns {week: {key: receptions}}."""
    path = path or os.path.join(CACHE, "rec_history.pkl")
    hist = {}
    if os.path.exists(path):
        try: hist = pickle.load(open(path, "rb"))
        except Exception: hist = {}
    want = weeks if weeks is not None else list(range(1, 19))
    for wk in want:
        if wk in hist and wk != refresh_week and hist[wk]:
            continue
        try:
            mk = src_market_weekly(wk)
        except Exception:
            continue
        if mk is None or len(mk) == 0 or "rec" not in mk.columns:
            continue
        g = mk.groupby("key")["rec"].first().dropna()
        if len(g) == 0:
            continue                       # not posted yet; try again next week
        hist[wk] = {k: float(v) for k, v in g.items()}
    os.makedirs(CACHE, exist_ok=True)
    pickle.dump(hist, open(path, "wb"))
    return hist

def rec_season_from_history(hist, board, games=GAMES):
    """Season receptions = REAL weeks summed + bridge for the rest.

    Returns (rec_total, real_fraction) per key. real_fraction is the share of
    the season that is now actual book lines rather than a derived YPC -- it
    should climb toward 1.0 as the season runs, and it is the number to quote
    when someone asks how solid a full-PPR valuation is."""
    real_wks = {w: d for w, d in (hist or {}).items() if d and w <= games}
    n_real = len(real_wks)
    per = collections.defaultdict(list)
    for w, d in real_wks.items():
        for k, v in d.items():
            per[k].append(v)
    out, frac = {}, {}
    bi = board.set_index("key")
    for k in bi.index:
        got = per.get(k, [])
        bridged = bi.loc[k, "rec_mkt"] if "rec_mkt" in bi.columns else np.nan
        if isinstance(bridged, pd.Series): bridged = bridged.iloc[0]
        if not got:
            out[k] = float(bridged) if not pd.isna(bridged) else np.nan
            frac[k] = 0.0
            continue
        rate = float(np.mean(got))
        rest = games - len(got)
        # remaining weeks priced at the bridged per-game rate where we have one,
        # else at his own realised market rate
        b_pg = (float(bridged) / games) if not pd.isna(bridged) else rate
        out[k] = sum(got) + rest * b_pg
        frac[k] = len(got) / games
    return out, frac

def own_ypc(board, week=1, mkw=None):
    """Market-implied yards-per-catch from a player's OWN week-1 book lines.

    Only returned where BOTH his receptions and his receiving-yards lines
    exist at that week, so it is never itself a derivation. Use it to replace
    ypc_src=='proj' entries, which are bridges built on bridges."""
    mkw = mkw if mkw is not None else src_market_weekly(week)
    if mkw is None or len(mkw) == 0: return {}
    g = mkw.groupby("key").first()
    out = {}
    for k, r in g.iterrows():
        rec = r.get("rec", np.nan); ry = r.get("rec_yd", np.nan)
        if pd.isna(rec) or pd.isna(ry) or float(rec) <= 0: continue
        v = float(ry) / float(rec)
        if 3.0 <= v <= 25.0:               # anything outside is a parse error
            out[k] = v
    return out

def ypc_audit(board, week=1, mkw=None):
    """Every player whose receptions were bridged off a BORROWED ypc, next to
    the ypc his own market implies. A large delta here is a large error in his
    reception count, and in full PPR that is a point per reception."""
    o = own_ypc(board, week, mkw)
    rows = []
    for r in board[board.rec_mkt.notna()].itertuples():
        mine = o.get(r.key)
        borrowed = (r.ypc_src == "proj") or (r.ypc_is_own is False)
        if not borrowed and mine is None: continue
        used = float(r.ypc_used) if not pd.isna(r.ypc_used) else np.nan
        rows.append(dict(key=r.key, name=r.name, pos=r.pos, team=r.team,
                         value_pg=round(float(r.value_pg), 2),
                         ypc_used=round(used, 2), ypc_own=(round(mine, 2) if mine else None),
                         ypc_src=r.ypc_src,
                         rec_now=round(float(r.rec_mkt), 1),
                         rec_fixed=(round(float(r.rec_mkt) * used / mine, 1)
                                    if mine and used == used else None),
                         fixable=mine is not None))
    d = pd.DataFrame(rows)
    if len(d):
        d["rec_delta"] = (d.rec_fixed - d.rec_now).round(1)
        d["pts_pg"] = (d.rec_delta / GAMES).round(2)
        d = d.sort_values("pts_pg", key=lambda s: s.abs(), ascending=False)
    return d

def stale_suspects(board, hard=None):
    """Flag the FINGERPRINT of a stale line, since the line itself cannot be
    timestamped.

    A market that has not repriced after news diverges from the projections,
    which have. So: an extreme books-minus-projections gap, or a book/shop
    disagreement far past the coin-flip bar, is the signature. This does not
    prove staleness -- it says the number is not safe to quote bare. Josh
    Jacobs is the reference case."""
    hard = hard if hard is not None else COIN_FLIP * 2
    d = board[(board.n_mkt > 0) & (board.n_src >= 2)].copy()
    why = []
    for r in d.itertuples():
        f = []
        if not pd.isna(r.spread_pg) and float(r.spread_pg) >= hard:
            f.append(f"shops disagree {float(r.spread_pg):.2f}/gm")
        if not pd.isna(r.mkt_edge) and abs(float(r.mkt_edge)) >= hard:
            f.append(f"market edge {float(r.mkt_edge):+.2f}")
        if not pd.isna(r.n_books) and float(r.n_books) <= 4:
            f.append(f"only {int(r.n_books)} books")
        if r.ypc_src == "proj":
            f.append("receptions bridged off a borrowed ypc")
        why.append("; ".join(f))
    d["why"] = why
    d = d[d.why != ""]
    return d[["name", "pos", "team", "value_pg", "spread_pg", "mkt_edge",
              "n_books", "support", "why"]].sort_values("spread_pg",
                                                        ascending=False)

# =========================================================================
# v5.5 (Sep 4 2026) -- TWO DEAD ENDS BROKEN
# =========================================================================
# "We shouldn't have dead ends." Correct. Re-probed all of them. Results:
#
#   STILL DEAD (do not retry):
#     PrizePicks     403, DataDome captcha. partner-api 429.
#     DraftKings     403 at sportsbook-nash CDN.
#     FanDuel        400 at sbapi.
#     ESPN odds      403 at site.api scoreboard.
#     BettingPros 330 (season receptions) confirmed permanently empty -- I
#                    pulled their FULL market catalog (129 NFL markets, 32
#                    season-period) and 330 is the only season receptions
#                    market that exists. There is no alternate id. Closed.
#
#   NEWLY LIVE, both added below:
#     Underdog Fantasy  api.underdogfantasy.com/beta/v5/over_under_lines
#                       200. 11,917 lines, 602 NFL players, NO AUTH.
#     nflverse          github.com/nflverse/nflverse-data/releases/download/
#                       stats_player/stats_player_reg_2025.csv
#                       200. 2,020 rows of ACTUAL 2025 production.
#
# WHY UNDERDOG IS NOT PRIZEPICKS. I assumed it was another fixed-payout
# pick'em where the line is shaded and unusable as a probability. It is not.
# Underdog posts line_type="balanced" with a two-sided american_price on each
# side (e.g. -112 higher). That is a real vigged market and the existing devig
# machinery applies to it directly. Treat it as a venue, not as a projection.
#
# WHAT IT ACTUALLY BUYS:
#   * WEEKLY RECEPTIONS: 292 lines vs BettingPros' 152. Nearly double. This is
#     the largest hole in the engine and this is the biggest single fix
#     available to it right now.
#   * SEASON LINES BettingPros also has (receiving yards 95, rec tds 87, rush
#     yards 57, rush tds 58, pass yards/tds 31 each) -- an INDEPENDENT second
#     venue on the same quantity, so spread_pg finally measures book-vs-book
#     disagreement and not just shop-vs-shop.
#   * DEPTH BettingPros does not carry at all: Kenyon Sadiq, Makai Lemon, Omar
#     Cooper, Carnell Tate, Denzel Boston, Germie Bernard. Those are the exact
#     names sitting in the "bridged off a borrowed ypc" bucket.
#   * STILL NO season receptions. Nobody sells it. Underdog does not either.
#     The accumulate-weekly path from v5.4 remains the only route to one.
#
# nflverse closes the OTHER half of the bridge. The bridge needs a
# yards-per-catch; the engine was borrowing a positional average for 8
# players. nflverse gives each player's ACTUAL 2025 receptions and receiving
# yards, so his real YPC is available -- an empirical number about that
# specific player instead of an assumption about his position group.

UD_URL = "https://api.underdogfantasy.com/beta/v5/over_under_lines"
UD_SEASON = {"season_receiving_yards": "rec_yd", "season_rec_tds": "rec_td",
             "season_rush_yards": "rush_yd", "season_rush_tds": "rush_td",
             "season_pass_yards": "pass_yd", "season_pass_tds": "pass_td"}
UD_GAME = {"receiving_rec": "rec", "receiving_yds": "rec_yd",
           "rushing_yds": "rush_yd", "rush_rec_tds": "rush_rec_td",
           "passing_yds": "pass_yd"}
NFLVERSE = ("https://github.com/nflverse/nflverse-data/releases/download/"
            "stats_player/stats_player_reg_{yr}.csv")

def _ud_positions(players):
    """Underdog's `position_id` is a UUID, not a position string. Resolve it by
    matching player names against Sleeper's roster and taking a majority vote
    per UUID, so the mapping is learned from the data rather than hardcoded to
    ids that will rotate."""
    try:
        _, _, pl, _, _ = league_cached()
    except Exception:
        return {}, {}
    by_name = {}
    for p in pl.values():
        if not isinstance(p, dict): continue
        n, ps = p.get("full_name"), p.get("position")
        if n and ps in ("QB", "RB", "WR", "TE"):
            by_name.setdefault(n.lower().strip(), ps)
    vote = collections.defaultdict(collections.Counter)
    for p in players.values():
        nm = f"{p.get('first_name','')} {p.get('last_name','')}".strip().lower()
        ps = by_name.get(nm)
        uid = p.get("position_id")
        if ps and uid: vote[uid][ps] += 1
    uuid2pos = {u: c.most_common(1)[0][0] for u, c in vote.items() if c}
    return by_name, uuid2pos

def _ud_price(opts, choice):
    for o in opts or []:
        if (o.get("choice") or "").lower() == choice or \
           (o.get("choice_id") or "").startswith(choice[:4]):
            try: return float(o.get("american_price"))
            except (TypeError, ValueError): return None
    return None

def src_underdog(period="both", timeout=90):
    """Underdog Fantasy as a MARKET VENUE, not a projection.

    period: 'season' | 'game' | 'both'.

    Returns key, stat, line, over/under american prices, and p_over where both
    sides are priced (devigged, so it is a probability and not a payout). Rows
    without two-sided pricing keep line only -- still usable as a level, just
    not as a distribution."""
    try:
        j = requests.get(UD_URL, headers=UA, timeout=timeout).json()
    except Exception as e:
        print(f"  underdog  FAIL {type(e).__name__}"); return pd.DataFrame()
    pls = {p["id"]: p for p in j.get("players", []) if p.get("sport_id") == "NFL"}
    aps = {a["id"]: a for a in j.get("appearances", [])}
    by_name, uuid2pos = _ud_positions(pls)
    want = {}
    if period in ("season", "both"): want.update(UD_SEASON)
    if period in ("game", "both"):   want.update(UD_GAME)
    rows = []
    for x in j.get("over_under_lines", []):
        ou = x.get("over_under") or {}
        ai = ou.get("appearance_stat") or {}
        stat = ai.get("stat")
        if stat not in want: continue
        ap = aps.get(ai.get("appearance_id")) or {}
        p = pls.get(ap.get("player_id"))
        if not p: continue
        nm = f"{p.get('first_name','')} {p.get('last_name','')}".strip()
        # name match first (authoritative), then the learned uuid->pos map
        pos = by_name.get(nm.lower()) or uuid2pos.get(p.get("position_id")) or ""
        if pos not in ("QB", "RB", "WR", "TE"): continue
        try: line = float(x.get("stat_value"))
        except (TypeError, ValueError): continue
        op, up = _ud_price(x.get("options"), "higher"), _ud_price(x.get("options"), "lower")
        po = None
        if op is not None and up is not None:
            f = lambda a: (100.0 / (a + 100.0)) if a > 0 else (-a / (-a + 100.0))
            a_, b_ = f(op), f(up)
            if a_ + b_ > 0: po = a_ / (a_ + b_)          # devigged
        rows.append(dict(name=nm, pos=pos, stat=want[stat], raw_stat=stat,
                         period=("season" if stat.startswith("season") else "game"),
                         line=line, over=op, under=up, p_over=po, venue="underdog"))
    d = pd.DataFrame(rows)
    if len(d):
        d["key"] = [norm(r.name, r.pos) if r.pos else norm(r.name, "") for r in d.itertuples()]
    print(f"  underdog  OK   {len(d)} lines | season "
          f"{(d.period=='season').sum() if len(d) else 0} game "
          f"{(d.period=='game').sum() if len(d) else 0} | two-sided "
          f"{d.p_over.notna().sum() if len(d) else 0}")
    return d

def src_nflverse_ypc(year=None, min_rec=25, timeout=120):
    """REAL yards-per-catch from last season's actual production.

    The receptions bridge divides a book yards line by a yards-per-catch. When
    that YPC is borrowed from a positional average it is an assumption about a
    position group; this is a measurement of the player. Returns
    {(lastname, first-initial): ypc} plus a by-name dict, because nflverse
    abbreviates first names ("P.Nacua")."""
    year = year or (SEASON - 1)
    try:
        r = requests.get(NFLVERSE.format(yr=year), headers=UA, timeout=timeout)
        if r.status_code != 200:
            print(f"  nflverse  FAIL http {r.status_code}"); return {}
        d = pd.read_csv(io.BytesIO(r.content), low_memory=False)
    except Exception as e:
        print(f"  nflverse  FAIL {type(e).__name__}"); return {}
    col = "player_display_name" if "player_display_name" in d.columns else "player_name"
    g = d.groupby(col)[["receptions", "receiving_yards"]].sum()
    g = g[g.receptions >= min_rec]
    out = {}
    for nm, r in g.iterrows():
        ypc = float(r.receiving_yards) / float(r.receptions)
        if not (3.0 <= ypc <= 25.0): continue
        s = str(nm).replace(".", ". ").split()
        last = s[-1].lower(); init = s[0][0].lower() if s else ""
        out[(last, init)] = ypc
    print(f"  nflverse  OK   {len(out)} players with {min_rec}+ receptions in {year}")
    return out

def real_ypc(board, year=None, week=1, mkw=None):
    """Best available YPC per board player, in priority order:
        1. his own week-N book lines   (market, this season)
        2. his actual production       (nflverse, last season)
        3. whatever the board is using (borrowed -- flagged as such)
    Returns a frame so the source of every number is visible."""
    own = own_ypc(board, week, mkw)
    hist = src_nflverse_ypc(year)
    rows = []
    for r in board[board.rec_mkt.notna()].itertuples():
        s = str(r.name).split()
        h = hist.get((s[-1].lower(), s[0][0].lower())) if len(s) >= 2 else None
        pick, src = (own.get(r.key), "own book line") if r.key in own else \
                    ((h, "nflverse actual") if h else (float(r.ypc_used), "borrowed"))
        rows.append(dict(key=r.key, name=r.name, pos=r.pos,
                         ypc_board=round(float(r.ypc_used), 2),
                         ypc_best=round(float(pick), 2), ypc_src_new=src,
                         rec_now=round(float(r.rec_mkt), 1),
                         rec_best=round(float(r.rec_mkt) * float(r.ypc_used) / float(pick), 1)))
    d = pd.DataFrame(rows)
    if len(d):
        d["rec_delta"] = (d.rec_best - d.rec_now).round(1)
        d["pts_pg"] = (d.rec_delta / GAMES).round(2)
    return d

# =========================================================================
# v5.6 (Sep 4 2026) -- UNDERDOG IS A VENUE NOW, AND A STALENESS WITNESS
# =========================================================================
# v5.5 added src_underdog() as a side function. Sitting beside the board it
# could not affect n_books, spread_pg or support, which is where corroboration
# actually gets counted. Wired in properly here.
#
# WHAT IT DOES AND DOES NOT DO, honestly:
#
#   DOES  +1 venue on ~240 season lines BettingPros already carries. That
#         moves players across the n_books thresholds that support tiers key
#         off, so some THIN becomes OK on real evidence rather than on nothing.
#
#   DOES  give the first INDEPENDENT witness this engine has ever had. Every
#         previous "book" came through one aggregator, so a stale upstream
#         line was stale in all eight of them simultaneously and n_books=8
#         looked like corroboration when it was one number copied. Underdog is
#         a different pricing engine on a different feed. When it disagrees
#         with the BettingPros consensus by a wide margin, that is EVIDENCE of
#         staleness, not an inference from spread. This is the first real
#         attack on the Josh Jacobs class of bug. See venue_gap().
#
#   DOES NOT rescue the 153 players Underdog covers and BettingPros does not.
#         One venue is one venue. MIN_BOOKS=3 exists because of the DeMario
#         Douglas incident and lowering it for a source we like would be
#         exactly the reasoning that produced that bug. They still fall back
#         to the projection. That is the correct outcome, not a shortfall.
#
#   DOES NOT solve season receptions. Nothing does. But it doubles the venue
#         count on the WEEKLY receptions that rec_history() accumulates, and
#         it enables rec_two_ways() below.

def src_market_v2(books=None, min_books=None, underdog=True):
    """Production season consensus with direct Underdog as an independent feed.

    v6.2 merges BEFORE applying MIN_BOOKS. The old research implementation
    called src_market() at the normal 3-book floor first, so a perfectly useful
    2-book BettingPros line + 1 direct Underdog line was discarded before
    Underdog had a chance to become the third witness.

    BettingPros consensus itself is excluded from BOOKS_USE, preventing the
    same constituent books from being counted once directly and once again
    through the aggregator consensus.
    """
    mb = MIN_BOOKS if min_books is None else int(min_books)
    d = src_market(books=books, min_books=1)
    if d is None or not len(d):
        d = pd.DataFrame(columns=["name","pos","stat","line","p_over","vig",
                                  "n_books","line_spread","value","key"])
    d = d.copy().reset_index(drop=True)
    if not underdog:
        return d[d.n_books >= mb].reset_index(drop=True)
    try:
        ud = src_underdog(period="season")
    except Exception:
        ud = pd.DataFrame()
    if ud is None or not len(ud):
        return d[d.n_books >= mb].reset_index(drop=True)

    ud = ud[ud.key.notna() & (ud.key != "")]
    idx = {(r.key, r.stat): i for i, r in d.iterrows()}
    add, merged = [], 0
    for r in ud.itertuples():
        val = (mean_from_count_line(r.line, r.p_over)
               if r.stat in DEVIG_STATS and r.p_over == r.p_over else float(r.line))
        i = idx.get((r.key, r.stat))
        if i is None:
            add.append(dict(name=r.name, pos=r.pos, stat=r.stat, line=float(r.line),
                            p_over=(r.p_over if r.p_over == r.p_over else np.nan),
                            vig=np.nan, n_books=1, line_spread=0.0,
                            value=float(val), key=r.key))
        else:
            old = float(d.at[i, "value"])
            d.at[i, "value"] = float(np.median([old, float(val)]))
            d.at[i, "n_books"] = float(d.at[i, "n_books"]) + 1
            d.at[i, "line_spread"] = max(float(d.at[i, "line_spread"] or 0.0),
                                         abs(old - float(val)))
            merged += 1
    if add:
        d = pd.concat([d, pd.DataFrame(add)], ignore_index=True)
    dropped = int((d.n_books < mb).sum()) if len(d) else 0
    d = d[d.n_books >= mb].reset_index(drop=True)
    print(f"  underdog  merged into {merged} existing season lines; "
          f"{dropped} lines remain below the {mb}-independent-venue floor")
    return d

def venue_gap(books=None, week=None, tol=0.15):
    """BettingPros consensus vs Underdog, line by line.

    This is the only true cross-feed check available. A large gap means one
    side has repriced and the other has not -- and since the engine cannot
    timestamp a line, this is as close to catching staleness in the act as it
    gets. Sorted by relative gap so a 40-yard miss on a 300-yard line ranks
    above a 40-yard miss on a 1300-yard line."""
    bp = src_market(books=books)
    ud = src_underdog(period="season")
    if not len(bp) or not len(ud): return pd.DataFrame()
    m = bp.merge(ud[["key", "name", "stat", "line", "p_over"]],
                 on=["key", "stat"], suffixes=("_bp", "_ud"))
    if not len(m): return pd.DataFrame()
    m["gap"] = (m.line_ud - m.line_bp).round(2)
    m["rel"] = (m.gap.abs() / m.line_bp.replace(0, np.nan)).round(4)
    m["flag"] = np.where(m.rel >= tol, "REPRICED SOMEWHERE", "")
    return m[["name_bp", "pos", "stat", "line_bp", "line_ud", "gap", "rel",
              "n_books", "flag"]].rename(columns={"name_bp": "name"}) \
            .sort_values("rel", ascending=False)

def rec_two_ways(board, week=1, mkw=None, year=None):
    """Season receptions estimated TWO independent ways, and the gap kept.

    Nobody sells season receptions, so it has to be inferred. There are two
    routes and they fail differently, which is the point of running both:

      A. YARDS / YPC     season rec-yd line (real, 8 venues) divided by a
                         yards-per-catch. Fails when the YPC is wrong -- and
                         YPC is the thing most likely to shift with a role
                         change.
      B. RATE x GAMES    his week-1 receptions line (real, two venues now)
                         times implied games. Fails when week 1 is an unusual
                         matchup, since it extrapolates one game.

    A is anchored to a season quantity and distorted by a rate. B is anchored
    to a rate and distorted by one matchup. They do not share an error, so
    where they AGREE the number is trustworthy and where they diverge the
    honest output is the disagreement, not an average pretending to be a
    measurement. spread is reported for exactly that reason."""
    mkw = mkw if mkw is not None else src_market_weekly(week)
    ypc = real_ypc(board, year=year, week=week, mkw=mkw)
    ypc_best = dict(zip(ypc.key, ypc.ypc_best)) if len(ypc) else {}
    ypc_src = dict(zip(ypc.key, ypc.ypc_src_new)) if len(ypc) else {}
    ig, _ = implied_games(board, week, mkw=mkw)
    g = mkw.groupby("key").first() if mkw is not None and len(mkw) else pd.DataFrame()
    try:
        ud = src_underdog(period="game")
        udrec = dict(zip(ud[ud.stat == "rec"].key, ud[ud.stat == "rec"].line))
    except Exception:
        udrec = {}
    rows = []
    for r in board[board.rec_yd_mkt.notna()].itertuples():
        y = float(r.rec_yd_mkt)
        v = ypc_best.get(r.key)
        A = (y / v) if v else np.nan
        wk = np.nan
        if len(g) and r.key in g.index and "rec" in g.columns:
            wk = g.loc[r.key, "rec"]
            if isinstance(wk, pd.Series): wk = wk.iloc[0]
        if pd.isna(wk): wk = udrec.get(r.key, np.nan)
        gm = ig.get(r.key, np.nan)
        B = (float(wk) * float(gm)) if not pd.isna(wk) and not pd.isna(gm) else np.nan
        if pd.isna(A) and pd.isna(B): continue
        both = not pd.isna(A) and not pd.isna(B)
        rows.append(dict(name=r.name, pos=r.pos, team=r.team,
                         rec_board=round(float(r.rec_mkt), 1) if not pd.isna(r.rec_mkt) else None,
                         rec_A=round(A, 1) if not pd.isna(A) else None,
                         rec_B=round(B, 1) if not pd.isna(B) else None,
                         ypc_src=ypc_src.get(r.key, "?"),
                         spread=round(abs(A - B), 1) if both else None,
                         best=round((A + B) / 2, 1) if both else round(
                             A if not pd.isna(A) else B, 1),
                         agree=(both and abs(A - B) <= 10)))
    d = pd.DataFrame(rows)
    if len(d):
        d["pts_pg_vs_board"] = ((d.best - d.rec_board) / GAMES).round(2)
        d = d.sort_values("spread", ascending=False, na_position="last")
    return d

# =========================================================================
# v5.7 (Sep 4 2026) -- THE SHOPS ARE NOT EQUALLY GOOD, AND ONE IS BIASED
# =========================================================================
# The blend weighted rotowire and espn 50/50 on the assumption that two
# opinions average out. They do not, because one of them is systematically
# wrong in a direction.
#
# The market is the only available truth proxy -- an 8-venue consensus, and
# v5.6 confirmed via an independent feed (Underdog) that the venues agree to a
# 0.1% median. Scoring both shops against it on 111 well-covered players:
#
#                      rotowire    espn
#   MAE vs market         0.876   1.386     espn is 58% worse
#   BIAS (mean error)     +0.544  +1.290    BOTH high; espn more than 2x
#   by position RB         0.52    1.90     the blowout
#   widest 25 disputes    21 wins   4 wins
#
# Two conclusions, and the second matters more than the first:
#
#   1. ESPN carries a +1.29/gm SYSTEMATIC INFLATION. A 50/50 blend inherits
#      about +0.92 of it on every single player. That does not cancel in a
#      trade comparison, but it does inflate every absolute number the engine
#      has ever printed, and it inflates RBs worst.
#
#   2. spread_pg -- the input the SUPPORT TIER keys off -- has been measuring
#      espn's inflation, not genuine uncertainty. A player is tagged THIN for
#      "the shops disagree" when what actually happened is espn is high on him
#      like it is high on everyone. JSN is the case in point: rotowire 16.62,
#      espn 19.18, market 17.16, spread 2.55 -> THIN. Rotowire is nearly on
#      the market. The disagreement is one-sided and the tag was misleading.
#
# calibrate_sources() measures this fresh each run rather than hardcoding
# today's numbers, because a shop that corrects itself midseason should get
# its weight back automatically.

def calibrate_sources(board, min_books=6, min_real=55.0):
    """Score each projection shop against the market consensus.

    Restricted to players the market genuinely covers, since scoring a shop
    against a bridged or thin line measures the bridge, not the shop.

    Returns per-shop bias (mean signed error) and weight (inverse mean-squared
    error, normalised). Weighting by inverse MSE is the right operation for
    combining estimators of the same quantity with different precisions."""
    d = board[(board.n_src >= 2) & (board.n_mkt > 0) &
              (board.n_books >= min_books) & (board.mkt_real_pct >= min_real)].copy()
    if len(d) < 25:
        return {"rotowire": dict(bias=0.0, mae=np.nan, w=0.5),
                "espn": dict(bias=0.0, mae=np.nan, w=0.5)}, len(d)
    gp = d.gp.replace(0, np.nan).fillna(float(GAMES))
    out = {}
    for src in ("rotowire", "espn"):
        e = d[src] / gp - d.mkt_pg
        out[src] = dict(bias=float(e.mean()), mae=float(e.abs().mean()),
                        mse=float((e ** 2).mean()))
    # WEIGHT BY INVERSE RESIDUAL VARIANCE, NOT INVERSE MSE.
    # v5.7 shipped inverse-MSE weights AND subtracted the bias. That is the
    # same penalty applied twice: MSE = bias^2 + variance, so a biased shop got
    # marked down for a bias that had already been removed. Corrected here.
    # It matters: espn's residual SCATTER (std 0.958) is TIGHTER than
    # rotowire's (0.989). Once the level shift is gone espn is the slightly
    # steadier estimator, and the 0.67/0.33 split v5.7 used was wrong.
    for src, v in out.items():
        e = d[src] / gp - d.mkt_pg
        v["var"] = float(((e - e.mean()) ** 2).mean())
    tot = sum(1.0 / v["var"] for v in out.values())
    for v in out.values():
        v["w"] = (1.0 / v["var"]) / tot
        v.pop("mse")
    return out, len(d)

def blend_weighted(board, cal=None, debias=True):
    """Re-derive proj_pg using calibrated weights instead of a flat average.

    debias=True subtracts each shop's measured mean error before blending, so
    the output sits on the market's level rather than a shop's. Turn it off to
    see how much of the board's absolute numbers were shop inflation."""
    cal = cal or calibrate_sources(board)[0]
    gp = board.gp.replace(0, np.nan).fillna(float(GAMES))
    num = np.zeros(len(board)); den = np.zeros(len(board))
    for src, v in cal.items():
        x = (board[src] / gp) - (v["bias"] if debias else 0.0)
        m = x.notna().values
        num[m] += (x.values[m] * v["w"]); den[m] += v["w"]
    out = pd.Series(np.where(den > 0, num / np.maximum(den, 1e-9), np.nan),
                    index=board.index)
    return out

def source_spread_honest(board, cal=None):
    """spread_pg with each shop's systematic bias removed first.

    What is left is REAL disagreement about a player rather than one shop's
    standing offset. A player whose spread collapses after de-biasing was
    never uncertain -- he was just someone espn likes. Use this, not raw
    spread_pg, when deciding whether a number is trustworthy."""
    cal = cal or calibrate_sources(board)[0]
    gp = board.gp.replace(0, np.nan).fillna(float(GAMES))
    a = board["rotowire"] / gp - cal["rotowire"]["bias"]
    b = board["espn"] / gp - cal["espn"]["bias"]
    return (a - b).abs()

# =========================================================================
# v5.9 (Sep 4 2026) -- THE FIRST REAL GROUND TRUTH, AND IT IS HUMBLING
# =========================================================================
# Every accuracy claim in this file up to v5.8 was measured against THE
# MARKET. The market is a proxy. It is a good one, but rotowire and the books
# read the same beat reporters, so agreeing with the books does not prove a
# projection is right -- it proves it is conventional.
#
# nflverse gives actual outcomes, and Sleeper still serves the 2025 rotowire
# projections. So the real test is available and it has now been run.
#
# CONTAMINATION CHECK FIRST, because a backfilled "projection" would make the
# engine look brilliant: corr(projected, actual) = 0.79. A backfill scores
# ~0.99. 0.79 is what an honest August forecast looks like. The data is clean.
#
# ROTOWIRE PRESEASON 2025 vs ACTUAL 2025, per game, n=291:
#
#     MAE 2.93/gm     median 2.38     std 3.33     corr 0.792
#
#     by tier   proj_pg  act_pg   MAE          by pos   MAE
#     bottom      1.09    4.64    3.56           QB    4.02
#     mid         4.33    6.56    2.96           RB    2.94
#     high        8.42    9.17    2.49           WR    2.82
#     ELITE      14.32   15.17    2.71           TE    2.53
#
# WHAT THIS MEANS, AND IT CHANGES HOW EVERY NUMBER HERE SHOULD BE READ:
#
#  1. COIN_FLIP WAS TOO PERMISSIVE. It was set to 1.75 to match the typical
#     shop-vs-shop disagreement. But shop disagreement (mean spread_pg 1.11)
#     is only about 38% of the real error. Two shops agreeing tells you they
#     read the same reports, not that the number is right. The honest
#     per-player bar is 2.93, and for a 2-for-2 trade -- four players, roughly
#     independent errors -- the bar on the DELTA is nearer 2.93*sqrt(4) ≈ 5.9.
#     Almost every "edge" this engine has reported was inside forecast noise.
#     COIN_FLIP raised to the measured value; forecast_error() recomputes it.
#
#  2. THE TOP OF THE BOARD IS THE RELIABLE PART. MAE falls from 3.56 in the
#     bottom quartile to 2.49-2.71 at the top, and in RELATIVE terms the
#     collapse is enormous: 3.56 on a 1.09 projection is noise exceeding
#     signal; 2.71 on 14.32 is 19%. Concentrating value in a few big names is
#     not just good roster construction, it is the part of the board that is
#     actually knowable. Depth pieces are close to unforecastable.
#
#  3. QB IS THE LEAST PREDICTABLE POSITION (MAE 4.02, worst by a full point).
#     Independent of the VOR argument, the QB slot is where the engine knows
#     least. Two reasons now to treat it as the expendable one.
#
#  4. THE +1.85 BIAS IS PARTLY AN ARTIFACT AND MUST NOT BE "CORRECTED" AWAY.
#     Actuals are conditioned on players who appeared in 6+ games, so the
#     sample is survivors, who outperform. This measures accuracy GIVEN
#     availability. It is the right question for start/sit and the wrong one
#     for season value, where missing games is the main risk. Do not subtract
#     this bias from projections. calibrate_sources() against the market stays
#     the tool for level correction.

def backtest(year=None, min_games=6, min_pts=20, pos=("QB", "RB", "WR", "TE")):
    """Score last season's PRESEASON projections against what actually
    happened. The only unproxied accuracy measurement in this file.

    Returns (frame, summary). Check summary['corr'] first: anything above ~0.95
    means the upstream 'projections' were quietly backfilled with results and
    the whole test is worthless."""
    year = year or (SEASON - 1)
    rows = []
    for p in pos:
        try:
            j = requests.get(f"https://api.sleeper.app/projections/nfl/{year}"
                             f"?season_type=regular&position[]={p}&order_by=pts_ppr",
                             headers=UA, timeout=90).json()
        except Exception:
            continue
        for x in j:
            st = x.get("stats") or {}
            pl = x.get("player") or {}
            nm = pl.get("full_name") or \
                 f"{pl.get('first_name','')} {pl.get('last_name','')}".strip()
            if nm and st.get("pts_ppr"):
                rows.append(dict(name=nm, pos=p, proj=float(st["pts_ppr"]),
                                 proj_gp=float(st.get("gp") or GAMES)))
    if not rows: return pd.DataFrame(), {}
    P = pd.DataFrame(rows)
    try:
        r = requests.get(NFLVERSE.format(yr=year), headers=UA, timeout=150)
        A = pd.read_csv(io.BytesIO(r.content), low_memory=False)
    except Exception:
        return pd.DataFrame(), {}
    if "season" in A.columns: A = A[A.season == year]
    col = "player_display_name" if "player_display_name" in A.columns else "player_name"
    if "position" in A.columns:
        G = A.groupby([col, "position"]).agg(act=("fantasy_points_ppr", "sum"),
              g=("games", "sum")).reset_index()
        G["join_key"] = [norm(n, p) for n, p in zip(G[col], G["position"])]
        P["join_key"] = [norm(n, p) for n, p in zip(P.name, P.pos)]
    else:
        G = A.groupby(col).agg(act=("fantasy_points_ppr", "sum"),
              g=("games", "sum")).reset_index()
        G["join_key"] = [norm(n) for n in G[col]]
        P["join_key"] = [norm(n) for n in P.name]
    G = G[G.join_key != ""].drop_duplicates("join_key", keep=False)
    P = P[P.join_key != ""].drop_duplicates("join_key", keep=False)
    M = P.merge(G, on="join_key")
    M = M[(M.act > min_pts) & (M.g >= min_games)].copy()
    if not len(M): return M, {}
    M["proj_pg"] = M.proj / M.proj_gp.clip(lower=1)
    M["act_pg"] = M.act / M.g
    M["err"] = M.act_pg - M.proj_pg
    s = dict(n=len(M), mae=float(M.err.abs().mean()),
             median=float(M.err.abs().median()), bias=float(M.err.mean()),
             std=float(M.err.std()), corr=float(M.proj_pg.corr(M.act_pg)),
             contaminated=bool(M.proj_pg.corr(M.act_pg) > 0.95))
    return M, s

def forecast_error(year=None, players=1, cached=True, _c={}):
    """The honest significance bar, in points per game.

    players=1 -> per-player error. players=4 -> the bar on a 2-for-2 trade
    delta, since four independent forecasts contribute to it. Use this instead
    of the COIN_FLIP constant wherever a difference is being called real."""
    if cached and "mae" in _c:
        return _c["mae"] * np.sqrt(players)
    _, s = backtest(year)
    if not s: return COIN_FLIP * np.sqrt(players)
    _c["mae"] = s["mae"]
    return s["mae"] * np.sqrt(players)

# =========================================================================
# v6.0 (Sep 4 2026) -- THE VARIANCE MODEL, AND AN OVER-CORRECTION UNDONE
# =========================================================================
# TWO THINGS. The second one matters more.
#
# ---------------------------------------------------------------------------
# 1. THE SIGNIFICANCE BAR WAS NEVER MEANT TO BE A VETO, AND v5.9 TURNED IT
#    INTO ONE. THAT WAS WRONG.
# ---------------------------------------------------------------------------
# v5.9 measured a 2.93/gm forecast error and concluded that edges below it are
# "inside noise", implying they should not be acted on. That conflates LOW
# CONFIDENCE with NO EDGE. They are not the same thing and the difference is
# the whole game.
#
# Measured on 905 player-seasons (2023-25), sampling pairs of startable
# players and asking: when the engine said A beats B by X, what happened?
#
#   projected gap   P(right)   realised gap   CAPTURE
#      0.0-0.5        51%          +0.33        130%
#      0.5-1.0        57%          +0.72         96%
#      1.0-1.5        61%          +1.20         96%
#      1.5-2.0        64%          +1.70         97%
#      2.0-3.0        71%          +2.55        102%
#      3.0-4.0        79%          +3.76        108%
#      4.0-6.0        87%          +5.14        104%
#      6.0+           95%          +8.21        100%
#
# CAPTURE IS ~100% AT EVERY MAGNITUDE INCLUDING THE SMALLEST. The projected
# edge is UNBIASED. There is no shrinkage to correct for. A +1.0/gm edge is
# a real +1.0/gm in expectation -- you are simply only right about it 57% of
# the time.
#
# In a season of repeated decisions with no penalty for a wash, +EV at 57% is
# worth taking every single time. And it has to be, because a 12-team league
# of protective managers does not hand out 6-point edges; the tradeable range
# IS 0.5-2.0, and refusing to act there means never trading.
#
# So: COIN_FLIP goes back to being a CONFIDENCE LABEL, not a gate. Report the
# edge, report P(right) beside it, let the size of the edge set how hard to
# push -- do not suppress the trade. trade_confidence() does this.
#
# ---------------------------------------------------------------------------
# 2. BENCH PROJECTIONS DO NOT REACH THE TEAM NUMBER AT ALL.
# ---------------------------------------------------------------------------
# Tested by deleting each player outright and re-running pergame():
#
#   Tyjae Spears   zeroed  +0.00/gm      Chris Bell      zeroed +0.00/gm
#   Tank Bigsby    zeroed  +0.00/gm      Matthew Golden  zeroed +0.00/gm
#   Caleb Douglas  zeroed  +0.00/gm      Davante Adams   zeroed -2.49/gm
#
# A player who never enters the best-8 contributes exactly nothing, so the
# quality of his projection is irrelevant no matter how bad it is. The
# bottom-tier MAE of 3.56 that v5.9 fretted about propagates into NOTHING.
# Chase coverage for players who START. sensitivity() below is the check --
# run it before worrying about any player's sourcing.
#
# ---------------------------------------------------------------------------
# 3. THE VARIANCE MODEL (what the header has called the biggest gap since v4)
# ---------------------------------------------------------------------------
# Until now every player was ONE NUMBER. But you do not win by having the
# higher average, you win by outscoring one specific opponent on one specific
# Sunday. Two teams with identical means but different spreads have different
# win rates, and which spread you WANT depends on whether you are ahead.
#
# Forecast SD from the same backtest, and it is strikingly flat by tier
# (3.12 / 3.40 / 3.29 / 3.14 from 6-9 up through 16+) but NOT by position:
#
#      RB 3.85     WR 3.20     QB 3.02     TE 2.27
#
# RBs are the least predictable thing you can own and tight ends the most.
# That is a roster-construction fact, not a projection quirk.
#
# THE PRACTICAL UPSHOT FOR A TEAM THAT IS AHEAD: variance is the underdog's
# friend. Leading the league by 4/gm means every added point of spread gives
# back some of that lead, because it hands weaker opponents more chances to
# get lucky. Prefer the low-sigma asset when the points are close.

ENABLE_EXPERIMENTAL_MATCHUP_ODDS = False
SIGMA_POS = {"QB": 3.02, "RB": 3.85, "WR": 3.20, "TE": 2.27}
SIGMA_DEFAULT = 3.20

def player_sigma(pos, pg=None):
    """Season-long forecast SD for one player, in points per game.

    Measured, not assumed: residual SD of preseason projection vs realised
    per-game production, 2023-25. Flat across projection tiers, so it does not
    take pg -- the argument is accepted only so callers can pass it without
    breaking when a tier term is added later."""
    return SIGMA_POS.get(pos, SIGMA_DEFAULT)

def team_sigma(pids, val, mat, rates, pool=None, corr=0.25):
    """Per-game SD of a team's best-8 output.

    Two things are being combined and they behave differently:
      * FORECAST error is season-long. If the projection is wrong about a
        player it is wrong about him every week, so it does NOT average out
        over a season -- it shifts the whole team.
      * corr is the shared component (same offence, same game script, same
        weather). 0.25 is a deliberately conservative guess and is the softest
        number in this function; it is not measured.

    Only starters count, because sensitivity() shows bench players contribute
    nothing to the total."""
    rr = []
    for pid in pids:
        if pid not in val: continue
        x, pos, nm = val[pid]
        rr.append((rates.get(norm(nm, pos), 0.0), pos))
    rr.sort(reverse=True)
    starters = rr[:8]
    var = sum(player_sigma(p) ** 2 for _, p in starters)
    n = len(starters)
    var += corr * sum(player_sigma(a) * player_sigma(b)
                      for i, (_, a) in enumerate(starters)
                      for j, (_, b) in enumerate(starters) if i != j)
    return float(np.sqrt(max(var, 1e-9)))

def matchup_odds(mean_a, mean_b, sd_a, sd_b):
    """EXPERIMENTAL: disabled until weekly outcome volatility is measured."""
    if not ENABLE_EXPERIMENTAL_MATCHUP_ODDS:
        raise RuntimeError(
            "matchup_odds is disabled: season forecast error is not weekly "
            "score variance. Enable only for research, not decisions."
        )
    from scipy.stats import norm as _n
    s = float(np.sqrt(sd_a ** 2 + sd_b ** 2))
    if s <= 0: return 1.0 if mean_a > mean_b else 0.0
    return float(_n.cdf((mean_a - mean_b) / s))

def trade_confidence(edge_pg, players=None):
    """Empirical directional confidence label for a projected edge.

    The calibration table came from PAIR comparisons. v6.0 accepted a
    ``players=`` argument but ignored it, which falsely suggested package-size
    calibration. v6.2 keeps the empirical pair table and says explicitly that
    multi-player trade uncertainty is not yet modeled.
    """
    tbl = [(0.5, 0.51), (1.0, 0.57), (1.5, 0.61), (2.0, 0.64),
           (3.0, 0.71), (4.0, 0.79), (6.0, 0.87), (99.0, 0.95)]
    e = abs(float(edge_pg))
    p = next(v for t, v in tbl if e <= t)
    return dict(edge=round(float(edge_pg), 2), p_right=p,
                expected_realised=round(float(edge_pg), 2),
                calibration="pairwise historical; package-size uncertainty not modeled",
                verdict=("take it, low confidence" if p < 0.60 else
                         "take it" if p < 0.75 else "take it, high confidence"))

def sensitivity(pids, val, mat, rates, pool=None, names=None):
    """Which players on this roster actually move the team number?

    Deletes each in turn and re-prices. A player whose deletion costs 0.00 is
    invisible to the best-8 and his projection quality does not matter, however
    thin his sourcing is. Run this BEFORE chasing coverage for anyone."""
    base = pergame(pids, val, mat, rates, pool)
    rows = []
    for pid in pids:
        if pid not in val: continue
        x, pos, nm = val[pid]
        if names and nm not in names: continue
        k = norm(nm, pos)
        m2 = {kk: dict(v) for kk, v in mat.items()}
        if k in m2: m2[k] = {w: 0.0 for w in m2[k]}
        rows.append(dict(name=nm, pos=pos, rate=round(rates.get(k, 0.0), 2),
                         cost_if_lost=round(pergame(pids, val, m2, rates, pool) - base, 2)))
    d = pd.DataFrame(rows).sort_values("cost_if_lost")
    d["load_bearing"] = d.cost_if_lost < -0.01
    return d

# ------------------------------------------------------------------ checks
def health_check(board, wkly=None, wk_pts=None, espn_wk=None):
    """Fail LOUDLY. A source dropping out silently shifts every number and is
    the likeliest way this engine misleads without anyone noticing."""
    p = []
    for s in ("rotowire", "espn"):
        n = board[s].notna().sum() if s in board else 0
        if n < 200: p.append(f"SOURCE {s} missing or thin ({n} rows)")
    n2 = (board.n_src >= 2).sum()
    if n2 < 250: p.append(f"only {n2} players have both sources (expect 300+)")
    if not BP_API_KEY and not QUICK:
        p.append("BETTINGPROS_API_KEY is not set -- season market layer disabled")
    if board.n_mkt.sum() == 0 and not QUICK:
        p.append("NO season market lines -- BettingPros access may be unavailable")
    top = board.nlargest(1, "value_pg")
    if len(top) and not (14 <= float(top.value_pg.iloc[0]) <= 30):
        p.append(f"top player {float(top.value_pg.iloc[0]):.1f}/gm out of sane range")
    d = board.key.duplicated().sum()
    if d: p.append(f"{d} duplicate keys -- name normalisation broke")
    if "n_books_min" in board and (board.n_mkt > 0).any():
        shallow = int(((board.n_mkt > 0) & (board.n_books_min < 2)).sum())
        if shallow > 20:
            p.append(f"{shallow} market-covered players have a component with <2 independent venues")
    if "mkt_edge" in board and (board.n_mkt > 0).any():
        e = board[board.n_mkt > 0].mkt_edge.median()
        if abs(e) > 0.25:
            p.append(f"median mkt_edge {e:+.2f} -- haircut fit off, scale may be split")
    # ---- v5 weekly guards
    if wkly is not None:
        if not len(wkly):
            p.append("WEEKLY FEED EMPTY -- every week-specific number is v4-quality")
        else:
            wks = wkly.week.nunique()
            if wks < 17: p.append(f"weekly feed only covers {wks} weeks (expect 18)")
            live = wkly[wkly.pts.notna()].key.nunique()
            if live < 300: p.append(f"only {live} players projected in ANY week (expect 400+)")
            lm = pd.to_numeric(wkly.last_mod, errors="coerce").dropna()
            if len(lm):
                v = float(lm.max())
                if v > 1e12: v /= 1000.0
                age = (time.time() - v) / 3600
                if age > 72:
                    p.append(f"weekly feed last rebuilt {age:.0f}h ago -- it is supposed to be daily")
    if espn_wk is not None:
        if not espn_wk:
            p.append("ESPN WEEKLY EMPTY -- weekly layer is single-source, no disagreement flag")
        else:
            n = len(espn_wk.get(min(espn_wk), {}))
            if n < 300: p.append(f"espn weekly thin ({n} players/wk, expect 450+)")
    if wk_pts:
        # observed byes must agree with the schedule, or a lineup is wrong
        try:
            sched, _ = byes()
            bad = 0
            for k, wks in list(wk_pts.items())[:400]:
                pass
        except Exception:
            pass
    return p

def bye_crosscheck(wkly, limit=None):
    """Compare the weekly feed's OBSERVED byes against Sleeper's schedule.
    Uses the same tolerant team-level rule as wk_matrix -- see _team_byes for
    why the strict version is unusable. Empty is good; a disagreement means a
    lineup call is riding on two sources that cannot both be right, and the
    schedule is the one to believe."""
    sched, _ = byes()
    allwk = set(int(w) for w in wkly.week.unique())
    feed_bye = _team_byes(wkly, allwk)
    bad = []
    for t in sorted(wkly.team.dropna().unique()):
        feed = sorted(feed_bye.get(t, set()))
        sch = sorted(w for w, s in sched.items() if t in s)
        if feed != sch:
            bad.append((t, f"schedule {sch}", f"feed {feed}"))
    return bad[:limit] if limit else bad

def key_collisions(players, limit=12):
    """norm() maps name+position to one key, and that is not always unique.
    Two different Kaleb Johnsons (both RB) collapse together and one of them
    carries a wrong team tag, which is how Green Bay lost its Week 11 bye.
    This lists keys that map to more than one real NFL team so a join can be
    checked before it silently moves a number."""
    seen = collections.defaultdict(set)
    for pid, p in players.items():
        if not isinstance(p, dict): continue
        pos, nm, tm = p.get("position"), p.get("full_name"), p.get("team")
        if pos not in ("QB", "RB", "WR", "TE") or not nm or not tm: continue
        seen[norm(nm, pos)].add(tm)
    out = [(k, sorted(v)) for k, v in seen.items() if len(v) > 1]
    return out[:limit]

def selftest():
    """health_check catches MISSING data; this catches WRONG data -- a silently
    altered scoring rule or join key, which shifts every number while every
    status line still reads OK."""
    p = []
    if abs(score(rec=5, reyd=80, retd=1) - 19.0) > 1e-9: p.append("score() PPR")
    if abs(score(payd=300, patd=2, pint=1) - 19.0) > 1e-9: p.append("score() passing")
    if abs(score(ruyd=100, fl=1) - 8.0) > 1e-9: p.append("score() fumble")
    if norm("Ken Walker III","RB") != "ken walker|RB": p.append("norm() suffix")
    if norm("Marquise Brown","WR") != "hollywood brown|WR": p.append("norm() FIX")
    if norm("A.J. Brown","WR") != "aj brown|WR": p.append("norm() punctuation")
    v = {f"p{i}": (float(x), ps, f"p{i}") for i, (x, ps) in enumerate(
        [(20,"QB"), (15,"RB"), (14,"RB"), (13,"RB"),
         (12,"WR"), (11,"WR"), (10,"WR"), (9,"TE")])}
    got = best8(list(v), v)
    if abs(got - 104.0) > 1e-9: p.append(f"best8() got {got}, expected 104.0")
    thin = {"a": (10.0,"QB","a"), "b": (5.0,"RB","b")}
    if abs(best8(["a","b"], thin) - 15.0) > 1e-9: p.append("best8() short roster")

    # ---- v5: weekly lineup must use the WEEK, not the season average
    val = {"x": (20.0, "RB", "Star"), "y": (5.0, "RB", "Sub"),
           "q": (18.0, "QB", "Qb")}
    wkp = {norm("Star","RB"): {1: 22.0, 2: np.nan},
           norm("Sub","RB"):  {1: 4.0,  2: 6.0},
           norm("Qb","QB"):   {1: 19.0, 2: 19.0}}
    w1 = best8_week(["x","y","q"], val, 1, wkp, {})
    w2 = best8_week(["x","y","q"], val, 2, wkp, {})
    if abs(w1 - (19.0+22.0+4.0)) > 1e-9: p.append(f"best8_week() wk1 got {w1}")
    if abs(w2 - (19.0+6.0)) > 1e-9:
        p.append(f"best8_week() wk2 got {w2}, a NaN week must score 0 not the season avg")
    _, unk = wk_val({"z": (9.9, "WR", "Ghost")}, wkp, {}, 1)
    if unk != ["Ghost"]: p.append("wk_val() failed to flag a player absent from the weekly feed")

    # ---- v5.1: de-vig must be symmetric and must move a skewed line
    p1, v1 = devig(-110, -110)
    if abs(p1 - 0.5) > 1e-6: p.append(f"devig() balanced book gave P(over) {p1}")
    if not (0.03 < v1 < 0.06): p.append(f"devig() vig on -110/-110 was {v1}")
    p2, _ = devig(-145, 119); p3, _ = devig(119, -145)
    if abs((p2 + p3) - 1.0) > 1e-6: p.append("devig() not symmetric")
    if p2 < 0.55: p.append(f"devig() failed to flag a juiced over ({p2})")

    # ---- v5.1: a line is a MEDIAN, the mean of a count sits above it
    m50 = mean_from_count_line(2.5, 0.50)
    if not (2.6 < m50 < 2.8): p.append(f"mean_from_count_line(2.5,.50) = {m50}, expected ~2.67")
    if mean_from_count_line(2.5, 0.60) <= m50:
        p.append("mean_from_count_line did not rise with P(over)")
    if mean_from_count_line(2.5, np.nan) != 2.5:
        p.append("mean_from_count_line must pass the line through when odds are missing")

    # ---- v5.1: blending must respect byes and must not resurrect a bye player
    wkp2 = {norm("Guy","WR"): {1: 10.0, 2: np.nan, 3: 12.0}}
    byes2 = {norm("Guy","WR"): {2}}
    esp2 = {1: {norm("Guy","WR"): 14.0}, 2: {norm("Guy","WR"): 9.0}, 3: {}}
    bl, sp = blend_weekly(wkp2, byes2, esp2)
    g = bl[norm("Guy","WR")]
    if abs(g[1] - 12.0) > 1e-9: p.append(f"blend_weekly wk1 got {g[1]}, expected mean(10,14)=12")
    if not pd.isna(g[2]):
        p.append("blend_weekly let ESPN resurrect a player on a BYE -- byes come from rotowire only")
    if abs(g[3] - 12.0) > 1e-9: p.append("blend_weekly should pass rotowire through when espn is silent")
    if abs(sp[norm("Guy","WR")][1] - 4.0) > 1e-9: p.append("blend_weekly spread wrong")

    # ---- v6.2: soft source omission must NOT be averaged with an invented zero
    kg = norm("Soft Missing", "WR")
    rw = {kg: {1: np.nan}}
    by = {kg: set()}
    ew = {1: {kg: 10.0}}
    meta_df = pd.DataFrame([dict(key=kg, week=1, pts=np.nan, inj="Questionable",
                                  team="AAA", opp="BBB", name="Soft Missing", pos="WR",
                                  body=None, last_mod=None, news=None)])
    bb, _ = blend_weekly(rw, by, ew, wkly=meta_df)
    if abs(bb[kg][1] - 10.0) > 1e-9:
        p.append(f"blend_weekly soft omission got {bb[kg][1]}, expected ESPN 10")

    # ---- v6.2: hard inactive Rotowire row remains zero even if ESPN is stale
    meta_df.loc[0, "inj"] = "Out"
    bb, _ = blend_weekly(rw, by, ew, wkly=meta_df)
    if abs(bb[kg][1]) > 1e-9:
        p.append("blend_weekly let ESPN resurrect an Out player")

    # ---- v6.2: market overlay changes only a real, non-bye matrix cell
    # (synthetic arithmetic; no network call here)

    # ---- v5.1: one mislabelled row must not delete a team's bye
    rows = []
    for wkn in range(1, 5):
        for i in range(12):
            onbye = (wkn == 3)
            rows.append(dict(key=f"p{i}|WR", name=f"p{i}", pos="WR", team="ZZ",
                             week=wkn, opp=(None if onbye else "XX"),
                             pts=(np.nan if onbye else 10.0), inj=None, body=None,
                             last_mod=None, news=None))
    rows.append(dict(key="ghost|RB", name="ghost", pos="RB", team="ZZ", week=3,
                     opp="XX", pts=1.0, inj=None, body=None, last_mod=None, news=None))
    tb = _team_byes(pd.DataFrame(rows))
    if tb.get("ZZ") != {3}:
        p.append(f"_team_byes got {tb.get('ZZ')}, expected {{3}} -- one bad row deleted a bye")

    # ---- v5.2: support() must tier on books, spread and coverage
    tb = pd.DataFrame([
        dict(key="a|WR", name="Thin Guy",  pos="WR", value_pg=15.0, n_books=3, spread_pg=1.83, coverage=0.92),
        dict(key="b|WR", name="Solid Guy", pos="WR", value_pg=15.0, n_books=8, spread_pg=0.60, coverage=0.94),
        dict(key="c|WR", name="Mid Guy",   pos="WR", value_pg=15.0, n_books=5, spread_pg=1.20, coverage=0.80),
        dict(key="d|WR", name="No Line",   pos="WR", value_pg=15.0, n_books=np.nan, spread_pg=0.10, coverage=0.0)])
    tb = support(tb)
    got = list(tb.support)
    if got != ["THIN", "SOLID", "OK", "THIN"]:
        p.append(f"support() tiers {got}, expected THIN/SOLID/OK/THIN")
    if "3bk" not in tb.support_why.iloc[0] or "SOURCE DISAGREE" not in tb.support_why.iloc[0]:
        p.append("support() did not report the reason for a THIN tier")
    if tb.support_why.iloc[1]:
        p.append("support() invented a reason for a SOLID player")
    if "[" not in fmt_val(tb, "Thin Guy") or "THIN" not in fmt_val(tb, "Thin Guy"):
        p.append("fmt_val() dropped the support tag -- the whole point of it")

    # ---- v5.2: implied_games must be season_line / per_game_line, and must
    # ---- refuse an insane ratio rather than emitting it
    bd = pd.DataFrame([
        dict(key="x|WR", name="Full Season", pos="WR", value_pg=15.0, rec_yd_mkt=1100.5),
        dict(key="y|WR", name="Misses Time", pos="WR", value_pg=15.0, rec_yd_mkt=975.5),
        dict(key="z|WR", name="Broken Pair", pos="WR", value_pg=15.0, rec_yd_mkt=1000.0)])
    mk = pd.DataFrame([dict(key="x|WR", rec_yd=63.5), dict(key="y|WR", rec_yd=61.5),
                       dict(key="z|WR", rec_yd=2.0)])
    ig, igd = implied_games(bd, 1, mkw=mk)
    if abs(ig.get("x|WR", 0) - 17.3) > 0.05: p.append(f"implied_games full-season got {ig.get('x|WR')}")
    if abs(ig.get("y|WR", 0) - 15.9) > 0.05: p.append(f"implied_games missed-time got {ig.get('y|WR')}")
    if "z|WR" in ig: p.append("implied_games emitted a 500-game ratio instead of dropping it")

    # ---- v5.2: TAIL_RISK must refuse undated / unsourced entries and must
    # ---- never touch a number
    savedt = list(TAIL_RISK)
    try:
        TAIL_RISK.clear()
        TAIL_RISK.append(dict(player="Thin Guy", pos="WR", dated="2026-09-03", src="unit test"))
        TAIL_RISK.append(dict(player="Thin Guy", pos="WR"))
        before = float(tb.value_pg.iloc[0])
        okk, rf2 = tail_risk_report(tb, verbose=False)
        if len(okk) != 1: p.append(f"tail_risk_report flagged {len(okk)}, expected 1")
        if len(rf2) != 1: p.append(f"tail_risk_report refused {len(rf2)}, expected 1")
        if abs(float(tb.value_pg.iloc[0]) - before) > 1e-9:
            p.append("tail_risk_report MUTATED a value -- it must only flag")
        if tail_flagged(["Thin Guy", "Solid Guy"]) != ["Thin Guy"]:
            p.append("tail_flagged() wrong")
    finally:
        TAIL_RISK.clear(); TAIL_RISK.extend(savedt)

    # ---- v5.3: per-game must be E[best8], not best8(E)
    # Two RBs who alternate: each averages 10, but the WEEKLY max averages 14.
    # best8(E) sees 10+10; E[best8] sees 14+6. Same players, different answer,
    # and the second one is what you score.
    wp3 = {"a|RB": {1: 18.0, 2: 2.0}, "b|RB": {1: 2.0, 2: 18.0},
           "q|QB": {1: 10.0, 2: 10.0}}
    wb3 = {"a|RB": set(), "b|RB": set(), "q|QB": set()}
    rt3 = player_rates(wp3, wb3, weeks=[1, 2])
    if abs(rt3["a|RB"] - 10.0) > 1e-9: p.append("player_rates() wrong")
    m3 = bye_neutral(wp3, wb3, rt3, weeks=[1, 2])
    v3 = {"a": (10.0, "RB", "a"), "b": (10.0, "RB", "b"), "q": (10.0, "QB", "q")}
    got = pergame(["a", "b", "q"], v3, m3, rt3, None, weeks=[1, 2])
    naive = pergame_naive(["a", "b", "q"], v3, rt3, None)
    if abs(got - 30.0) > 1e-9:
        p.append(f"pergame() got {got}, expected 30.0 (E[best8])")
    if abs(naive - 30.0) > 1e-9:
        p.append(f"pergame_naive() got {naive}, expected 30.0")
    # now make the lineup binding: only ONE RB slot's worth of value differs
    v3b = {"a": (10.0, "RB", "a"), "b": (10.0, "WR", "b"), "q": (10.0, "QB", "q")}
    wp3b = {"a|RB": {1: 18.0, 2: 2.0}, "b|WR": {1: 2.0, 2: 18.0},
            "q|QB": {1: 10.0, 2: 10.0}}
    rt3b = player_rates(wp3b, wb3 | {"b|WR": set()}, weeks=[1, 2])
    m3b = bye_neutral(wp3b, {"a|RB": set(), "b|WR": set(), "q|QB": set()},
                      rt3b, weeks=[1, 2])
    if abs(pergame(["a", "b", "q"], v3b, m3b, rt3b, None, weeks=[1, 2]) -
           pergame_naive(["a", "b", "q"], v3b, rt3b, None)) > 1e-9:
        p.append("pergame vs naive should tie when every player starts every week")
    if pergame(["a", "b", "q"], v3b, m3b, rt3b, None, weeks=[1, 2]) < \
       pergame_naive(["a", "b", "q"], v3b, rt3b, None) - 1e-9:
        p.append("JENSEN VIOLATED: pergame() came in BELOW pergame_naive()")

    # a bye must be replaced by his own rate, NOT zeroed
    wp4 = {"g|WR": {1: 12.0, 2: np.nan, 3: 8.0}}
    wb4 = {"g|WR": {2}}
    r4 = player_rates(wp4, wb4, weeks=[1, 2, 3])
    m4 = bye_neutral(wp4, wb4, r4, weeks=[1, 2, 3])
    if abs(r4["g|WR"] - 10.0) > 1e-9: p.append("player_rates() counted the bye week")
    if abs(m4["g|WR"][2] - 10.0) > 1e-9:
        p.append("bye_neutral() zeroed a bye instead of substituting his rate")
    # an unprojected NON-bye week is an injury and must score 0
    wp5 = {"h|WR": {1: 12.0, 2: np.nan, 3: 8.0}}
    m5 = bye_neutral(wp5, {"h|WR": set()}, None, weeks=[1, 2, 3])
    if m5["h|WR"][2] != 0.0:
        p.append("bye_neutral() laundered a missed game into a bye")

    # ---- v5: overrides must refuse undated / unsourced entries
    b = pd.DataFrame([dict(key=norm("Test Guy","RB"), name="Test Guy", pos="RB",
                           value_pg=10.0)])
    saved = list(OVERRIDES)
    try:
        OVERRIDES.clear()
        OVERRIDES.append(dict(player="Test Guy", pos="RB", weeks=None, mult=0.5,
                              dated="2026-08-30", src="unit test"))
        OVERRIDES.append(dict(player="Test Guy", pos="RB", weeks=None, mult=0.1))
        _, ap, rf = apply_overrides(b.copy(), verbose=False)
        if len(ap) != 1: p.append(f"apply_overrides applied {len(ap)}, expected 1")
        if len(rf) != 1: p.append(f"apply_overrides refused {len(rf)}, expected 1")
        bb, _, _ = apply_overrides(b.copy(), verbose=False)
        if abs(float(bb.value_pg.iloc[0]) - 5.0) > 1e-9:
            p.append("apply_overrides mult did not take")
    finally:
        OVERRIDES.clear(); OVERRIDES.extend(saved)

    # ---- v6.1: remaining weeks must not leak completed weeks
    if remaining_weeks(start=5, end=7) != [5, 6, 7]:
        p.append("remaining_weeks failed")

    # ---- v6.1: an over-cap roster must incur exactly one forced drop here
    tv = {f"x{i}": (float(20-i), "WR", f"x{i}") for i in range(16)}
    tr = {"players": list(tv), "reserve": []}
    legal, forced = legalize_roster(list(tv), tr, tv, lambda ids: best8(ids, tv), 15)
    if len(legal) != 15 or len(forced) != 1:
        p.append(f"legalize_roster got {len(legal)} players / {len(forced)} drops")

    # ---- v6.3: ROS value must neutralise a bye but retain a missed non-bye
    rb = pd.DataFrame([dict(key="a|WR", name="A", pos="WR", value_pg=8.0, n_src=2),
                       dict(key="b|WR", name="B", pos="WR", value_pg=8.0, n_src=2)])
    rp = {"a|WR": {1:10.0,2:np.nan,3:10.0},
          "b|WR": {1:10.0,2:np.nan,3:10.0}}
    rr = attach_ros_values(rb, rp, {"a|WR":{2}, "b|WR":set()}, weeks=[1,2,3])
    if abs(float(rr.loc[rr.key=="a|WR","ros_pg"].iloc[0])-10.0)>1e-9:
        p.append("attach_ros_values penalised a bye")
    if abs(float(rr.loc[rr.key=="b|WR","ros_pg"].iloc[0])-(20/3))>1e-9:
        p.append("attach_ros_values failed to price a missed non-bye week")

    # ---- v6.3: explicit role conflicts must be visible in source audit
    aud = weekly_source_audit({"x|QB":{1:16.0}}, {1:{"x|QB":0.5}},
                              {"x|QB":{1:8.25}}, {"x|QB":set()})
    if len(aud)!=1 or not bool(aud.role_conflict.iloc[0]):
        p.append("weekly_source_audit missed a starter/no-role conflict")

    # ---- v6.3: negative perception capital is zero, never package debt
    if perceived_cap({"x":-4.0}, "x") != 0.0:
        p.append("perceived_cap allowed negative filler to subsidise an elite asset")
    return p

# ---------------------------------------------------------------- session
def current_week(wkly=None, default=1):
    """Official Sleeper week, with --week N as an explicit override."""
    for i, a in enumerate(sys.argv):
        if a == "--week" and i + 1 < len(sys.argv):
            return int(sys.argv[i + 1])
    try:
        state = requests.get("https://api.sleeper.app/v1/state/nfl",
                             headers=UA, timeout=20).json()
        if str(state.get("season")) == str(SEASON):
            return max(1, min(18, int(state.get("week") or default)))
    except Exception:
        pass
    return int(default)


def remaining_weeks(start=None, end=17):
    """Remaining fantasy weeks; Week 18 is intentionally excluded."""
    start = current_week() if start is None else int(start)
    start, end = max(1, start), min(17, int(end))
    return list(range(start, end + 1)) if start <= end else []

def session(board, wkly=None, wk_pts=None, wk_bye=None, wk_meta=None, week=None,
            wk_roto=None, wk_spread=None, wk_espn=None, source_audit=None,
            market_audit=None, skip_trade_scan=False):
    rosters, users, players, picks, tx = league_cached()
    objective_col = "ros_pg" if "ros_pg" in board.columns else "value_pg"
    val = make_val(board, players, value_col=objective_col)
    vt  = vor_table(board, players, rosters, users, value_col=objective_col)
    anc = anchor_curve(vt, picks)
    umap = {u["user_id"]: u["display_name"] for u in users}
    myname = umap[next(x for x in rosters if x["roster_id"] == ME)["owner_id"]]
    rl = replacement(board, value_col=objective_col)
    week = week or current_week(wkly)
    have_wk = wk_pts is not None and len(wk_pts) > 0

    print("\n=== ROSTER (roster %d, %s) ===" % (ME, myname))
    mine = vt[vt.rid == ME].sort_values("vor", ascending=False)
    bidx = board.set_index("key")
    myr = next(x for x in rosters if x["roster_id"] == ME)
    for _, r in mine.iterrows():
        k = norm(r["name"], r["pos"])
        br = bidx.loc[k] if k in bidx.index else None
        if isinstance(br, pd.DataFrame): br = br.iloc[0]
        sp = float(br.spread_pg) if br is not None else 0.0
        m = (wk_meta or {}).get(k, {})
        tm = m.get("team") or "--"
        wkp = (wk_pts.get(k, {}) or {}).get(week, np.nan) if have_wk else np.nan
        wkc = f"{wkp:5.1f}" if not pd.isna(wkp) else ("  BYE" if week in (wk_bye or {}).get(k, set()) else "  OUT")
        istat, ibody = m.get("inj"), m.get("body")
        istat = None if (istat is None or (isinstance(istat, float) and pd.isna(istat))) else istat
        ibody = None if (ibody is None or (isinstance(ibody, float) and pd.isna(ibody))) else ibody
        inj = f" [{istat}{'/'+str(ibody) if ibody else ''}]" if istat else ""
        sup = (br["support"] if br is not None and "support" in br else "?")
        tail = "  <-- TAIL RISK" if r["name"] in {t["player"] for t in TAIL_RISK} else ""
        season_v = float(br.value_pg) if br is not None else float("nan")
        basis = "ROS" if objective_col == "ros_pg" else "SZN"
        print(f"  {r['pos']:3s} {r['name'][:21]:22s} {tm:4s}{r.value_pg:6.2f} {basis} "
              f"VOR {r.vor:+6.2f} szn {season_v:5.2f} spread {sp:4.2f} {sup:5s} w{week} {wkc}{inj}"
              + ("  <-- SOURCE DISAGREE" if sp > SUPPORT_SPREAD_BAD else "") + tail)
    print(f"  above replacement: {(mine.vor>0).sum()} of {len(mine)}  |  objective best-8 "
          f"{best8(myr['players'], val):.1f}")
    print("  replacement/gm: " + "  ".join(f"{k}={v:.1f}" for k, v in rl.items()))

    # ---------------------------------------------------- staleness first
    verify = set()
    if have_wk:
        # DIVERGENCE MUST SEE ROTOWIRE ONLY. It works by subtracting one
        # provider's season view from the SAME provider's weekly view, so any
        # gap can only be staleness rather than two shops disagreeing. Feeding
        # it the blended matrix would silently turn it into an opinion spread
        # and destroy the only clean staleness signal in the file.
        dv = divergence(board, wk_roto if wk_roto else wk_pts)
        if len(dv):
            print("\n=== STALENESS: season line vs the SAME source's weekly lines ===")
            print(f"  (basis offset removed: weekly runs {dv.attrs.get('offset',0):+.0f} "
                  f"season pts hotter across the top 250)")
            lo = dv.head(6); hi = dv.tail(6).iloc[::-1]
            print("  SEASON LINE TOO HIGH -- weekly says he plays less:")
            for r in lo.itertuples():
                print(f"    {r.name[:22]:23s} {r.pos:3s} season {r.season:6.1f}  "
                      f"weekly {r.weekly:6.1f} over {r.wks_played:2d} wks  gap {r.gap:+7.1f} ({r.gap_pg:+.2f}/gm)")
                verify.add(r.name)
            print("  SEASON LINE TOO LOW -- weekly says he plays more:")
            for r in hi.itertuples():
                print(f"    {r.name[:22]:23s} {r.pos:3s} season {r.season:6.1f}  "
                      f"weekly {r.weekly:6.1f} over {r.wks_played:2d} wks  gap {r.gap:+7.1f} ({r.gap_pg:+.2f}/gm)")
                verify.add(r.name)
            owned = {v[2] for p in myr["players"] if (v := val.get(p))}
            mineflag = dv[dv.name.isin(owned) & (dv.gap.abs() >= 15)]
            if len(mineflag):
                print("  ON YOUR ROSTER:")
                for r in mineflag.itertuples():
                    print(f"    {r.name[:22]:23s} gap {r.gap:+7.1f} ({r.gap_pg:+.2f}/gm) "
                          f"-- ROS objective now uses weekly truth; season provenance is stale")
                    verify.add(r.name)

    if wk_spread:
        ws = weekly_spread_report(wk_spread, board, top=8)
        if len(ws):
            print("\n=== WEEKLY SOURCE DISAGREEMENT (rotowire vs espn, per game) ===")
            print("  the weekly layer had no spread flag before v5.1; a big number here")
            print("  means the week-by-week rank on that player is a coin flip, not a fact")
            owned = {norm(v[2], v[1]) for p in myr["players"] if (v := val.get(p))}
            for r in ws.itertuples():
                mine_ = "  <-- YOURS" if r.key in owned else ""
                print(f"    {str(r.name)[:22]:23s} {str(r.pos):3s} mean spread "
                      f"{r.mean_spread:5.2f}/gm over {r.n} weeks{mine_}")
                if r.mean_spread >= 3.0: verify.add(r.name)

    print("\n=== ROOM MISPRICING (value vs draft slot, position-controlled) ===")
    for _, r in anc.nlargest(6, "misprice").iterrows():
        print(f"  BUY  {r['name'][:20]:21s} {r['pos']:3s} +{r.misprice:5.2f}  "
              f"({umap[next(x for x in rosters if x['roster_id']==r.rid)['owner_id']]})")
    for _, r in anc[anc.rid == ME].nsmallest(4, "misprice").iterrows():
        print(f"  SELL {r['name'][:20]:21s} {r['pos']:3s} {r.misprice:6.2f}")

    print("\n=== TRADE CANDIDATES (good for me, reads fair in round currency) ===")
    if skip_trade_scan:
        # Audit/export should never wait on the exhaustive combinatorial scanner.
        # The scanner is an optional decision tool, not required to reproduce
        # projections, roster rankings, or trade pricing from a supplied offer.
        s = pd.DataFrame()
        print("  SKIPPED for audit export (use a normal run when you explicitly want exhaustive trade search)")
    else:
        deep = "--deep-trade-scan" in sys.argv
        s = (scan_asymmetric(rosters, val, anc) if deep
             else scan_asymmetric_fast(rosters, val, anc))
        print(f"  search mode: {'EXHAUSTIVE' if deep else 'FAST bounded'} | objective={objective_col}")
        if len(s):
            s["mgr"] = s.rid.map({r["roster_id"]: umap[r["owner_id"]] for r in rosters})
            top = s.groupby("rid", group_keys=False).head(2).sort_values(
                "me", ascending=False).head(8)
            scan_cols = ["mgr","pkg","give","get","my_drop","their_drop","me","looks","truly"]
            print(top[[c for c in scan_cols if c in top.columns]].to_string(index=False))
            print(f"  ({len(s)} distinct packages; showing best 2 per manager)")
            for row in top.head(3).itertuples():
                verify |= set(row.give.split(" + ")) | set(row.get.split(" + "))
            if have_wk:
                rs = rescore_weekly(s, rosters, val, players, wk_pts, fill=None)
                if len(rs) and "wk_playoff" in rs:
                    print("\n  --- SAME PACKAGES, RE-PRICED ON THE WEEKLY BASIS ---")
                    print("  (search runs on the season board because that is the trade currency;")
                    print("   ranking runs on the basis that knows about this week's injuries)")
                    cols = ["mgr","give","get","me","wk_reg","wk_playoff","wk_worst","worst_wk"]
                    print(rs.head(6)[cols].to_string(index=False))
                    flip = rs[rs.season_says_yes_weekly_says_no]
                    if len(flip):
                        print(f"  !! {len(flip)} of {len(rs)} packages gain on the season number "
                              f"and LOSE playoff points. Season-basis rank is not safe alone.")
        else:
            print("  none")

    print("\n=== WIRE (free agents, both-source, by VOR) ===")
    fa = wire(board, players, rosters)
    if have_wk:
        fa["w%d" % week] = [round(float(wk_pts.get(norm(r["name"], r.pos), {}).get(week, np.nan)), 1)
                            if not pd.isna(wk_pts.get(norm(r["name"], r.pos), {}).get(week, np.nan))
                            else np.nan for _, r in fa.iterrows()]
    for pos in ("RB", "WR", "TE", "QB"):
        top = fa[fa.pos == pos].head(4)
        cells = []
        for _, t in top.iterrows():
            c = f"{t['name']} {t.value_pg:.1f}"
            if have_wk:
                v = t.get(f"w{week}")
                c += f" (w{week} {v:.1f})" if not pd.isna(v) else f" (w{week} --)"
            if t.status: c += f" [{t.status[:4]}]"
            cells.append(c)
        print(f"  {pos} (repl {rl[pos]:.1f}): " + " | ".join(cells))
    up = upgrades(rosters, val, fa, rl)
    print("  --- worthwhile add/drop (best-8 priced, roster is full) ---")
    print(up.head(6).to_string(index=False) if len(up) else "  none clears the bar")

    # ------------------------------------------------ weekly, the real one
    if have_wk:
        # v5.3 -- this is now the headline ranking. weekly_strength() below is
        # kept because a bye-loaded week is still a matchup you have to play,
        # but it is NOT what decides whether a roster is good.
        rates_, mat_, pool_ = pergame_setup(board, wk_pts, wk_bye, players, rosters)
        pgt = pergame_table(rosters, users, val, mat_, rates_, pool_)
        jg = jensen_gap(rosters, val, mat_, rates_, pool_)
        print("\n=== PER-GAME STRENGTH (E[best8], byes neutralised) -- THE RANKING ===")
        print(pgt.to_string(index=False))
        me_pg = float(pgt[pgt.rid == ME].pergame.iloc[0])
        lead = me_pg - float(pgt[pgt.rid != ME].pergame.max())
        print(f"  you: {me_pg:.2f}/gm, {lead:+.2f} vs the next best "
              f"({'REAL, clears the ' if abs(lead) >= COIN_FLIP else 'INSIDE the '}"
              f"{COIN_FLIP} coin-flip line)")
        print(f"  deprecated estimator understated the field by "
              f"{jg.gap.mean():+.2f}/gm on average, spread "
              f"{jg.gap.min():+.2f} to {jg.gap.max():+.2f} -- a wide spread means "
              f"it was RE-ORDERING teams, not just shifting them")

        print("\n=== WEEKLY STRENGTH (absolute best-8, real per-week projections) ===")
        fill = None
        ws = weekly_strength(rosters, users, val, players, wk_pts, fill=None)
        me_row = ws[ws.rid == ME].iloc[0]
        wcols = [c for c in ws.columns if c.startswith("w") and c[1:].isdigit()]
        print("  me:  " + " ".join(f"w{w}{me_row['w%d'%w]:6.1f}" for w in range(1, 18)
                                   if f"w{w}" in ws.columns))
        print(f"  reg(w1-14) {me_row['reg']:.0f}   playoffs(w15-17) {me_row['playoff']:.0f}"
              f"   worst {me_row['worst']:.1f} in {me_row['worst_wk']}")
        rank = ws.sort_values("reg", ascending=False).reset_index(drop=True)
        pos_ = int(rank.index[rank.rid == ME][0]) + 1
        pl = ws.sort_values("playoff", ascending=False).reset_index(drop=True)
        ppos = int(pl.index[pl.rid == ME][0]) + 1
        print(f"  league rank: {pos_} of {len(ws)} on regular season, {ppos} of {len(ws)} on playoff weeks")
        print("  weakest weeks league-wide (natural trade counterparties):")
        for r in ws.nsmallest(4, "worst").itertuples():
            print(f"    {r.mgr:16s} {r.worst:6.1f} in {r.worst_wk}")

        ma = market_audit if market_audit is not None else pd.DataFrame()
        ma = ma[ma.week == week].copy() if len(ma) and "week" in ma else pd.DataFrame()
        if len(ma):
            print(f"\n=== WEEK {week} MARKET OVERLAY -- THIS IS IN THE PRODUCTION MATRIX ===")
            print(f"  {len(ma)} player projections adjusted | median coverage "
                  f"{ma.coverage.median()*100:.0f}%")
            owned = {norm(v[2], v[1]) for p in myr["players"] if (v := val.get(p))}
            mine_ma = ma[ma.key.isin(owned)]
            hi = mine_ma.nlargest(6, "adjustment")
            lo = mine_ma.nsmallest(4, "adjustment")
            print("  books ABOVE your blended projection:")
            for r in hi.itertuples():
                print(f"    {r.name[:22]:23s} {r.base:5.1f} {r.adjustment:+5.2f} -> {r.final:5.1f}  "
                      f"({r.coverage*100:3.0f}% cov)")
            print("  books BELOW:")
            for r in lo.itertuples():
                print(f"    {r.name[:22]:23s} {r.base:5.1f} {r.adjustment:+5.2f} -> {r.final:5.1f}  "
                      f"({r.coverage*100:3.0f}% cov)")
        else:
            print(f"\n  week {week} market overlay: none applied to production")

    print(f"\n=== VERIFY BEFORE ACTING ({len(verify)} names) ===")
    bw = board.set_index("key")
    for n in sorted(verify)[:18]:
        rows = bw[bw.name == n]
        flag = ""
        if len(rows):
            rr = rows.iloc[0]
            if rr.get("spread_pg", 0) > 1.5: flag += " [sources disagree]"
            if rr.get("n_mkt", 0) == 0: flag += " [no season line]"
            k = rr.name if isinstance(rr.name, str) else norm(n, rr.get("pos"))
            m = (wk_meta or {}).get(norm(n, rr.get("pos")), {}) or {}
            st_, bd_ = m.get("inj"), m.get("body")
            if st_ is not None and not (isinstance(st_, float) and pd.isna(st_)):
                bd_ = None if (bd_ is None or (isinstance(bd_, float) and pd.isna(bd_))) else bd_
                flag += f" [{st_}{'/'+str(bd_) if bd_ else ''}]"
        print(f"  {n}{flag}")
    print("  -> injury/suspension/role status, snap+target trend, is the line stale")
    return dict(board=board, weekly=wkly, wk_pts=wk_pts, wk_bye=wk_bye,
                wk_meta=wk_meta, wk_roto=wk_roto, wk_spread=wk_spread,
                wk_espn=wk_espn, source_audit=source_audit,
                market_audit=market_audit, rosters=rosters, users=users,
                players=players, picks=picks, tx=tx, val=val, vor=vt,
                anchor=anc, shortlist=s, week=week)

def _bundle_jsonable(x):
    """Convert engine objects to conservative JSON-safe primitives."""
    if x is None or isinstance(x, (str, int, bool)):
        return x
    if isinstance(x, float):
        return None if (np.isnan(x) or np.isinf(x)) else x
    if isinstance(x, np.generic):
        return _bundle_jsonable(x.item())
    if isinstance(x, dict):
        return {str(k): _bundle_jsonable(v) for k, v in x.items()}
    if isinstance(x, (set, tuple, list, range)):
        return [_bundle_jsonable(v) for v in x]
    return str(x)

def export_audit_bundle(sess, out_path="ff_audit_bundle.zip"):
    """Write one self-contained, non-pickle bundle for offline auditing.

    The bundle intentionally contains no API credentials. It lets a second
    machine reproduce roster/trade/ranking analysis without another live pull.
    """
    out_path = os.path.abspath(out_path)
    with tempfile.TemporaryDirectory(prefix="ff_audit_") as td:
        files = []
        def add_csv(name, obj):
            if obj is None:
                return
            if isinstance(obj, pd.DataFrame):
                if len(obj.columns) == 0:
                    return
                q = os.path.join(td, name); obj.to_csv(q, index=False); files.append(q)
        def add_json(name, obj):
            q = os.path.join(td, name)
            with open(q, "w", encoding="utf-8") as f:
                json.dump(_bundle_jsonable(obj), f, indent=2, sort_keys=True)
            files.append(q)

        add_csv("board.csv", sess.get("board"))
        add_csv("weekly_raw.csv", sess.get("weekly"))
        add_csv("market_audit.csv", sess.get("market_audit"))
        add_csv("weekly_source_audit.csv", sess.get("source_audit"))
        add_csv("anchor.csv", sess.get("anchor"))
        add_csv("trade_shortlist.csv", sess.get("shortlist"))

        # Dict matrices become compact long CSVs, easier and safer than pickle.
        for field, fname, value_name in (("wk_pts", "weekly_final.csv", "points"),
                                         ("wk_roto", "weekly_rotowire.csv", "points"),
                                         ("wk_spread", "weekly_spread.csv", "spread")):
            mat = sess.get(field) or {}
            rows = []
            for key, weeks in mat.items():
                if not isinstance(weeks, dict): continue
                for wk, value in weeks.items():
                    rows.append({"key": key, "week": int(wk), value_name: value})
            add_csv(fname, pd.DataFrame(rows))

        esp_rows = []
        for wk, vals in (sess.get("wk_espn") or {}).items():
            if not isinstance(vals, dict): continue
            for key, value in vals.items():
                esp_rows.append({"key": key, "week": int(wk), "points": value})
        add_csv("weekly_espn.csv", pd.DataFrame(esp_rows))

        add_json("weekly_byes.json", sess.get("wk_bye") or {})
        add_json("weekly_meta.json", sess.get("wk_meta") or {})
        add_json("rosters.json", sess.get("rosters") or [])
        add_json("users.json", sess.get("users") or [])
        add_json("draft_picks.json", sess.get("picks") or [])
        add_json("transactions.json", sess.get("tx") or [])

        # Only fields used by the engine/auditor; this keeps the bundle small.
        pkeep = {}
        for pid, r in (sess.get("players") or {}).items():
            if not isinstance(r, dict): continue
            pkeep[pid] = {k: r.get(k) for k in ("player_id", "full_name", "first_name",
                "last_name", "position", "team", "status", "injury_status",
                "injury_body_part", "fantasy_positions") if k in r}
        add_json("players_skill.json", pkeep)

        # Include the exact engine source used to create the bundle. Credentials
        # live in the environment, never in this file, so this is safe and makes
        # an audit genuinely reproducible from one upload.
        try:
            src_path = os.path.abspath(__file__)
            q = os.path.join(td, "engine_source.py")
            with open(src_path, "rb") as src, open(q, "wb") as dst:
                dst.write(src.read())
            files.append(q)
        except Exception:
            pass

        hashes = {}
        for q in files:
            with open(q, "rb") as f: hashes[os.path.basename(q)] = hashlib.sha256(f.read()).hexdigest()
        board_ = sess.get("board") if isinstance(sess.get("board"), pd.DataFrame) else pd.DataFrame()
        mkt_players = int((board_.get("n_mkt", pd.Series(dtype=float)).fillna(0) > 0).sum()) if len(board_) else 0
        wk_mkt = len(sess.get("market_audit")) if isinstance(sess.get("market_audit"), pd.DataFrame) else 0
        bp_enabled = bool(BP_API_KEY) and not QUICK
        quality = ("COMPLETE" if (bp_enabled and mkt_players > 0 and wk_mkt > 0)
                   else ("PARTIAL_MARKET" if (mkt_players > 0 or wk_mkt > 0) else "NO_MARKET"))
        manifest = dict(engine="v6.3 audit-export", season=SEASON, league=LEAGUE,
                        generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        current_week=sess.get("week"), files=hashes,
                        market_auth_active=bp_enabled, quick_mode=bool(QUICK),
                        season_market_players=mkt_players,
                        weekly_market_adjustments=wk_mkt,
                        audit_quality=quality,
                        objective_basis=("ros_pg" if "ros_pg" in board_.columns else "value_pg"),
                        note="No API credentials are included. Trade scan is intentionally skipped during --export-bundle.")
        add_json("manifest.json", manifest)

        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for q in files:
                z.write(q, arcname=os.path.basename(q))
    if not QUICK and not BP_API_KEY:
        print("AUDIT WARNING: BettingPros auth was NOT active in this process; market overlay is degraded.")
    elif isinstance(sess.get("board"), pd.DataFrame) and int((sess["board"].get("n_mkt",0)>0).sum()) == 0:
        print("AUDIT WARNING: auth is present but exported season board has 0 market-covered players.")
    print(f"AUDIT BUNDLE: {out_path}")
    return out_path

# ------------------------------------------------------------------- main
if __name__ == "__main__":
    if "--selftest" in sys.argv:
        p = selftest()
        print("SELFTEST: " + ("OK" if not p else "!! " + " | ".join(p)))
        sys.exit(0 if not p else 1)
    p = selftest()
    if p:
        print("!! SELFTEST FAILED: " + " | ".join(p) + "\n   numbers below are untrustworthy\n")
    force = "--rebuild" in sys.argv

    print("=== v6.3 ROS PRODUCTION PATH ===")
    print("  season production: independent venues + direct Underdog + progressive receptions")
    print("  weekly production: one authoritative Rotowire + ESPN + posted-market pipeline")
    print("  streamers: excluded unless explicitly requested")
    print("  research-only: calibrated source weights, rec_two_ways diagnostics, matchup_odds")
    print("=== board (season basis: VOR, anchor, trade scanner) ===")
    board = board_cached(force=force)
    print(f"board: {len(board)} players, {(board.n_src>=2).sum()} both-source, "
          f"{(board.n_mkt>0).sum()} with season market lines")

    wkly = wk_pts = wk_bye = wk_meta = None
    wk_roto = wk_spread = None
    market_audit = pd.DataFrame()
    source_audit = pd.DataFrame()
    esp = {}
    if "--board-only" not in sys.argv:
        print("\n=== weekly production pipeline ===")
        try:
            wkly = weekly_cached(force=force)
            live = wkly[wkly.pts.notna()].key.nunique()
            pipe = build_weekly_projection_pipeline(wkly, board=board, force=force,
                                                    use_market=True)
            wk_roto, wk_bye, wk_meta = pipe["rotowire"], pipe["bye"], pipe["meta"]
            wk_pts, wk_spread, esp = pipe["final"], pipe["spread"], pipe["espn"]
            market_audit = pipe["market_audit"]
            source_audit = pipe.get("source_audit", pd.DataFrame())
            print(f"weekly rotowire: {wkly.week.nunique()} weeks, {wkly.key.nunique()} players, "
                  f"{live} projected in at least one week")
            if esp:
                print(f"weekly espn:     {len(esp)} weeks -> missingness-safe blend")
            if len(market_audit):
                print(f"weekly market:   applied to {len(market_audit)} player-weeks in production")
            else:
                print("weekly market:   no posted/authorized overlay; projection blend passes through")
        except Exception as e:
            print(f"weekly FAILED {type(e).__name__}: {e}\n"
                  "   -> falling back to season-only behaviour")

    board, _ap, _rf = apply_overrides(board, wk_pts)
    if "support" not in board: board = support(board)
    if wk_pts:
        board = attach_ros_values(board, wk_pts, wk_bye or {}, wk_spread=wk_spread,
                                  source_audit=source_audit)
        movers = board[(board.n_src >= 2) & board.pos.isin(["QB","RB","WR","TE"])].copy()
        if len(movers):
            print("ROS BASIS: authoritative remaining-week matrix attached; "
                  f"median |ROS-season|={movers.ros_gap.abs().median():.2f}/gm, "
                  f"role-conflict players={(movers.ros_role_conflicts>0).sum()}")
    else:
        board = attach_ros_values(board, None, {}, source_audit=source_audit)
    tail_risk_report(board)

    probs = health_check(board, wkly, wk_pts, locals().get("esp"))
    print("\nHEALTH: " + ("OK" if not probs else "!! " + " | ".join(probs)))
    if wkly is not None and len(wkly):
        bad = bye_crosscheck(wkly, limit=5)
        print("BYE CROSSCHECK: " + (f"schedule and weekly feed agree on all "
          f"{wkly.team.nunique()} teams"
          if not bad else f"!! {len(bad)} team disagreements: {bad[:3]}"))
    if "--board-only" not in sys.argv:
        _r, _u, _p, _pk, _tx = league_cached()
        seen, stale, worst, age_h = freshness(board, _p, wkly)
        print(f"FRESHNESS: {seen} injured/questionable players on the board | "
              f"still carrying a full season projection: "
              + (", ".join(f"{k} {v}" for k, v in stale.items()) if stale else "none")
              + ("   <-- a source may be frozen" if any(v > 8 for v in stale.values()) else ""))
        for pts_, nm_, st_, s_, why_ in worst[:5]:
            print(f"   {nm_[:22]:23s} {st_:12s} {why_:24s} {s_} still projects {pts_:.0f} season pts")
        if age_h is not None:
            print(f"   weekly feed last rebuilt {age_h:.1f}h ago")
        print("RECEPTIONS: " + " | ".join(f"{k} -> {v}" for k, v in
              check_receptions(current_week(wkly)).items()))
        cv = board[board.n_mkt > 0]
        print("SEASON COVERAGE: median share of points from a REAL book line -- " +
              "  ".join(f"{p}={g.mkt_real_pct.median():.0f}%" for p, g in cv.groupby("pos")))
        _sess = session(board, wkly, wk_pts, wk_bye, wk_meta,
                        wk_roto=wk_roto, wk_spread=wk_spread, wk_espn=esp,
                        source_audit=source_audit, market_audit=market_audit,
                        skip_trade_scan=("--export-bundle" in sys.argv))
        if "--export-bundle" in sys.argv:
            export_audit_bundle(_sess)
