"""Level-0 data contract tests (brief §5).

Level 0 is the ONLY true input: one row per game, outcome inferred from goals,
no home/away, nothing derived stored as a primary field.
"""

import dataclasses

import pytest

from core.game import GameRow

# A minimal, valid Level-0 row used across tests.
def make_row(goals_team: int, goals_opponent: int) -> GameRow:
    return GameRow(
        week=1,
        date="2025-10-03",
        time="10:45",
        team="T01",
        opponent="T07",
        goals_team=goals_team,
        goals_opponent=goals_opponent,
    )


@pytest.mark.parametrize(
    "gf, ga, expected",
    [
        (5, 2, "W"),  # more goals than opponent -> win
        (2, 5, "L"),  # fewer goals -> loss
        (3, 3, "T"),  # equal goals -> tie
        (1, 0, "W"),  # a 1-goal win is still a win
        (0, 1, "L"),  # a 1-goal loss is still a loss
        (0, 0, "T"),  # scoreless tie
    ],
)
def test_outcome_inferred_from_goals(gf, ga, expected):
    assert make_row(gf, ga).outcome == expected


def test_level0_fields_are_exactly_the_contract():
    """The schema is locked: week,date,time,team,opponent,goals_team,goals_opponent.
    No home/away/venue, and outcome/result is NOT a stored field — it is inferred."""
    field_names = {f.name for f in dataclasses.fields(GameRow)}
    assert field_names == {
        "week",
        "date",
        "time",
        "team",
        "opponent",
        "goals_team",
        "goals_opponent",
    }
    # Explicitly forbidden by the brief — these must never exist on a Level-0 row.
    for forbidden in ("home", "away", "venue", "outcome", "result"):
        assert forbidden not in field_names


def test_row_is_immutable():
    """Determinism (I8): observed inputs are frozen; nothing mutates them in place."""
    row = make_row(5, 2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.goals_team = 9  # type: ignore[misc]
