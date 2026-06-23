"""Tests for ingest.mhr_loader — written test-first per CLAUDE.md §2 (TDD).

Pure-unit tests cover the four field transforms and the dedup rules in isolation.
End-to-end tests exercise the full load on the vendored raw file and assert the
validated-count oracle from the task spec.
"""
import json
import datetime
from pathlib import Path

import pytest

# Path to the vendored raw dump — committed so tests are reproducible without
# an external filesystem dependency.
RAW_PATH = (
    Path(__file__).parent.parent
    / "data/real/raw/mhr-teams-games-2025-a2-v123-top50.json"
)


# ---------------------------------------------------------------------------
# Pure-unit tests — no file I/O, no dependency on vendored data
# ---------------------------------------------------------------------------


def test_infer_year():
    from ingest.mhr_loader import infer_year

    assert infer_year("Sep") == 2025
    assert infer_year("Dec") == 2025
    assert infer_year("Aug") == 2025
    # Jan–Jul boundary → 2026
    assert infer_year("Jan") == 2026
    assert infer_year("Jul") == 2026
    assert infer_year("Mar") == 2026


def test_parse_date_to_iso():
    from ingest.mhr_loader import parse_date

    # Sep 5 → 2025 (Aug–Dec)
    assert parse_date("Sep 5") == datetime.date(2025, 9, 5)
    # Jan 3 → 2026 (Jan–Jul)
    assert parse_date("Jan 3") == datetime.date(2026, 1, 3)
    # Aug 15 → 2025
    assert parse_date("Aug 15") == datetime.date(2025, 8, 15)
    # Dec 31 → 2025
    assert parse_date("Dec 31") == datetime.date(2025, 12, 31)
    # Mar 7 → 2026
    assert parse_date("Mar 7") == datetime.date(2026, 3, 7)


def test_week_seam():
    from ingest.mhr_loader import week_of

    # 2025-09-09 (Tue) is the last day of the long week-1 bucket
    assert week_of(datetime.date(2025, 9, 9)) == 1
    # 2025-09-10 (Wed) is the first day of week 2
    assert week_of(datetime.date(2025, 9, 10)) == 2
    # 2025-09-16 (Tue) — last day of week 2
    assert week_of(datetime.date(2025, 9, 16)) == 2
    # 2025-09-17 (Wed) — first day of week 3
    assert week_of(datetime.date(2025, 9, 17)) == 3
    # Aug dates fall in the long week-1 opening bucket
    assert week_of(datetime.date(2025, 8, 1)) == 1
    assert week_of(datetime.date(2025, 8, 22)) == 1
    # Feb 2026: 2026-02-04 (Wed) is day 147 from Sep 10 → 147//7=21 → week 23
    assert week_of(datetime.date(2026, 2, 4)) == 23
    # 2026-02-10 (Tue) — same Wed→Tue window as Feb 4 → still week 23
    assert week_of(datetime.date(2026, 2, 10)) == 23
    # 2026-02-11 (Wed) — next window → week 24
    assert week_of(datetime.date(2026, 2, 11)) == 24


def test_normalize_time():
    from ingest.mhr_loader import normalize_time

    assert normalize_time("10:19 am") == "10:19"
    assert normalize_time("6:26 pm") == "18:26"
    # 12:00 am = midnight
    assert normalize_time("12:00 am") == "00:00"
    # 12:30 pm = noon + 30 min
    assert normalize_time("12:30 pm") == "12:30"
    # empty string → treat as 00:00 (the 20 rows with no time in raw data)
    assert normalize_time("") == "00:00"


def test_dedup_collapses_mirrored_pair():
    """Two mirrored rows for one intra game → one canonical row (team = min of pair)."""
    from ingest.mhr_loader import load_games

    raw = {
        "teams": [
            {
                "name": "Alpha",
                "games": [
                    {
                        "date": "Sep 5",
                        "time": "10:00 am",
                        "opponentName": "Beta",
                        "teamScore": 3,
                        "opponentScore": 1,
                    }
                ],
            },
            {
                "name": "Beta",
                "games": [
                    {
                        "date": "Sep 5",
                        "time": "10:00 am",
                        "opponentName": "Alpha",
                        "teamScore": 1,
                        "opponentScore": 3,
                    }
                ],
            },
        ]
    }
    games = load_games(raw)
    assert len(games) == 1
    # Canonical: team = min("Alpha", "Beta") = "Alpha"
    assert games[0].team == "Alpha"
    assert games[0].opponent == "Beta"
    assert games[0].goals_team == 3
    assert games[0].goals_opponent == 1


def test_dedup_outside_game_kept():
    """A one-sided outside game is kept as-is (team = top-50 side)."""
    from ingest.mhr_loader import load_games

    raw = {
        "teams": [
            {
                "name": "Alpha",
                "games": [
                    {
                        "date": "Sep 5",
                        "time": "10:00 am",
                        "opponentName": "Outside Team X",
                        "teamScore": 5,
                        "opponentScore": 2,
                    }
                ],
            }
        ]
    }
    games = load_games(raw)
    assert len(games) == 1
    assert games[0].team == "Alpha"
    assert games[0].opponent == "Outside Team X"
    assert games[0].goals_team == 5
    assert games[0].goals_opponent == 2


def test_dedup_raises_on_score_mismatch():
    """Two rows with the same canonical key but disagreeing scores must raise."""
    from ingest.mhr_loader import load_games

    raw = {
        "teams": [
            {
                "name": "Alpha",
                "games": [
                    {
                        "date": "Sep 5",
                        "time": "10:00 am",
                        "opponentName": "Beta",
                        "teamScore": 3,
                        "opponentScore": 1,
                    }
                ],
            },
            {
                "name": "Beta",
                "games": [
                    {
                        "date": "Sep 5",
                        "time": "10:00 am",
                        "opponentName": "Alpha",
                        # Correct mirror would be teamScore=1, opponentScore=3 — this is wrong
                        "teamScore": 2,
                        "opponentScore": 3,
                    }
                ],
            },
        ]
    }
    with pytest.raises(ValueError, match="[Ss]core"):
        load_games(raw)


def test_doubleheader_kept_distinct():
    """Same two teams, same date, two different times → two separate games survive dedup."""
    from ingest.mhr_loader import load_games

    raw = {
        "teams": [
            {
                "name": "Alpha",
                "games": [
                    {
                        "date": "Sep 5",
                        "time": "10:00 am",
                        "opponentName": "Beta",
                        "teamScore": 3,
                        "opponentScore": 1,
                    },
                    {
                        "date": "Sep 5",
                        "time": "2:00 pm",
                        "opponentName": "Beta",
                        "teamScore": 2,
                        "opponentScore": 2,
                    },
                ],
            },
            {
                "name": "Beta",
                "games": [
                    {
                        "date": "Sep 5",
                        "time": "10:00 am",
                        "opponentName": "Alpha",
                        "teamScore": 1,
                        "opponentScore": 3,
                    },
                    {
                        "date": "Sep 5",
                        "time": "2:00 pm",
                        "opponentName": "Alpha",
                        "teamScore": 2,
                        "opponentScore": 2,
                    },
                ],
            },
        ]
    }
    games = load_games(raw)
    assert len(games) == 2


# ---------------------------------------------------------------------------
# End-to-end tests — vendored raw file (the count oracle from the task spec)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def raw_data():
    with open(RAW_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def loaded_games(raw_data):
    from ingest.mhr_loader import load_games

    return load_games(raw_data)


def test_full_load_counts(raw_data, loaded_games):
    """Validated oracle counts from the task spec must all pass exactly."""
    teams = raw_data["teams"]
    top50 = {t["name"] for t in teams}

    # Input sanity
    assert len(top50) == 50
    total_raw = sum(len(t["games"]) for t in teams)
    assert total_raw == 3174

    # Dedup output
    assert len(loaded_games) == 2130

    # Intra vs outside breakdown
    intra = [g for g in loaded_games if g.opponent in top50]
    outside = [g for g in loaded_games if g.opponent not in top50]
    assert len(intra) == 1044
    assert len(outside) == 1086

    # Distinct outside opponents
    outside_opponents = {g.opponent for g in outside}
    assert len(outside_opponents) == 215


def test_output_is_levelzero_and_roundtrips(loaded_games):
    """Every emitted game has the 7 §8 camelCase fields; round-trips through dataset_from_dict."""
    from ingest.mhr_loader import build_dataset_dict
    from generator.io import dataset_from_dict

    ds_dict = build_dataset_dict(loaded_games)
    expected_fields = {"week", "date", "time", "team", "opponent", "goalsTeam", "goalsOpponent"}
    for g in ds_dict["games"]:
        assert set(g.keys()) == expected_fields
        assert isinstance(g["week"], int)
        assert isinstance(g["date"], str)
        assert isinstance(g["time"], str)
        assert isinstance(g["team"], str)
        assert isinstance(g["opponent"], str)
        assert isinstance(g["goalsTeam"], int)
        assert isinstance(g["goalsOpponent"], int)

    dataset = dataset_from_dict(ds_dict)
    assert len(dataset.games) == 2130


def test_output_is_deterministic(raw_data):
    """Two independent calls to load_games + build_dataset_dict yield byte-identical JSON."""
    from ingest.mhr_loader import load_games, build_dataset_dict

    games1 = load_games(raw_data)
    games2 = load_games(raw_data)
    d1 = json.dumps(build_dataset_dict(games1), indent=2, ensure_ascii=False)
    d2 = json.dumps(build_dataset_dict(games2), indent=2, ensure_ascii=False)
    assert d1 == d2
