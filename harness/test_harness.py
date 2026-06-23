"""Model-agnostic invariant harness — the parametrized test matrix (TASK-07).

Every invariant I1–I13 is exercised against every registered model (bespoke_flat,
bespoke_weekly, mhr, ridge) using a consistent parametrize+MATRIX pattern.  The MATRIX
encodes the expected outcome for each (invariant, model) cell:
  "pass"  — check_* must succeed (no AssertionError); test fails if it raises
  "xfail" — the model is documented to violate this invariant; test xfails (strict=True) so
             any unexpected pass becomes a failure
  "skip"  — the check requires features (attribution) the model does not emit, or the minimal
             construction is ambiguous for this model

Game factories (make_*_games()) live here — NOT inside check functions — so TASK-12 can
reuse the check functions with real scenario data by calling them directly with its own
game lists.  Each factory is a plain zero-argument callable that returns list[GameRow].

Note on I13: make_I13_games() is a special-case factory used only by check_I13 itself
(via the adapter) because the invariant compares two game worlds (blip vs no-blip) and two
window sizes — that state needs to be passed through.  The factory for the MATRIX cell is a
wrapper that just exercises the invariant using the check function's internal two-world logic.
"""

import random

import pytest

from core.game import GameRow
from harness.adapters import ModelFn, bespoke_flat, bespoke_weekly, mhr, ridge
from harness.invariants import (
    check_I1,
    check_I1_benchmark,
    check_I2,
    check_I3,
    check_I4,
    check_I5,
    check_I6,
    check_I7,
    check_I8,
    check_I9,
    check_I10,
    check_I11,
    check_I12,
    check_I13,
)


# ---------------------------------------------------------------------------
# Game factory helpers
# ---------------------------------------------------------------------------

def _g(team: str, opponent: str, gf: int, ga: int, week: int = 1) -> GameRow:
    """Minimal hand-built Level-0 row (date/time are inert for all models)."""
    return GameRow(
        week=week,
        date="2025-10-06",
        time="10:45",
        team=team,
        opponent=opponent,
        goals_team=gf,
        goals_opponent=ga,
    )


# --- I1 -------------------------------------------------------------------

def make_I1_games() -> list[GameRow]:
    """3-team A/B/C: A beats C 3-2, B loses to C 2-3.
    I1 requires ratings["A"] > ratings["B"] (winning vs C > losing vs C).
    """
    return [
        _g("A", "C", 3, 2),
        _g("B", "C", 2, 3),
    ]


def make_I1_benchmark_games() -> list[GameRow]:
    """A/B/C/STRONG: the exact I1-violation construction from test_I1_violation_documented.
    A beats C 2-1, B loses to C 1-2; A loses to STRONG 0-7, B beats STRONG 7-0.
    Benchmarks violate I1 here: ratings["B"] > ratings["A"] despite A winning vs C.
    """
    return [
        _g("A", "C",      2, 1),   # A wins  vs C
        _g("B", "C",      1, 2),   # B loses vs C
        _g("A", "STRONG", 0, 7),   # A loses to STRONG by 7
        _g("B", "STRONG", 7, 0),   # B beats  STRONG by 7
    ]


# --- I2 -------------------------------------------------------------------

def make_I2_games() -> list[list[GameRow]]:
    """Four separate 2-team datasets at margins 1, 3, 4, 6.
    Each dataset is independent: T beats OPP by that margin, OPP is a fresh dummy team.
    Returned as a list of 4 game lists in ascending-margin order.
    """
    return [
        [_g("T", f"OPP_{m}", 1 + m, 1)]   # win by margin m; goals_team = 1+m, goals_opponent=1
        for m in [1, 3, 4, 6]
    ]


# --- I3 -------------------------------------------------------------------

def make_I3_games() -> list[list[GameRow]]:
    """Same 4 datasets as I2 (margins 1, 3, 4, 6). Used to read per_game_attribution.total."""
    return make_I2_games()


# --- I4 -------------------------------------------------------------------

def make_I4_games() -> tuple[list[GameRow], list[GameRow]]:
    """Two 2-team datasets: T loses 1-2 (close, margin 1) vs T loses 1-6 (blowout, margin 5).
    Returns (close_games, blowout_games). I4: ratings_close["T"] >= ratings_blowout["T"].
    """
    close   = [_g("T", "OPP", 1, 2)]   # lose by 1: close loss, zero penalty
    blowout = [_g("T", "OPP", 1, 6)]   # lose by 5: blowout, full penalty
    return close, blowout


# --- I5 -------------------------------------------------------------------

def make_I5_games() -> tuple[list[GameRow], list[GameRow], list[GameRow]]:
    """Three 2-team datasets: T wins 3-2, T ties 2-2, T loses 2-3.
    Returns (win_games, tie_games, loss_games). I5: rating_win >= rating_tie >= rating_loss.
    """
    win  = [_g("T", "OPP", 3, 2)]
    tie  = [_g("T", "OPP", 2, 2)]
    loss = [_g("T", "OPP", 2, 3)]
    return win, tie, loss


# --- I6 -------------------------------------------------------------------

def make_I6_games() -> list[GameRow]:
    """Long-chain construction: ELITE >> LINK1 >> ... >> LINK6 >> WEAK (8-team chain).
    Each team beats the next one in the chain 7-0 (10 games each), creating a large enough
    ELITE-WEAK rating gap (~5.4) that the bespoke schedule term can overcome the base(W - L) gap.
    TARGET1 loses to ELITE 1-2 (close, zero margin penalty).
    TARGET2 beats WEAK 1-0 (close, zero margin bonus).

    I6 (for bespoke): a close loss to ELITE must rate better than a close win over WEAK.
    Assert ratings["TARGET1"] > ratings["TARGET2"].

    Mechanically: TARGET1 credit = base_L(0) + 0 + alpha*R_E = 0.6*R_E
                  TARGET2 credit = base_W(3) + 0 + alpha*R_W = 3 + 0.6*R_W
    I6 passes when 0.6*(R_E - R_W) > 3, i.e., R_E - R_W > 5.
    The 8-team chain achieves an ~5.5 gap (verified), which clears the threshold.

    Note: Ridge Massey is marked skip (not xfail) because in this chain construction Ridge also
    places TARGET1 above TARGET2 (Massey: T1 ≈ ELITE - 1 >> T2 ≈ WEAK + 1 given the large chain
    gap).  Ridge fails I6 in blowout-score scenarios where margin swamps result category, but that
    requires a separate (narrower) construction; exposing that gap is TASK-11's job.
    """
    chain = ["ELITE", "LINK1", "LINK2", "LINK3", "LINK4", "LINK5", "LINK6", "WEAK"]
    games: list[GameRow] = []
    for i in range(len(chain) - 1):
        for _ in range(10):
            games.append(_g(chain[i], chain[i + 1], 7, 0))
    games.append(_g("TARGET1", "ELITE", 1, 2))   # close loss to ELITE (no penalty)
    games.append(_g("TARGET2", "WEAK",  1, 0))   # close win over WEAK (no bonus)
    return games


# --- I7 -------------------------------------------------------------------

def make_I7_games() -> list[GameRow]:
    """3-team W/L/O: W beats O 2-1 (weeks 1-3), L loses to O 1-2 (weeks 1-3).
    I7: ratings["W"] > ratings["L"] — the win/loss floor can't be flipped by schedule.
    """
    games: list[GameRow] = []
    for week in range(1, 4):
        games.append(_g("W", "O", 2, 1, week=week))
        games.append(_g("L", "O", 1, 2, week=week))
    return games


# --- I8 -------------------------------------------------------------------

def make_I8_games() -> list[GameRow]:
    """Round-robin 3 teams STRONG/MID/WEAK, 4 rounds, seeded RNG for reproducible but varied scores.
    I8: any permutation of this list → byte-identical ratings.
    """
    # Use a seeded RNG to generate realistic-but-fixed scores (the RNG is only for game construction,
    # never in the rater itself — I8 requires the RATER to be deterministic, not the game generator).
    rng = random.Random(1)
    teams = [("STRONG", "MID"), ("STRONG", "WEAK"), ("MID", "WEAK")]
    games: list[GameRow] = []
    for week in range(1, 5):
        for home, away in teams:
            # Generate simple biased scores: home advantage of +1 expected goal for illustration.
            gf = max(0, rng.randint(1, 7))
            ga = max(0, rng.randint(0, 5))
            games.append(_g(home, away, gf, ga, week=week))
    return games


# --- I9 -------------------------------------------------------------------

def make_I9_games() -> list[GameRow]:
    """Same round-robin dataset as I8 (seed=1) but the I9 check injects two init dicts.
    The factory just returns the game list; the check passes init separately.
    """
    return make_I8_games()


# --- I10 ------------------------------------------------------------------

def make_I10_games() -> list[GameRow]:
    """I10 game construction: STALE has a misleading early record — close wins over weak opponents
    in week 1 (no margin bonus, low schedule credit), then blowout losses to strong opponents in
    week 2 (full margin penalty, high schedule debit).

    The asymmetric credit structure makes STALE rate below zero despite equal wins and losses:
      - Win by 1 over WEAK: base=3, margin_adj=0 (close win, no bonus), schedule_term=0.6*R_W (<0)
      - Lose by 7 to STRONG: base=0, margin_adj=-1.0 (blowout penalty), schedule_term=0.6*R_S (>0)
    STALE's season credit is pulled negative because the big-margin losses carry a full penalty
    whereas the close wins carry no bonus, and the opponent quality weighting goes against STALE.

    Additional context games (S1/S2 beat W1/W2 big) establish the STRONG/WEAK strata so the
    schedule terms in STALE's games reflect converged quality, not just centering artifacts.
    I10: assert ratings["STALE"] < 0.
    """
    return [
        # Week 1: STALE wins by 1 goal over weak teams (small credit: no margin bonus)
        _g("STALE", "W1", 2, 1, week=1),
        _g("STALE", "W2", 2, 1, week=1),
        # Week 2: STALE loses by 7 to strong teams (full blowout penalty)
        _g("S1", "STALE", 8, 1, week=2),
        _g("S2", "STALE", 8, 1, week=2),
        # Context: S1/S2 are genuinely strong (beat the same weak teams); W1/W2 are genuinely weak
        _g("S1", "W1", 5, 0, week=1),
        _g("S2", "W2", 5, 0, week=1),
    ]


# --- I11 ------------------------------------------------------------------

def make_I11_games() -> list[GameRow]:
    """6-week RISER/FALLER/FIELD construction: RISER beats FIELD by increasing margin (1→6 goals),
    FALLER beats FIELD by decreasing margin (6→1 goals). Both play every FIELD team each week.
    Same season-average winning margin ensures I11 is a trend effect, not a raw-strength effect.
    Uses 3 field teams for a connected graph.
    """
    fields = ["F1", "F2", "F3"]
    games: list[GameRow] = []
    for week in range(1, 7):
        riser_margin = week          # 1, 2, 3, 4, 5, 6
        faller_margin = 7 - week     # 6, 5, 4, 3, 2, 1
        for f in fields:
            # RISER beats field by riser_margin: score = (1 + riser_margin) to 1
            games.append(_g("RISER",  f, 1 + riser_margin, 1, week=week))
            # FALLER beats field by faller_margin: score = (1 + faller_margin) to 1
            games.append(_g("FALLER", f, 1 + faller_margin, 1, week=week))
            # FIELD teams play each other to stay connected (simple round robin)
        for i in range(len(fields)):
            for j in range(i + 1, len(fields)):
                # Ties among field teams: neutral signal
                games.append(_g(fields[i], fields[j], 2, 2, week=week))
    return games


# --- I12 ------------------------------------------------------------------

def make_I12_games() -> list[GameRow]:
    """3-week 3-team round-robin (A/B/C), 3 repeats per week pair — 9 games per week, 27 total.
    Each team plays the other two in each week across all 3 weeks. Provides varied scores to
    exercise the reconciliation identity across all three attribution drivers.
    """
    rng = random.Random(42)
    teams = ["A", "B", "C"]
    games: list[GameRow] = []
    for week in range(1, 4):
        for i, home in enumerate(teams):
            for j, away in enumerate(teams):
                if i < j:
                    gf = rng.randint(0, 6)
                    ga = rng.randint(0, 6)
                    games.append(_g(home, away, gf, ga, week=week))
    return games


# --- I13 ------------------------------------------------------------------

def make_I13_blip_games() -> list[GameRow]:
    """The blip-world for I13: BLIP crushes elites in week 2 only; VICTIM plays BLIP in week 3.
    Mirrors the _i13_world(blip=True) construction in models/test_bespoke_rate.py but simplified
    to 3 clear weeks.

    Strata: E1/E2 (elite), M1 (mid), BLIP + F1 (field), VICTIM.
    Weeks 1-3: elites beat field and mid; mid beats field. BLIP normally loses.
    Week 2 blip: BLIP beats E1/E2/M1 big (10-0).
    Week 3: VICTIM beats BLIP 3-0 (the single game used to read margin_adj).
    """
    games: list[GameRow] = []
    for week in range(1, 4):
        # Elites dominate
        games += [
            _g("E1", "F1", 8, 0, week=week),
            _g("E2", "F1", 8, 0, week=week),
            _g("E1", "M1", 5, 0, week=week),
            _g("E2", "M1", 5, 0, week=week),
            _g("M1", "F1", 5, 0, week=week),
        ]
        if week == 2:
            # One-week blip: BLIP demolishes everyone
            games += [
                _g("BLIP", "E1", 10, 0, week=week),
                _g("BLIP", "E2", 10, 0, week=week),
                _g("BLIP", "M1", 10, 0, week=week),
            ]
        else:
            # Normal: BLIP is field-level, losing to elites and mid
            games += [
                _g("E1", "BLIP", 8, 0, week=week),
                _g("E2", "BLIP", 8, 0, week=week),
                _g("M1", "BLIP", 5, 0, week=week),
            ]
    # VICTIM's single game: beats BLIP in week 3
    games.append(_g("VICTIM", "BLIP", 3, 0, week=3))
    return games


def make_I13_normal_games() -> list[GameRow]:
    """Normal world (no blip) for I13: BLIP is always field-level. Used to establish baseline."""
    games: list[GameRow] = []
    for week in range(1, 4):
        games += [
            _g("E1", "F1", 8, 0, week=week),
            _g("E2", "F1", 8, 0, week=week),
            _g("E1", "M1", 5, 0, week=week),
            _g("E2", "M1", 5, 0, week=week),
            _g("M1", "F1", 5, 0, week=week),
            _g("E1", "BLIP", 8, 0, week=week),
            _g("E2", "BLIP", 8, 0, week=week),
            _g("M1", "BLIP", 5, 0, week=week),
        ]
    games.append(_g("VICTIM", "BLIP", 3, 0, week=3))
    return games


# ---------------------------------------------------------------------------
# MATRIX: (inv_id, check_fn, model_name, model_fn, games_fn, expect)
#
# games_fn must be a zero-argument callable returning list[GameRow] (or a tuple for
# invariants that need multiple datasets).  check_* receives the factory's return value.
# "expect" is "pass", "xfail", or "skip".
#
# I11 and I13 require bespoke_weekly (rate_weekly).
# I1 uses two rows: the simple bespoke check AND a separate benchmark xfail check.
# I8/I9 are passed to all three models; I2-I7/I10/I12 are bespoke-only (benchmarks skip).
# ---------------------------------------------------------------------------

MATRIX = [
    # I1 — bespoke_flat passes; benchmarks fail
    ("I1",  check_I1,           "bespoke_flat",   bespoke_flat,   make_I1_games,           "pass"),
    ("I1",  check_I1_benchmark, "mhr",            mhr,            make_I1_benchmark_games, "xfail"),
    ("I1",  check_I1_benchmark, "ridge",          ridge,          make_I1_benchmark_games, "xfail"),

    # I2 — bespoke_flat passes; benchmarks skip (no per-game result floor guarantee)
    ("I2",  check_I2,           "bespoke_flat",   bespoke_flat,   make_I2_games,           "pass"),
    ("I2",  check_I2,           "mhr",            mhr,            make_I2_games,           "skip"),
    ("I2",  check_I2,           "ridge",          ridge,          make_I2_games,           "skip"),

    # I3 — bespoke_flat passes (attribution); benchmarks skip (no attribution)
    ("I3",  check_I3,           "bespoke_flat",   bespoke_flat,   make_I3_games,           "pass"),
    ("I3",  check_I3,           "mhr",            mhr,            make_I3_games,           "skip"),
    ("I3",  check_I3,           "ridge",          ridge,          make_I3_games,           "skip"),

    # I4 — bespoke_flat passes; benchmarks skip
    ("I4",  check_I4,           "bespoke_flat",   bespoke_flat,   make_I4_games,           "pass"),
    ("I4",  check_I4,           "mhr",            mhr,            make_I4_games,           "skip"),
    ("I4",  check_I4,           "ridge",          ridge,          make_I4_games,           "skip"),

    # I5 — bespoke_flat passes; benchmarks skip
    ("I5",  check_I5,           "bespoke_flat",   bespoke_flat,   make_I5_games,           "pass"),
    ("I5",  check_I5,           "mhr",            mhr,            make_I5_games,           "skip"),
    ("I5",  check_I5,           "ridge",          ridge,          make_I5_games,           "skip"),

    # I6 — bespoke_flat passes; benchmarks skip.
    # Ridge is skip (not xfail): in the chain construction Ridge also passes I6 because
    # Massey puts T1 just below ELITE (way above 0) and T2 just above WEAK (way below 0);
    # only blowout-score narrow-gap scenarios reveal ridge's I6 failure — that is TASK-11's scope.
    ("I6",  check_I6,           "bespoke_flat",   bespoke_flat,   make_I6_games,           "pass"),
    ("I6",  check_I6,           "mhr",            mhr,            make_I6_games,           "skip"),
    ("I6",  check_I6,           "ridge",          ridge,          make_I6_games,           "skip"),

    # I7 — bespoke_flat passes; benchmarks skip
    ("I7",  check_I7,           "bespoke_flat",   bespoke_flat,   make_I7_games,           "pass"),
    ("I7",  check_I7,           "mhr",            mhr,            make_I7_games,           "skip"),
    ("I7",  check_I7,           "ridge",          ridge,          make_I7_games,           "skip"),

    # I8 — all three models pass (determinism is table stakes)
    ("I8",  check_I8,           "bespoke_flat",   bespoke_flat,   make_I8_games,           "pass"),
    ("I8",  check_I8,           "mhr",            mhr,            make_I8_games,           "pass"),
    ("I8",  check_I8,           "ridge",          ridge,          make_I8_games,           "pass"),

    # I9 — all three models pass (convergence / unique fixed-point)
    ("I9",  check_I9,           "bespoke_flat",   bespoke_flat,   make_I9_games,           "pass"),
    ("I9",  check_I9,           "mhr",            mhr,            make_I9_games,           "pass"),
    ("I9",  check_I9,           "ridge",          ridge,          make_I9_games,           "pass"),

    # I10 — bespoke_flat passes; benchmarks skip
    ("I10", check_I10,          "bespoke_flat",   bespoke_flat,   make_I10_games,          "pass"),
    ("I10", check_I10,          "mhr",            mhr,            make_I10_games,          "skip"),
    ("I10", check_I10,          "ridge",          ridge,          make_I10_games,          "skip"),

    # I11 — bespoke_weekly passes (trend output); benchmarks skip (no trend output)
    ("I11", check_I11,          "bespoke_weekly", bespoke_weekly, make_I11_games,          "pass"),
    ("I11", check_I11,          "mhr",            mhr,            make_I11_games,          "skip"),
    ("I11", check_I11,          "ridge",          ridge,          make_I11_games,          "skip"),

    # I12 — bespoke_flat passes (attribution); benchmarks skip (no attribution)
    ("I12", check_I12,          "bespoke_flat",   bespoke_flat,   make_I12_games,          "pass"),
    ("I12", check_I12,          "mhr",            mhr,            make_I12_games,          "skip"),
    ("I12", check_I12,          "ridge",          ridge,          make_I12_games,          "skip"),

    # I13 — bespoke_weekly passes; benchmarks skip (no tier window)
    ("I13", check_I13,          "bespoke_weekly", bespoke_weekly, make_I13_blip_games,     "pass"),
    ("I13", check_I13,          "mhr",            mhr,            make_I13_blip_games,     "skip"),
    ("I13", check_I13,          "ridge",          ridge,          make_I13_blip_games,     "skip"),
]


# ---------------------------------------------------------------------------
# Parametrized test — the single pytest entry point for all (inv, model) cells
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "inv_id,check_fn,model_name,model_fn,games_fn,expect",
    MATRIX,
    ids=[f"{inv_id}::{model_name}" for inv_id, _, model_name, _, _, _ in MATRIX],
)
def test_invariant(
    inv_id: str,
    check_fn,
    model_name: str,
    model_fn: ModelFn,
    games_fn,
    expect: str,
) -> None:
    """Parametrized invariant runner — one test per (invariant, model) cell in MATRIX."""
    if expect == "skip":
        pytest.skip(reason=f"{model_name} {inv_id}: ambiguous or unsupported in minimal construction")

    games = games_fn()

    if expect == "xfail":
        # Run the check; it MUST raise AssertionError to document a known model violation.
        # We use pytest.xfail() to mark the test so that:
        #   - if AssertionError is raised (expected failure), pytest records xfail (green)
        #   - if no exception is raised (unexpected pass), pytest records XPASS and fails the suite
        # This mirrors xfail(strict=True) while keeping the mechanics in the test body.
        try:
            check_fn(model_fn, games)
        except AssertionError as exc:
            pytest.xfail(reason=f"{model_name} documented {inv_id} violation: {exc}")
        else:
            # The model unexpectedly PASSED an invariant it is supposed to fail — this is surprising
            # and we surface it as a hard failure so the MATRIX gets updated.
            pytest.fail(
                f"XPASS: {model_name} unexpectedly passed {inv_id} — update MATRIX to 'pass' if intentional"
            )
        return

    # expect == "pass": the check must succeed with no exception
    check_fn(model_fn, games)
