"""§8 JSON serialisation for Dataset objects (brief §8).

Converts between the internal Dataset / GameRow / TeamParams dataclasses and the
camelCase JSON dict schema defined in brief §8.  This is the only place where
field-name mapping lives — callers should never hand-roll dict construction.

Design notes
------------
- Field names in the JSON follow camelCase (goalsTeam, goalsOpponent, trueAttack …)
  because that is the brief's wire schema.  Python internals remain snake_case.
- groundTruth and expect are *optional*: they are only written when present / non-empty
  and are only reconstructed when present in the source dict.  No null-padding ever.
- All conversions are pure functions with no side effects, so determinism (I8) is free.
"""

from __future__ import annotations

from typing import Any

from core.game import GameRow
from generator.simulate import Dataset, TeamParams


# ---------------------------------------------------------------------------
# Internal helpers — game row ↔ dict
# ---------------------------------------------------------------------------

def _game_to_dict(row: GameRow) -> dict[str, Any]:
    """Serialise one GameRow to its §8 camelCase representation."""
    return {
        "week": row.week,
        "date": row.date,
        "time": row.time,
        "team": row.team,
        "opponent": row.opponent,
        "goalsTeam": row.goals_team,       # camelCase per §8
        "goalsOpponent": row.goals_opponent,  # camelCase per §8
    }


def _game_from_dict(d: dict[str, Any]) -> GameRow:
    """Deserialise one §8 camelCase game dict back to an immutable GameRow."""
    return GameRow(
        week=int(d["week"]),
        date=str(d["date"]),
        time=str(d["time"]),
        team=str(d["team"]),
        opponent=str(d["opponent"]),
        goals_team=int(d["goalsTeam"]),
        goals_opponent=int(d["goalsOpponent"]),
    )


# ---------------------------------------------------------------------------
# Internal helpers — TeamParams ↔ dict
# ---------------------------------------------------------------------------

def _team_to_dict(tp: TeamParams) -> dict[str, Any]:
    """Serialise one TeamParams to its §8 camelCase groundTruth entry."""
    d: dict[str, Any] = {
        "id": tp.id,
        "trueAttack": tp.attack,
        "trueDefense": tp.defense,
        "trueRating": tp.rating,         # derived, included for reader convenience
        "trajectory": tp.trajectory,
    }
    # tier is optional at the data-model level (TeamParams.tier is None by default)
    if tp.tier is not None:
        d["trueTier"] = tp.tier
    return d


def _team_from_dict(d: dict[str, Any]) -> TeamParams:
    """Deserialise one §8 groundTruth entry back to TeamParams."""
    return TeamParams(
        id=str(d["id"]),
        attack=float(d["trueAttack"]),
        defense=float(d["trueDefense"]),
        tier=int(d["trueTier"]) if "trueTier" in d else None,
        trajectory=str(d.get("trajectory", "flat")),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def dataset_to_dict(
    dataset: Dataset,
    *,
    scenario: str,
    seed: int,
    world_model: str = "dixon_coles",
    config: dict[str, Any] | None = None,
    expect: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialise *dataset* to a §8-compliant JSON-ready dict.

    Required metadata (scenario, seed) is provided by the caller because Dataset
    itself is a pure data object without scenario context.

    Optional fields (groundTruth, expect) are written only when non-empty / non-None,
    keeping the dict free of null-padding.
    """
    if config is None:
        config = {"tierCount": "auto", "tierMethod": "natural_gaps", "freezeWindowWeeks": 4}

    result: dict[str, Any] = {
        "scenario": scenario,
        "seed": seed,
        "worldModel": world_model,
        "config": config,
        "games": [_game_to_dict(g) for g in dataset.games],
    }

    # groundTruth only if we have it
    if dataset.ground_truth:
        result["groundTruth"] = {
            "teams": [_team_to_dict(t) for t in dataset.ground_truth]
        }

    # expect only if supplied
    if expect is not None:
        result["expect"] = expect

    return result


def dataset_from_dict(d: dict[str, Any]) -> Dataset:
    """Deserialise a §8 JSON dict back to a Dataset.

    groundTruth is optional in the schema; if absent, Dataset.ground_truth is an
    empty list (the Dataset default).  The expect payload is metadata only — it is
    not stored on Dataset (which is a pure Level-0 container) and is preserved in
    the raw dict for the caller to inspect if needed.
    """
    games = [_game_from_dict(g) for g in d.get("games", [])]

    ground_truth: list[TeamParams] = []
    if "groundTruth" in d and d["groundTruth"]:
        ground_truth = [_team_from_dict(t) for t in d["groundTruth"].get("teams", [])]

    return Dataset(games=games, ground_truth=ground_truth)
