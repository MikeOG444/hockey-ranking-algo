"""Tests for generator/io.py — §8 JSON serialisation round-trip.

Six tests covering the full contract:

1. games_round_trip — a Dataset with only games (no groundTruth, no expect) serialises
   to camelCase JSON and deserialises back to an identical Dataset.
2. ground_truth_round_trip — a Dataset whose groundTruth list includes trajectory and tier
   fields survives the round-trip unchanged.
3. camel_case_game_fields — the serialised JSON dict uses camelCase keys (goalsTeam,
   goalsOpponent) for the game rows, not the Python snake_case names.
4. optional_fields_absent — when groundTruth and expect are not supplied, neither key
   appears in the serialised dict (no null-padding).
5. optional_expect_round_trip — when an expect payload is supplied it survives the round-
   trip byte-for-byte (dict equality, not JSON string equality — order irrelevant).
6. determinism — calling dataset_to_dict twice on the same Dataset yields an equal dict;
   the output is a pure function of the input with no hidden state.
"""

import json

import pytest

from core.game import GameRow
from generator.io import dataset_from_dict, dataset_to_dict
from generator.simulate import Dataset, TeamParams


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _single_game() -> GameRow:
    return GameRow(
        week=1,
        date="2025-09-29",
        time="10:45",
        team="T01",
        opponent="T02",
        goals_team=3,
        goals_opponent=1,
    )


def _team_params() -> TeamParams:
    return TeamParams(
        id="T01",
        attack=0.5,
        defense=0.2,
        tier=1,
        trajectory="flat",
    )


# ---------------------------------------------------------------------------
# Test 1: games-only round-trip (no optional fields)
# ---------------------------------------------------------------------------

def test_games_round_trip():
    """A games-only Dataset serialises to dict and back without loss."""
    original = Dataset(games=[_single_game()])

    d = dataset_to_dict(original, scenario="test", seed=42)
    recovered = dataset_from_dict(d)

    assert recovered.games == original.games
    assert recovered.ground_truth == []  # absent in source → empty on recovery


# ---------------------------------------------------------------------------
# Test 2: ground_truth round-trip
# ---------------------------------------------------------------------------

def test_ground_truth_round_trip():
    """A Dataset whose groundTruth includes tier and trajectory survives unchanged."""
    tp = _team_params()
    original = Dataset(games=[_single_game()], ground_truth=[tp])

    d = dataset_to_dict(original, scenario="gt_test", seed=7)
    recovered = dataset_from_dict(d)

    assert len(recovered.ground_truth) == 1
    rt = recovered.ground_truth[0]
    assert rt.id == tp.id
    assert rt.attack == pytest.approx(tp.attack)
    assert rt.defense == pytest.approx(tp.defense)
    assert rt.tier == tp.tier
    assert rt.trajectory == tp.trajectory


# ---------------------------------------------------------------------------
# Test 3: camelCase game field names in the serialised dict
# ---------------------------------------------------------------------------

def test_camel_case_game_fields():
    """Games are serialised with camelCase keys per §8 schema."""
    d = dataset_to_dict(Dataset(games=[_single_game()]), scenario="camel", seed=0)

    assert "games" in d
    game_dict = d["games"][0]

    # Required camelCase keys from §8
    assert "week" in game_dict
    assert "date" in game_dict
    assert "time" in game_dict
    assert "team" in game_dict
    assert "opponent" in game_dict
    assert "goalsTeam" in game_dict        # camelCase, not goals_team
    assert "goalsOpponent" in game_dict    # camelCase, not goals_opponent

    # Snake_case keys must NOT appear
    assert "goals_team" not in game_dict
    assert "goals_opponent" not in game_dict

    # Values must match
    assert game_dict["goalsTeam"] == 3
    assert game_dict["goalsOpponent"] == 1


# ---------------------------------------------------------------------------
# Test 4: optional fields absent when not provided
# ---------------------------------------------------------------------------

def test_optional_fields_absent():
    """groundTruth and expect must not appear when not supplied (no null padding)."""
    d = dataset_to_dict(Dataset(games=[_single_game()]), scenario="s", seed=1)

    assert "groundTruth" not in d
    assert "expect" not in d


# ---------------------------------------------------------------------------
# Test 5: optional expect payload round-trips
# ---------------------------------------------------------------------------

def test_optional_expect_round_trip():
    """An expect payload serialises into the dict and is recovered verbatim."""
    expect_payload = {
        "invariants": ["I1", "I3"],
        "assertions": [{"type": "ratesBelow", "a": "T_padded", "b": "T_gauntlet"}],
    }
    d = dataset_to_dict(
        Dataset(games=[_single_game()]),
        scenario="expect_test",
        seed=99,
        expect=expect_payload,
    )

    # Present in serialised form
    assert d["expect"] == expect_payload

    # Survives round-trip through JSON (catches any non-serialisable types)
    json_str = json.dumps(d)
    recovered_d = json.loads(json_str)
    # Verify round-trip through JSON text works (catches any non-serialisable types).
    # dataset_from_dict is called here to confirm it doesn't raise on valid input;
    # games/ground_truth fidelity is covered by tests 1 and 2.
    dataset_from_dict(recovered_d)
    assert recovered_d["expect"] == expect_payload


# ---------------------------------------------------------------------------
# Test 6: determinism — same input → same output, no hidden state
# ---------------------------------------------------------------------------

def test_determinism():
    """dataset_to_dict is a pure function: two calls on the same Dataset are equal."""
    ds = Dataset(games=[_single_game()], ground_truth=[_team_params()])

    d1 = dataset_to_dict(ds, scenario="det", seed=5)
    d2 = dataset_to_dict(ds, scenario="det", seed=5)

    assert d1 == d2
