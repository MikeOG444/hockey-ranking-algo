# data/real — Real MHR game log (USA 11U AAA 2025-26)

## What this is

A clean, deterministic Level-0 game log built from the MyHockey Rankings top-50
USA 11U AAA teams for the 2025-26 season.  It is the first Stage-B dataset: real
observed data for the rating models to consume, replacing the synthetic generator.

## Files

| File | Description |
|------|-------------|
| `mhr-2025-top50.json` | The clean Level-0 dataset (2,130 unique games, §8 wire schema). **Generated** — do not hand-edit. |
| `raw/mhr-teams-games-2025-a2-v123-top50.json` | Vendored copy of the raw MHR per-team dump (committed for reproducibility). |

## How to regenerate

```
python -m ingest.mhr_loader
```

Reads `raw/mhr-teams-games-2025-a2-v123-top50.json`, writes `mhr-2025-top50.json`
and `reports/real-data-quality.md`.  Output is byte-identical on every run.

## Dataset schema (§8 Level-0)

```json
{
  "source": "MyHockey Rankings",
  "division": "USA 11U AAA",
  "season": "2025-26",
  "scenario": "real-mhr-2025-top50",
  "worldModel": "observed-real",
  "games": [
    {
      "week": 1,
      "date": "2025-08-15",
      "time": "19:20",
      "team": "...",
      "opponent": "...",
      "goalsTeam": 4,
      "goalsOpponent": 3
    }
  ]
}
```

Fields follow the camelCase §8 wire schema (`goalsTeam`/`goalsOpponent`).
No `groundTruth` — real data has no planted truth.

## Key design decisions

**Dedup:** The raw source lists games per team, so every intra-top-50 game
appears twice (once in each team's log).  The loader collapses each mirror pair
to one canonical row (team = alphabetically first of the two, scores oriented
accordingly) and raises on any score disagreement.  Outside-top-50 games appear
once and are kept as-is.

**Outside-top-50 opponents are retained** (215 distinct teams, 1,086 games).
They receive noisy ratings (few games each), but they correctly feed the
schedule-strength signal — which is the whole point of the real-data evaluation.
A team with a 41-3 record against unranked opponents versus 7-9-1 against ranked
ones looks very different when schedule strength is measured properly.

**Week derivation:**
- Week 1 = all games on or before 2025-09-09 (a long opening bucket — teams
  start at different times).
- Week 2 starts 2025-09-10 (Wednesday); each subsequent Wed→Tue window is
  week N+1.
- This is a pure calendar transform of the observed date — not a rating and not
  fed back into any model (observed-vs-derived wall, CLAUDE.md §3).

**No model run / no accuracy metric here.**  Real data has no planted ground
truth.  Designing the comparison yardstick (walk-forward prediction /
head-to-head agreement) is a deliberate follow-up task.
