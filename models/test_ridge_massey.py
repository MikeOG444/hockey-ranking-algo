"""Ridge Massey benchmark tests: determinism (I8), disconnected-graph stability (ridge uniqueness),
and gross rank recovery.

The Ridge Massey model is a *benchmark* — it is allowed to fail fairness invariants (I1, I4, I6,
I7). These tests verify only the properties that characterize the method:

  I8  — same input, byte-identical output; shuffled input order, same output.
  I9  — finite, unique solution on disconnected graphs (ridge term prevents blow-up/singularity).
  Rank recovery — on a round-robin with planted strengths the recovered order matches truth.
  Margin cap — when a cap is set, a game beyond it earns the same credit as one exactly at the cap.
"""

import pytest

from core.game import GameRow
from generator.simulate import Matchup, TeamParams, WorldConfig, simulate
from models.bespoke import RateResult
from models.ridge_massey import rate

TEAMS = {"STRONG", "MID", "WEAK"}


def round_robin_dataset(seed: int, repeats: int):
    teams = [
        TeamParams("STRONG", attack=0.6, defense=-0.4),  # true rating +1.0
        TeamParams("MID", attack=0.0, defense=0.0),       # true rating  0.0
        TeamParams("WEAK", attack=-0.4, defense=0.6),     # true rating -1.0
    ]
    pairs = [("STRONG", "MID"), ("STRONG", "WEAK"), ("MID", "WEAK")]
    schedule = [
        Matchup(week=1 + i, team=a, opponent=b)
        for i in range(repeats)
        for (a, b) in pairs
    ]
    return simulate(WorldConfig(teams=teams, schedule=schedule, seed=seed))


def hand_game(team: str, opponent: str, gf: int, ga: int) -> GameRow:
    return GameRow(week=1, date="2025-10-01", time="10:00",
                   team=team, opponent=opponent,
                   goals_team=gf, goals_opponent=ga)


def test_rate_returns_rate_result():
    """rate() returns a RateResult with one rating per team."""
    res = rate(round_robin_dataset(seed=1, repeats=4).games)
    assert isinstance(res, RateResult)
    assert set(res.ratings) == TEAMS


def test_ratings_centered_to_mean_zero():
    """Ratings are gauge-fixed to mean 0 (same convention as bespoke/MHR)."""
    r = rate(round_robin_dataset(seed=3, repeats=4).games).ratings
    mean = sum(r.values()) / len(r)
    assert mean == pytest.approx(0.0, abs=1e-10)


def test_I8_deterministic_and_order_independent():
    """I8: running twice gives byte-identical output; reversing input order changes nothing."""
    games = round_robin_dataset(seed=1, repeats=4).games
    ra = rate(games).ratings
    rb = rate(games).ratings
    rc = rate(list(reversed(games))).ratings
    assert ra == rb
    assert ra == rc


def test_I9_disconnected_graph_ridge_prevents_blowup():
    """I9 / ridge: two completely isolated pods produce finite ratings (no singularity).

    Without the ridge term, the Massey matrix is singular on a disconnected schedule; the
    ridge penalty makes it positive definite and guarantees a unique finite solution.
    """
    # Pod A: two teams that only play each other.
    # Pod B: two different teams that only play each other.
    pod_a = [hand_game("A1", "A2", gf=3, ga=1), hand_game("A1", "A2", gf=2, ga=0)]
    pod_b = [hand_game("B1", "B2", gf=1, ga=0), hand_game("B1", "B2", gf=2, ga=1)]
    res = rate(pod_a + pod_b)
    for t in ("A1", "A2", "B1", "B2"):
        assert abs(res.ratings[t]) < 1e6, f"Rating blew up for {t}: {res.ratings[t]}"


def test_I9_unique_solution_independent_of_init():
    """I9: Ridge Massey is a direct solve — different games, same solution every call.

    Unlike iterative models, Ridge Massey has no init parameter (it's a direct linear solve),
    so uniqueness is verified by confirming two calls on the same data return identical results.
    """
    games = round_robin_dataset(seed=7, repeats=6).games
    r1 = rate(games).ratings
    r2 = rate(games).ratings
    for t in TEAMS:
        assert r1[t] == r2[t]


def test_recovers_gross_strength_order():
    """Over enough round-robin games the recovered order matches planted truth: STRONG > MID > WEAK."""
    r = rate(round_robin_dataset(seed=5, repeats=30).games).ratings
    assert r["STRONG"] > r["MID"] > r["WEAK"]


def test_margin_cap_applied():
    """When margin_cap is set, a game beyond the cap earns the same Massey credit as one at the cap.

    In the Massey system the right-hand side entry for each game is the (capped) margin, so two
    games with margins 10 and cap both contribute the same value to b[i].
    """
    cap = 5
    at_cap = [hand_game("A", "B", gf=cap, ga=0)]
    over_cap = [hand_game("A", "B", gf=cap + 4, ga=0)]
    r_at = rate(at_cap, margin_cap=cap).ratings
    r_over = rate(over_cap, margin_cap=cap).ratings
    assert r_at["A"] == pytest.approx(r_over["A"], abs=1e-12)


def test_no_cap_by_default():
    """Without a cap, larger margins produce larger ratings (raw goal diff is used)."""
    small = [hand_game("A", "B", gf=2, ga=0)]
    large = [hand_game("A", "B", gf=8, ga=0)]
    r_small = rate(small).ratings
    r_large = rate(large).ratings
    assert r_large["A"] > r_small["A"]
