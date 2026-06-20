"""Generator tests (brief §6, §8): config -> Level-0 rows + hidden ground truth.

The generator emits ONLY Level-0 rows plus a hidden ground-truth key (true attack/defense/
rating/tier/trajectory). Levels 1-3 are derived by the harness, never emitted — that keeps
the test honest. Every dataset is a fixed (config, seed) and is fully reproducible.
"""

import math

from core.aggregate import aggregate_team
from core.game import GameRow
from generator.simulate import Matchup, TeamParams, WorldConfig, simulate


def test_team_rating_is_attack_minus_defense():
    t = TeamParams(id="T01", attack=0.6, defense=0.2)
    assert t.rating == 0.6 - 0.2


def two_team_config(seed: int, repeats: int) -> WorldConfig:
    strong = TeamParams(id="STRONG", attack=0.5, defense=-0.5)  # rating +1.0
    weak = TeamParams(id="WEAK", attack=-0.5, defense=0.5)      # rating -1.0
    schedule = [Matchup(week=1 + (i // 5), team="STRONG", opponent="WEAK") for i in range(repeats)]
    return WorldConfig(teams=[strong, weak], schedule=schedule, mu=math.log(3.0), seed=seed)


def test_emits_one_level0_row_per_scheduled_game():
    ds = simulate(two_team_config(seed=1, repeats=10))
    assert len(ds.games) == 10
    assert all(isinstance(g, GameRow) for g in ds.games)
    g = ds.games[0]
    assert g.team == "STRONG" and g.opponent == "WEAK"


def test_same_config_and_seed_is_reproducible():
    """Determinism (I8): identical config+seed -> identical games, byte for byte."""
    a = simulate(two_team_config(seed=99, repeats=20))
    b = simulate(two_team_config(seed=99, repeats=20))
    assert a.games == b.games


def test_different_seed_changes_the_draws():
    a = simulate(two_team_config(seed=1, repeats=20))
    b = simulate(two_team_config(seed=2, repeats=20))
    assert a.games != b.games


def test_ground_truth_key_is_carried_through():
    ds = simulate(two_team_config(seed=1, repeats=4))
    gt = {t.id: t for t in ds.ground_truth}
    assert gt["STRONG"].rating == 1.0 and gt["WEAK"].rating == -1.0


def test_stronger_team_outscores_weaker_over_repeats():
    """The world produces signal aligned with true ratings: across many games the higher-
    rated team has a clearly positive goal differential. (Recovered via the Level-1 aggregate.)"""
    ds = simulate(two_team_config(seed=5, repeats=300))
    strong = aggregate_team(ds.games, "STRONG")
    assert strong.goal_diff > 0
    assert strong.w > strong.l


def test_dates_are_synthesized_deterministically_from_week():
    ds = simulate(two_team_config(seed=1, repeats=10))
    # Two games in the same week share a date; later weeks are strictly later.
    wk1 = next(g for g in ds.games if g.week == 1)
    wk2 = next(g for g in ds.games if g.week == 2)
    assert wk1.date < wk2.date
