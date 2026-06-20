"""MHR replica tests: determinism (I8), convergence (I9), gross rank recovery, and I1 violation.

The MHR replica is a *benchmark* — it is expected to fail some fairness invariants.
Test 5 here documents the specific I1 violation: result ordering can flip when season-wide AGD
is overwhelmed by schedule asymmetry, with no per-game result floor to prevent it.
"""

import pytest

from core.game import GameRow
from generator.simulate import Matchup, TeamParams, WorldConfig, simulate
from models.bespoke import RateResult
from models.mhr_replica import GD_CAP, rate

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


def test_rate_returns_a_rating_per_team():
    """rate() returns a RateResult with one rating per team appearing in the games."""
    res = rate(round_robin_dataset(seed=1, repeats=4).games)
    assert isinstance(res, RateResult)
    assert set(res.ratings) == TEAMS


def test_I8_deterministic_and_order_independent():
    """I8: same games run twice are byte-identical; shuffling input order changes nothing."""
    games = round_robin_dataset(seed=1, repeats=4).games
    twice_a = rate(games).ratings
    twice_b = rate(games).ratings
    shuffled = rate(list(reversed(games))).ratings
    assert twice_a == twice_b == shuffled


def test_I9_converges_from_different_starting_points():
    """I9: a unique fixed point — different inits reach the same ratings (within tolerance)."""
    games = round_robin_dataset(seed=2, repeats=4).games
    from_zero = rate(games, init={t: 0.0 for t in TEAMS}).ratings
    from_wild = rate(games, init={"STRONG": 5.0, "MID": -3.0, "WEAK": 2.0}).ratings
    for t in TEAMS:
        assert from_zero[t] == pytest.approx(from_wild[t], abs=1e-6)


def test_recovers_gross_strength_order():
    """Over enough games the recovered order matches planted truth: STRONG > MID > WEAK.
    MHR need only recover gross order (it is allowed to be weaker than bespoke here)."""
    r = rate(round_robin_dataset(seed=5, repeats=30).games).ratings
    assert r["STRONG"] > r["MID"] > r["WEAK"]


def test_gd_cap_applied():
    """GD_CAP=7: a result beyond the cap earns the same credit as one exactly at it.
    This verifies brief §3.1 ('capped ±7') — blowouts beyond 7 goals add nothing."""
    at_cap   = [hand_game("A", "B", gf=GD_CAP,     ga=0)]
    over_cap = [hand_game("A", "B", gf=GD_CAP + 3, ga=0)]
    r_cap  = rate(at_cap).ratings
    r_over = rate(over_cap).ratings
    assert r_cap["A"] == pytest.approx(r_over["A"], abs=1e-12)


def test_I1_violation_documented():
    """MHR violates I1 — construct the exact case and assert the replica reproduces the flaw.

    Setup: 4 teams — A, B, C (the shared opponent), STRONG.
      - A beats  C    2–1   (A wins vs C, GD = +1)
      - B loses  to C 1–2   (B loses vs C, GD = -1)
      - A loses  to STRONG 0–7  (huge loss, GD = -7)
      - B beats  STRONG  7–0   (huge win,  GD = +7)

    A and B each played exactly the same two opponents (C and STRONG) with the same margins.
    A won vs C; B lost vs C. By I1, A must outrate B.

    AGD_A = (+1 + -7) / 2 = -3;  AGD_B = (-1 + +7) / 2 = +3.
    At the fixed point (see decision-memo §8 worked example):
        r_A = 3*(lam-1),  r_B = 3*(1-lam)  →  r_B > r_A.

    MHR has no per-game result floor; the blowout AGD difference swamps the win-vs-C credit.
    The bespoke model's `base(result)` floor prevents exactly this flip.
    """
    games = [
        hand_game("A", "C",      gf=2, ga=1),   # A wins  vs C by 1
        hand_game("B", "C",      gf=1, ga=2),   # B loses vs C by 1
        hand_game("A", "STRONG", gf=0, ga=7),   # A loses to STRONG by 7 (at GD_CAP)
        hand_game("B", "STRONG", gf=7, ga=0),   # B beats  STRONG by 7 (at GD_CAP)
    ]
    r = rate(games).ratings
    # Despite A winning vs C and B losing vs C (same opponent, same margin), MHR gives B > A.
    assert r["B"] > r["A"], (
        f"Expected I1 violation: B (lost to C) should outrate A (won vs C) in MHR, "
        f"but got r[A]={r['A']:.4f} r[B]={r['B']:.4f}"
    )
