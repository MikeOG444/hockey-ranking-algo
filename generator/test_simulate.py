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


# ---------------------------------------------------------------------------
# Trajectory tests (TASK-04)
# ---------------------------------------------------------------------------

import numpy as np  # noqa: E402  (grouped for clarity)


def _multi_week_config(
    team_traj: str,
    weeks: list[int],
    reps_per_week: int,
    seed: int,
) -> WorldConfig:
    """Build a config with one team whose trajectory varies vs a flat benchmark."""
    actor = TeamParams(id="ACTOR", attack=0.0, defense=0.0, trajectory=team_traj)
    bench = TeamParams(id="BENCH", attack=0.0, defense=0.0, trajectory="flat")
    schedule = [
        Matchup(week=wk, team="ACTOR", opponent="BENCH")
        for wk in weeks
        for _ in range(reps_per_week)
    ]
    return WorldConfig(teams=[actor, bench], schedule=schedule, seed=seed, mu=math.log(3.0))


def test_flat_trajectory_byte_identical_to_default():
    """flat trajectory must not change the scorelines vs the unmodified default (regression I8)."""
    config_flat = WorldConfig(
        teams=[
            TeamParams(id="A", attack=0.5, defense=-0.5, trajectory="flat"),
            TeamParams(id="B", attack=-0.5, defense=0.5, trajectory="flat"),
        ],
        schedule=[Matchup(week=1, team="A", opponent="B") for _ in range(20)],
        seed=7,
        mu=math.log(3.0),
    )
    config_default = WorldConfig(
        teams=[
            TeamParams(id="A", attack=0.5, defense=-0.5),  # trajectory defaults to "flat"
            TeamParams(id="B", attack=-0.5, defense=0.5),
        ],
        schedule=[Matchup(week=1, team="A", opponent="B") for _ in range(20)],
        seed=7,
        mu=math.log(3.0),
    )
    assert simulate(config_flat).games == simulate(config_default).games


def test_rising_team_scores_more_in_later_weeks():
    """A rising team's mean goals improve over weeks; early-week mean < late-week mean."""
    config = _multi_week_config("rising", weeks=[1, 2, 3, 4, 5], reps_per_week=300, seed=42)
    ds = simulate(config)

    early = np.mean([g.goals_team for g in ds.games if g.week == 1])
    late = np.mean([g.goals_team for g in ds.games if g.week == 5])
    assert late > early, f"expected late ({late:.3f}) > early ({early:.3f}) for rising team"


def test_falling_team_scores_less_in_later_weeks():
    """A falling team's mean goals decrease over weeks."""
    config = _multi_week_config("falling", weeks=[1, 2, 3, 4, 5], reps_per_week=300, seed=42)
    ds = simulate(config)

    early = np.mean([g.goals_team for g in ds.games if g.week == 1])
    late = np.mean([g.goals_team for g in ds.games if g.week == 5])
    assert late < early, f"expected late ({late:.3f}) < early ({early:.3f}) for falling team"


def test_blip_perturbs_only_target_week():
    """blip@w3 boosts goals only in week 3; weeks 2 and 4 stay at baseline."""
    config = _multi_week_config("blip@w3", weeks=[2, 3, 4], reps_per_week=400, seed=11)
    ds = simulate(config)

    wk2 = np.mean([g.goals_team for g in ds.games if g.week == 2])
    wk3 = np.mean([g.goals_team for g in ds.games if g.week == 3])
    wk4 = np.mean([g.goals_team for g in ds.games if g.week == 4])

    assert wk3 > wk2, f"blip week ({wk3:.3f}) should exceed pre-blip ({wk2:.3f})"
    assert wk3 > wk4, f"blip week ({wk3:.3f}) should exceed post-blip ({wk4:.3f})"
    # Weeks 2 and 4 are both baseline — gap between them should be small vs the blip lift
    assert abs(wk2 - wk4) < (wk3 - wk2), (
        f"non-blip weeks should be similar: |{wk2:.3f}-{wk4:.3f}|={abs(wk2-wk4):.3f}"
        f" vs blip lift {wk3-wk2:.3f}"
    )


def test_trajectory_reproducible_across_runs():
    """Trajectory simulation is deterministic (I8): same seed + trajectory -> same games."""
    config = _multi_week_config("rising", weeks=[1, 2, 3], reps_per_week=10, seed=99)
    a = simulate(config)
    b = simulate(config)
    assert a.games == b.games


def test_week_params_exported_for_harness():
    """week_params is importable and returns week-1 baseline as the team's raw attack/defense."""
    from generator.simulate import week_params  # noqa: PLC0415

    t = TeamParams(id="T", attack=0.3, defense=0.1, trajectory="flat")
    atk, dfn = week_params(t, week=1)
    assert atk == t.attack and dfn == t.defense
