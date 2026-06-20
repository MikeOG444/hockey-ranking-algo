"""Cross-opponent invariants for the bespoke model (brief §4 I6, I7, I10, I12; memo §1.3-§1.4, §7).

These exercise the schedule term `alpha * R_opp` — the model's only cross-opponent signal — and
the per-game attribution that reconciles back to the rating. Where I1-I5 isolate the floor by
fixing the opponent, these tests vary the opponent and prove the schedule channel does the right
thing without ever touching `base` (the floor stays structural).
"""

import pytest

from core.game import GameRow
from models.bespoke import BespokeParams, CreditBreakdown, per_game_credit, rate

P = BespokeParams()  # strawman defaults (memo §9); alpha pinned by I6 (memo Q1)


def game(team: str, opponent: str, gf: int, ga: int, week: int = 1) -> GameRow:
    """Hand-built Level-0 row. date/time are inert here (rate() ignores them today); week is
    carried for realism even though recency weighting is not online until TASK-06."""
    return GameRow(
        week=week,
        date="2025-10-06",
        time="10:45",
        team=team,
        opponent=opponent,
        goals_team=gf,
        goals_opponent=ga,
    )


# --- I6: tier x margin interaction (the owner's canonical example, memo §1.4) --------------

# Centered ratings from the memo's worked example: an elite opponent and a bottom-of-field one.
R_ELITE = 4.0
R_WEAK = -2.0


def test_I6_close_loss_to_elite_beats_close_win_over_weak():
    """I6 (brief §82): a 1-goal LOSS to a top-tier team rates strictly better than a 1-goal WIN
    over a bottom-of-field team. The schedule term carries this cross-opponent comparison; it is
    decided by alpha * (R_elite - R_weak) vs the base gap (W - L). With the strawman alpha=0.5 the
    canonical +4 / -2 example is exactly a tie, so alpha is pinned just above it (memo Q1: alpha is
    derived from I6, not guessed).

    SCOPE: this is the *credit-level* proof on per_game_credit (in scope for TASK-01). The
    *end-to-end* I6 — feeding Level-0 games through rate() and asserting the ordering on CONVERGED
    ratings — is Scenario 7 / TASK-11. Note (invariant-auditor, TASK-01): centering compresses the
    converged spread, so an 'elite' team that only beat an average field may not reach a gap of 6;
    end-to-end I6 holds where the elite team beat a genuinely strong slate (the Scenario-7 setup).
    TASK-11 must re-derive alpha against the reachable gap, not this hand-picked one. See memo Q1."""
    close_loss_to_elite = per_game_credit(0, 1, opp_rating=R_ELITE, opp_tier=1, params=P).total
    close_win_over_weak = per_game_credit(1, 0, opp_rating=R_WEAK, opp_tier=5, params=P).total
    assert close_loss_to_elite > close_win_over_weak


# --- I7: underperformance never flips the result order (brief §83, memo §1.2) -------------


def test_I7_margin_helps_but_never_flips_a_beaten_opponent():
    """I7: a strong team that wins every game by only 1 goal *gains less* than an otherwise-identical
    team that wins by 3 — but it must never fall below a team it actually beat.

    Schedule-matched construction: CLOSER and BLOWOUT play the SAME three opponents (O1-O3) and never
    each other, so their schedule terms are identical and the ONLY difference is `marginAdj` (the
    bonus, never `base`). The by-3 team must therefore rate >= the by-1 team, yet the by-1 team must
    still out-rate every opponent it beat — the floor cannot be flipped by withheld margin bonus."""
    opponents = ["O1", "O2", "O3"]
    games = []
    for o in opponents:
        games.append(game("CLOSER", o, 1, 0))   # wins by exactly 1 (close: zero margin bonus)
        games.append(game("BLOWOUT", o, 3, 0))  # wins by 3 (earns the margin bonus)
    res = rate(games)

    # The blowout team gains at least as much as the close-winning team (margin helps, never hurts).
    assert res.ratings["BLOWOUT"] >= res.ratings["CLOSER"]
    # ...but the close-winning team still ranks above every team it beat — the result floor holds.
    for o in opponents:
        assert res.ratings["CLOSER"] > res.ratings[o]


# --- I10: stale-opponent float, the "Dallas" case (brief §86, memo §1.3) ------------------


def test_I10_beating_an_exposed_team_does_not_inflate_the_beneficiary():
    """I10: credit for beating a team reflects its CURRENT (converged) strength, not an inflated
    early record. The solve is a single batch over all games, so an opponent's schedule contribution
    always uses its final rating.

    Construction: EXPOSED beats two weak teams (a glossy early record) but then loses to two strong
    teams — its converged rating is low. GENUINE has the same two weak-team wins but ALSO beats the
    two strong teams — genuinely strong, high converged rating. Two otherwise-identical beneficiaries
    each win one close game: BEN_STALE beats EXPOSED, BEN_GEN beats GENUINE. Because the schedule
    term floats with the opponent's converged rating, BEN_GEN must out-rate BEN_STALE — the
    stale-beneficiary does not coast on EXPOSED's early glory."""
    games = [
        # EXPOSED: pads its record on weak teams, then is exposed by the strong ones.
        game("EXPOSED", "W1", 5, 0),
        game("EXPOSED", "W2", 5, 0),
        game("S1", "EXPOSED", 5, 0),
        game("S2", "EXPOSED", 5, 0),
        # GENUINE: same weak-team wins, but beats the strong teams too -> truly strong.
        game("GENUINE", "W3", 5, 0),
        game("GENUINE", "W4", 5, 0),
        game("GENUINE", "S1", 5, 0),
        game("GENUINE", "S2", 5, 0),
        # Two beneficiaries, identical but for who they beat (an exposed team vs a genuine one).
        game("BEN_STALE", "EXPOSED", 1, 0),
        game("BEN_GEN", "GENUINE", 1, 0),
    ]
    res = rate(games)

    # EXPOSED re-rated below GENUINE despite the identical weak-team wins — the float worked.
    assert res.ratings["GENUINE"] > res.ratings["EXPOSED"]
    # And the beneficiary of beating the genuinely strong team out-rates the one who beat the
    # exposed team: schedule credit tracks current strength, not the stale early record.
    assert res.ratings["BEN_GEN"] > res.ratings["BEN_STALE"]


# --- I12: per-game attribution reconciles to the rating (brief §88, memo §7) --------------

# A small connected season covering every credit shape: win-by-3, close win, tie, blowout,
# close loss, deep loss. This exercises all three attribution drivers at once.
_ATTR_GAMES = [
    game("A", "B", 3, 0),  # A: win by 3 (margin bonus)
    game("A", "C", 1, 0),  # A: close win (no bonus)
    game("A", "D", 2, 2),  # A/D: tie (no adjustment)
    game("B", "C", 5, 0),  # B: blowout win (capped bonus)
    game("B", "D", 0, 1),  # B: close loss (no penalty)
    game("C", "D", 0, 4),  # C: deep loss (penalty)
]


def test_I12_attribution_exposes_the_three_named_drivers():
    """I12 / explainability: per_game_attribution gives, for each team, one CreditBreakdown per game
    carrying the three named drivers (base, margin_adj, schedule_term). One entry per game played."""
    res = rate(_ATTR_GAMES, lam=0.05)
    games_played = {"A": 3, "B": 3, "C": 3, "D": 3}
    for team, n in games_played.items():
        breakdowns = res.per_game_attribution[team]
        assert len(breakdowns) == n
        assert all(isinstance(b, CreditBreakdown) for b in breakdowns)


def test_I12_attribution_reconciles_to_each_rating():
    """I12: the attribution sums back to the rating. By the solve's own algebra,
    `rating_i == (1 - lam) * mean_g(breakdown.total) - center_offset` exactly. This can only hold if
    each breakdown's schedule_term used the opponents' CONVERGED ratings, so the single reconciliation
    check also proves the attribution is built from final (not stale) ratings."""
    lam = 0.05
    res = rate(_ATTR_GAMES, lam=lam)
    for team, rating in res.ratings.items():
        breakdowns = res.per_game_attribution[team]
        mean_total = sum(b.total for b in breakdowns) / len(breakdowns)
        reconciled = (1.0 - lam) * mean_total - res.center_offset
        assert reconciled == pytest.approx(rating, abs=1e-9)
