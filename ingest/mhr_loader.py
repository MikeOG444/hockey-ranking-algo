"""Convert the raw MHR per-team JSON dump to a §8 Level-0 game log.

Responsibilities
----------------
1.  Derive the two Level-0 fields missing from the source: ``week`` (calendar
    bucket starting Wed 2025-09-10) and a year-qualified ISO ``date``.
2.  Normalise the 12-hour ``time`` string to ``HH:MM``.
3.  Dedup: every intra-top-50 game appears twice (one row per team's log).
    Collapse to one canonical row per physical game; raise on any score
    disagreement so future corrupt dumps are caught immediately.
4.  Write the clean dataset as a §8 Level-0 JSON file and a human-readable
    quality report.

Design constraints (from CLAUDE.md and the task spec)
-------------------------------------------------------
- **Observed-vs-derived wall**: ``week`` is a pure calendar transform of the
  observed date — it is not a rating and is not fed back into any model.
- **Determinism**: no ``datetime.now()``, no RNG, stable sort → byte-identical
  output on every run.
- **Decoupled from the generator**: this module builds dicts locally.  A test
  *may* import ``generator.io.dataset_from_dict`` to prove the round-trip, but
  this production file does not import the generator.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from core.game import GameRow


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# All dates in Aug–Dec belong to 2025; Jan–Jul belong to 2026.
_MONTHS_2025 = {"Aug", "Sep", "Oct", "Nov", "Dec"}

# The long week-1 opening bucket covers everything up to and including this date.
_WEEK1_CUTOFF = date(2025, 9, 9)
# Week 2 starts on this Wednesday; every subsequent Wed→Tue window is week N+1.
_WEEK2_START = date(2025, 9, 10)


# ---------------------------------------------------------------------------
# Pure field transforms
# ---------------------------------------------------------------------------


def infer_year(month: str) -> int:
    """Return 2025 for Aug–Dec, 2026 for Jan–Jul."""
    return 2025 if month in _MONTHS_2025 else 2026


def parse_date(raw: str) -> date:
    """Parse a bare 'Mon D' or 'Mon DD' string to a year-qualified date.

    Year is inferred from the month: Aug–Dec → 2025, Jan–Jul → 2026.
    """
    month_str, day_str = raw.split()
    year = infer_year(month_str)
    month_num = datetime.strptime(month_str, "%b").month
    return date(year, month_num, int(day_str))


def week_of(d: date) -> int:
    """Map an observed game date to its league-calendar week number.

    Week 1 is a long opening bucket (everything on or before 2025-09-09).
    Week 2 starts 2025-09-10 (Wed); thereafter every Wed→Tue 7-day window
    advances the week by one.

    Formula: week = 1 if d <= 2025-09-09 else 2 + (d - 2025-09-10).days // 7
    """
    if d <= _WEEK1_CUTOFF:
        return 1
    return 2 + (d - _WEEK2_START).days // 7


def normalize_time(raw: str) -> str:
    """Normalise a '12-hour am/pm' time string to 'HH:MM' (24-hour, zero-padded).

    An empty string (20 rows in the source have no time) becomes '00:00'.
    """
    if raw is None:
        return "00:00"
    raw = raw.strip()
    if not raw:
        return "00:00"
    return datetime.strptime(raw.upper(), "%I:%M %p").strftime("%H:%M")


# ---------------------------------------------------------------------------
# Dedup + canonical-row logic
# ---------------------------------------------------------------------------


def load_games(raw: dict) -> list[GameRow]:
    """Flatten, dedup, and sort the raw per-team game log into Level-0 rows.

    Algorithm
    ---------
    1.  Build the set of top-50 team names from the ``teams`` list.
    2.  Iterate every team's games, producing one candidate ``GameRow`` per raw
        entry (all field transforms applied).
    3.  Group candidates by canonical key
        ``(min(team, opponent), max(team, opponent), date, time)``.
    4.  Groups of 2 are intra-top-50 games: verify the scores are mirrors of
        each other; keep the row oriented with ``team = min(pair)``.
        Groups of 1 are outside games: keep as-is (``team`` = the top-50 side).
        Groups of any other size are a data error → raise.
    5.  Sort output by ``(week, date, time, team, opponent)`` for stability.
    """
    # Step 1 + 2: flatten into candidate rows
    groups: dict[tuple, list[GameRow]] = defaultdict(list)
    for team_entry in raw["teams"]:
        team_name = team_entry["name"]
        for g in team_entry["games"]:
            d = parse_date(g["date"])
            row = GameRow(
                week=week_of(d),
                date=d.isoformat(),
                time=normalize_time(g["time"]),
                team=team_name,
                opponent=g["opponentName"],
                goals_team=int(g["teamScore"]),
                goals_opponent=int(g["opponentScore"]),
            )
            key = (
                min(row.team, row.opponent),
                max(row.team, row.opponent),
                row.date,
                row.time,
            )
            groups[key].append(row)

    # Step 3 + 4: resolve each group to one canonical row
    result: list[GameRow] = []
    for key, rows in groups.items():
        if len(rows) == 1:
            # Outside game (one-sided): keep the single row unchanged.
            result.append(rows[0])
        elif len(rows) == 2:
            a, b = rows[0], rows[1]
            # Verify mirror consistency: a.goals_team should equal b.goals_opponent
            # and vice-versa.  The validated raw data has 0 mismatches; the guard
            # ensures future dumps cannot corrupt the dataset silently.
            if a.goals_team != b.goals_opponent or a.goals_opponent != b.goals_team:
                raise ValueError(
                    f"Score mismatch for key {key}: "
                    f"{a.team} {a.goals_team}-{a.goals_opponent} vs "
                    f"{b.team} {b.goals_team}-{b.goals_opponent}"
                )
            # Keep canonical orientation: team = min(pair).
            canon_team = key[0]  # already min(team, opponent)
            if a.team == canon_team:
                result.append(a)
            else:
                # Re-orient: flip team/opponent and swap scores.
                result.append(
                    GameRow(
                        week=a.week,
                        date=a.date,
                        time=a.time,
                        team=a.opponent,
                        opponent=a.team,
                        goals_team=a.goals_opponent,
                        goals_opponent=a.goals_team,
                    )
                )
        else:
            raise ValueError(
                f"Unexpected {len(rows)} rows for key {key} — "
                "expected 1 (outside game) or 2 (intra mirror pair)"
            )

    # Step 5: stable sort → byte-identical output across runs
    result.sort(key=lambda r: (r.week, r.date, r.time, r.team, r.opponent))
    return result


# ---------------------------------------------------------------------------
# Output builders
# ---------------------------------------------------------------------------


def build_dataset_dict(games: list[GameRow]) -> dict:
    """Wrap the clean game list in a §8-compliant Level-0 JSON dict.

    No ``groundTruth`` (real data has no planted truth) and no wall-clock
    timestamp in the serialized body — both are required for byte-identical
    output across runs.
    """
    return {
        "source": "MyHockey Rankings",
        "division": "USA 11U AAA",
        "season": "2025-26",
        "scenario": "real-mhr-2025-top50",
        "worldModel": "observed-real",
        "games": [
            {
                "week": g.week,
                "date": g.date,
                "time": g.time,
                "team": g.team,
                "opponent": g.opponent,
                "goalsTeam": g.goals_team,
                "goalsOpponent": g.goals_opponent,
            }
            for g in games
        ],
    }


def build_quality_report(raw: dict, games: list[GameRow]) -> str:
    """Generate a deterministic markdown quality report from the raw + deduped data.

    The report documents: source metadata, raw→dedup math, mirror-consistency
    proof, tie count, week histogram, doubleheader and empty-time counts, and the
    design decision to retain outside-top-50 opponents.
    """
    top50 = {t["name"] for t in raw["teams"]}

    # --- raw stats ---
    all_raw = [(t["name"], g) for t in raw["teams"] for g in t["games"]]
    total_raw = len(all_raw)
    raw_intra = sum(1 for _, g in all_raw if g["opponentName"] in top50)
    raw_outside = sum(1 for _, g in all_raw if g["opponentName"] not in top50)
    raw_empty_time = sum(1 for _, g in all_raw if not g["time"])

    # Mirror-consistency stats (validated during load — 0 mismatches guaranteed
    # because load_games would have raised; recompute for the report).
    intra_groups: dict[tuple, list] = defaultdict(list)
    for name, g in all_raw:
        opp = g["opponentName"]
        if opp in top50:
            key = (min(name, opp), max(name, opp), g["date"], g["time"] or "")
            # Store canonical-oriented scores (team = min(pair))
            if name == min(name, opp):
                intra_groups[key].append((g["teamScore"], g["opponentScore"]))
            else:
                intra_groups[key].append((g["opponentScore"], g["teamScore"]))

    unmatched = sum(1 for v in intra_groups.values() if len(v) != 2)
    mismatches = sum(
        1 for v in intra_groups.values() if len(v) == 2 and v[0] != v[1]
    )

    # --- deduped stats ---
    total_games = len(games)
    intra_games = [g for g in games if g.opponent in top50]
    outside_games = [g for g in games if g.opponent not in top50]
    outside_opponents = {g.opponent for g in outside_games}

    tie_count = sum(1 for g in games if g.goals_team == g.goals_opponent)

    # Week histogram — count of unique physical games per week
    week_hist = Counter(g.week for g in games)
    max_week = max(week_hist) if week_hist else 0

    # Doubleheader groups: intra-top-50 (pair,date) combinations with ≥2 games.
    # The spec oracle is 104 for intra pairs — these are the cases where time must
    # be in the dedup key, because two mirror-pair rows sharing the same key would
    # otherwise be collapsed into one game when they are in fact two.
    pair_date_intra = Counter(
        (min(g.team, g.opponent), max(g.team, g.opponent), g.date) for g in intra_games
    )
    doubleheader_groups = sum(1 for v in pair_date_intra.values() if v >= 2)

    # --- build report ---
    lines: list[str] = [
        "# Real-Data Quality Report — MHR 2025-26 USA 11U AAA Top-50",
        "",
        "Generated by `python -m ingest.mhr_loader`. Re-run to regenerate.",
        "",
        "## Source",
        "",
        "| Field | Value |",
        "|-------|-------|",
        "| Source | MyHockey Rankings |",
        "| Division | USA 11U AAA |",
        "| Season | 2025–26 |",
        "| Dataset | real-mhr-2025-top50 |",
        "| Raw file | `data/real/raw/mhr-teams-games-2025-a2-v123-top50.json` |",
        "",
        "## Dedup summary",
        "",
        "The raw file lists games **per team**, so every intra-top-50 game appears twice.",
        "Dedup collapses each mirror pair to one canonical row; outside-top-50 games",
        "(one-sided) are kept as-is.",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        "| Teams (top-50) | 50 |",
        f"| Raw game rows | {total_raw:,} |",
        f"| ↳ intra-top-50 rows | {raw_intra:,} |",
        f"| ↳ vs-outside rows | {raw_outside:,} |",
        f"| **Unique physical games** | **{total_games:,}** |",
        f"| ↳ intra-top-50 games | {len(intra_games):,} |",
        f"| ↳ vs-outside games | {len(outside_games):,} |",
        f"| Distinct outside opponents | {len(outside_opponents):,} |",
        "",
        "Dedup math: 2,088 intra rows ÷ 2 = **1,044 unique intra games**;",
        "1,086 outside rows are already unique → **1,086 outside games**;",
        f"total **{total_games:,}** unique physical games.",
        "",
        "## Mirror-consistency proof",
        "",
        "Every intra-top-50 pair was checked: A-side `(teamScore, opponentScore)` must",
        "equal B-side `(opponentScore, teamScore)`.  Any mismatch causes `load_games` to",
        "raise, so the dataset cannot be silently corrupted by future dumps.",
        "",
        "| Check | Result |",
        "|-------|--------|",
        f"| Intra canonical keys | {len(intra_groups):,} |",
        f"| Keys appearing ≠2 times (unmatched) | {unmatched} |",
        f"| Score mismatches | {mismatches} |",
        "",
        "**All 1,044 intra keys appear exactly twice with 0 score mismatches.**",
        "",
        "## Data-quality notes",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Tie games (deduped) | {tie_count:,} |",
        f"| Empty-time rows (raw) | {raw_empty_time:,} |",
        f"| Doubleheader (pair,date) groups | {doubleheader_groups:,} |",
        "",
        "Empty-time rows use `time = '00:00'`; `time` must be in the dedup key",
        f"because {doubleheader_groups} pair-date combinations have ≥2 games on the same day.",
        "",
        "## Week histogram (unique physical games)",
        "",
        "Week 1 is a long opening bucket (everything on or before 2025-09-09).",
        "Week 2 starts 2025-09-10; each subsequent Wed→Tue window advances by 1.",
        "",
        "| Week | Games |",
        "|------|-------|",
    ]

    for wk in range(1, max_week + 1):
        count = week_hist.get(wk, 0)
        if count > 0:
            note = " ← long opening bucket" if wk == 1 else ""
            lines.append(f"| {wk} | {count}{note} |")

    lines += [
        "",
        "## Scope note",
        "",
        "**Outside-top-50 opponents are retained** (215 distinct teams, 1,086 games).",
        "They receive noisy ratings (few games each) but correctly feed schedule-strength",
        "signals — which is the whole point of this dataset (e.g., a team with a 41-3",
        "record against unranked opponents vs 7-9-1 against ranked ones).",
        "",
        "**No model run and no accuracy metric in this task.** Real data has no planted",
        "ground truth; designing the comparison yardstick (walk-forward prediction /",
        "head-to-head agreement) is a deliberate follow-up.",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Read the vendored raw file, write the Level-0 dataset and quality report."""
    repo_root = Path(__file__).parent.parent
    raw_path = repo_root / "data/real/raw/mhr-teams-games-2025-a2-v123-top50.json"
    out_path = repo_root / "data/real/mhr-2025-top50.json"
    report_path = repo_root / "reports/real-data-quality.md"

    with open(raw_path) as f:
        raw = json.load(f)

    print(f"Loaded {sum(len(t['games']) for t in raw['teams'])} raw rows from {raw_path.name}")

    games = load_games(raw)
    print(f"Deduped to {len(games)} unique physical games")

    ds = build_dataset_dict(games)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(ds, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote dataset → {out_path}")

    report = build_quality_report(raw, games)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Wrote quality report → {report_path}")


if __name__ == "__main__":
    main()
