# TASK-15: Real MHR data loader + data-quality report

**State:** ready · **Model:** sonnet — this is **ingest/ETL** work, not model-core and not eval: a
deterministic converter from an external per-team JSON dump into one §8 Level-0 dataset, plus a generated
quality report. Clear, fully-specified spec with hard test guardrails (validated counts, byte-identical
output) → sonnet. It runs **no model** and computes **no accuracy metric**, so none of the spike's
fairness/gate machinery is in play.
**Owns (files):** a **new** `ingest/` package — `ingest/mhr_loader.py` + `ingest/test_mhr_loader.py`; the
generated dataset `data/real/mhr-2025-top50.json`; the generated report `reports/real-data-quality.md`; a
vendored copy of the raw input `data/real/raw/mhr-teams-games-2025-a2-v123-top50.json`; and a short
`data/real/README.md`. Nothing else.
**Must NOT touch:** `models/*`, `generator/*`, `harness/*`, `scenarios/*`, `reports/comparison.md`. This is
**purely additive** — it introduces a new ingest path and consumes the shared `core.game.GameRow` contract
**read-only** (do not change `core/`).
**Parallel-safe:** **yes** — its Owns set is a brand-new package + a new `data/real/` dir + a new report,
all disjoint from every other task. It changes no shared file and runs no model/harness/scenario, so it can
land beside anything.
**Depends on:** none. `core.game.GameRow` already exists; the §8 wire schema already exists in
`generator/io.py` (read it for the field names, but **do not import the generator** — see Approach).
**Branch from:** latest `main` — the `/task 15` loop handles branch + PR.

> **Baseline before you start:** `pytest -q` should be **fully green**. Confirm that, vendor the raw input
> file (copy it into `data/real/raw/` so the build is reproducible and not tied to a path outside the
> repo), then write the failing tests first.

---

## Goal

We want to run the candidate raters on **real** MyHockey Rankings data (USA 11U AAA, 2025–26, top-50
teams) — the natural next step after the spike characterised bespoke vs the MHR replica on synthetic
ground truth. This task does **only the data-cleaning half**: turn the raw dump into a clean, deterministic
Level-0 game log the existing models can consume, plus an honest data-quality report. **No model runs and
no accuracy metric** — real data has *no planted ground truth*, so designing the comparison yardstick
(walk-forward prediction / head-to-head agreement) is a deliberately separate follow-up task.

The raw file lists **games per team, not per game**, so every game between two top-50 teams appears
**twice** (once in each team's log) while games against teams outside the top-50 appear **once**. Feeding
that in as-is would double-count top-50 matchups and bias the model toward exactly the schedule-strength
signal we care about. So the core job is a **safe, validated dedup** down to one row per physical game,
plus deriving the two fields the Level-0 schema needs that the source lacks (`week`, and a year on the
date).

**Outside-top-50 opponents are kept** (215 of them, via 1,086 one-sided games). They get noisy ratings
(few games each) but correctly feed schedule strength — and schedule strength is the whole point (it is
what exposes a padded record like Dallas's 41-3 vs unranked / 7-9-1 vs ranked). The eventual eval focuses
on the top-50; this task just preserves the outside games in the log.

---

## The input (validated — these numbers are the test oracle)

External file (vendor a copy into `data/real/raw/`):
`/Users/mikeogara_m3/Documents/Codex/2026-06-23/files-mentioned-by-the-user-import/outputs/mhr-teams-games-2025-a2-v123-top50.json`

Shape: `{ meta:{source,rankUrl,topN,generated}, teams:[ {name, teamId, games:[ {date,time,opponentName,teamScore,opponentScore} ]} ] }`.
Opponent is a **name string** (no id); the team's own `name`/`teamId` live on the parent.

Validated facts (assert against these — they are the data-integrity oracle):
- **50 teams**, **3,174** game-rows total (min 49 / max 87 / avg 63.48 per team).
- **Intra-top-50 rows: 2,088** → **1,044 unique games**, each appearing **exactly twice**. Mirror check on
  key `(sorted(teamA,teamB), date, time)`: **0 unmatched, 0 keys appearing >2×, 0 score mismatches** (every
  B-side `teamScore/opponentScore` is the exact mirror of the A-side).
- **Vs-outside rows: 1,086** (one-sided), across **215 distinct** non-top-50 opponents.
- **Dedup target: 2,130 unique physical games** (1,044 intra + 1,086 outside).
- **0** null/missing scores; **0** team-vs-itself rows; all **50** self-names appear **verbatim** as
  opponent names (so intra linkage is exact, no fuzzy matching needed).
- **227 tie rows** (raw); **20 rows** with empty `time`; **104** `(pair,date)` groups are doubleheaders
  (same two teams, same day, ≥2 games) — which is **why `time` must be in the dedup key**.
- Month histogram (for year inference + the week-1 bucket): Aug 133, Sep 527, Oct 558, Nov 555, Dec 357,
  Jan 564, Feb 413, Mar 67. All months are Aug–Mar → unambiguous year split.

---

## Three things settled here (do not re-debate)

1. **Week derivation (from the league calendar, confirmed with the human):**
   - **Week 1** = every game on/before **Tue 2025-09-09** (a deliberately long opening bucket — teams start
     at different times).
   - **Week 2** = **Wed 2025-09-10** onward; thereafter every week is a **Wed→Tue** 7-day window.
   - Formula: `week = 1 if date <= 2025-09-09 else 2 + (date - date(2025,09,10)).days // 7`.
     (Check: 9/10→2, 9/16 Tue→2, 9/17 Wed→3.) Week is a **pure calendar transform of the observed date** —
     not a rating, so the observed-vs-derived wall (brief §5) is intact; no RNG, so I8 determinism holds.

2. **Year inference:** the source date is `"Mon D"` with no year. Rule: month in **Aug–Dec → 2025**, month
   in **Jan–Jul → 2026**. Emit `date` as ISO `YYYY-MM-DD` to match the generator's convention
   (`generator.io` / `_week_date` use `.isoformat()`).

3. **Dedup keeps one canonical directional row per physical game.** Models symmetrize internally (they take
   `team`/`opponent` and build a matrix), so **direction is invisible to ratings** — but output must be
   **byte-identical** across runs, so the choice must be deterministic:
   - Canonical key `(min(nameA,nameB), max(nameA,nameB), date, time)`.
   - For intra games, keep the row with `team = min(pair)`, `opponent = max(pair)`, scores oriented to that
     team. For outside games (one-sided), keep as-is (`team` = the top-50 side).
   - If two rows share a key but **disagree on score**, **raise** — never silently pick one. (Validated to
     be 0 today; the guard ensures future dumps can't corrupt silently.)
   - Emit games **sorted by `(week, date, time, team, opponent)`** so the file is stable.

---

## Read first (a cold chat must absorb these)

1. **`CLAUDE.md`** — prime directive (100% AI-authored, explain *why*/behaviour in plain English; tests are
   the proof — show output), **method §2** (determinism is sacred — no RNG, stable sort, byte-identical
   output) and **§3** (observed-vs-derived is a hard wall; week is a derived *calendar* field, never a
   rating fed back).
2. **`docs/planning/operating-model.md`** — the trunk + PR "stop before merge" loop and the model-matching
   table (ingest/ETL with a clear spec → sonnet).
3. **`core/game.py`** — the `GameRow` dataclass (`week, date, time, team, opponent, goals_team,
   goals_opponent`). This is the **shared contract** the loader emits; consume it, do not change it.
4. **`generator/io.py`** — `_game_to_dict` / `dataset_to_dict` define the §8 wire schema (camelCase
   `goalsTeam`/`goalsOpponent`, top-level `{scenario, seed, worldModel, config, games, groundTruth?}`).
   **Read it for the exact field names, but do NOT import the generator** — the loader builds the dict
   locally so ingest stays decoupled from the synthetic world. The round-trip test (below) *may* import
   `generator.io.dataset_from_dict` to prove the output loads back into a `Dataset` of correct `GameRow`s.
5. The validated-facts block above — it is the test oracle.

---

## Approach (TDD — write the failing tests first, watch them fail, then implement)

### Step 1 — `ingest/test_mhr_loader.py` (write first)

```python
# --- pure-unit tests (fast, no file IO) ---
# test_infer_year: ("Sep",..)->2025, ("Dec",..)->2025, ("Jan",..)->2026, ("Jul",..)->2026 boundary.
# test_parse_date_to_iso: "Sep 5" -> "2025-09-05"; "Jan 3" -> "2026-01-03".
# test_week_seam: 2025-09-09 -> week 1; 2025-09-10 -> week 2; 2025-09-16 -> 2; 2025-09-17 -> 3;
#                 an Aug date -> week 1; a Feb 2026 date -> the right Wed→Tue bucket.
# test_normalize_time: "10:19 am"->"10:19", "6:26 pm"->"18:26", "12:00 am"->"00:00",
#                      "12:30 pm"->"12:30", ""->"00:00".
# test_dedup_collapses_mirrored_pair: two mirrored rows for one intra game -> ONE canonical row
#                      (team=min(pair), scores oriented); an outside one-sided game is kept once.
# test_dedup_raises_on_score_mismatch: two rows, same key, disagreeing scores -> raises (no silent pick).
# test_doubleheader_kept_distinct: same pair, same date, two different times -> TWO games (time in key).

# --- end-to-end on the vendored raw file (the oracle) ---
# test_full_load_counts: 50 teams in, 2130 unique games out; 1044 intra + 1086 outside;
#                        215 distinct outside opponents; 0 ties dropped (count preserved post-dedup).
# test_output_is_levelzero_and_roundtrips: every emitted game has the 7 §8 camelCase fields and valid
#                        types; generator.io.dataset_from_dict(output) yields 2130 GameRows.
# test_output_is_deterministic: building twice yields byte-identical JSON (sorted, no wall-clock in body).
```

### Step 2 — implement `ingest/mhr_loader.py` to green

Pure helpers + a thin CLI. Suggested surface (adapt as the tests demand):
- `infer_year(month: str) -> int`, `parse_date(raw: str) -> datetime.date`, `week_of(d: date) -> int`,
  `normalize_time(raw: str) -> str` — the four pure field transforms above.
- `load_games(raw: dict) -> list[GameRow]` — flatten every team's games into directional candidate rows
  (team = parent name, opponent = `opponentName`, goals from `teamScore`/`opponentScore`, `date` ISO,
  `time` normalized, `week` derived), then **dedup** via the canonical-key rule (raise on score mismatch),
  then **stable-sort** by `(week, date, time, team, opponent)`.
- `build_dataset_dict(games) -> dict` — wrap as a §8 dict: `{"source": "MyHockey Rankings",
  "division": "USA 11U AAA", "season": "2025-26", "scenario": "real-mhr-2025-top50", "worldModel":
  "observed-real", "games": [ ...7-field camelCase... ]}`. **No `groundTruth`** (none exists). Keep any
  `generated`/wall-clock stamp OUT of the serialized body so the file is byte-identical (put provenance in
  the report, or stamp it from a fixed value passed in — never `datetime.now()`).
- `build_quality_report(raw, games) -> str` — the deterministic markdown (see Step 3).
- `main()` — read `data/real/raw/…json`, write `data/real/mhr-2025-top50.json` and
  `reports/real-data-quality.md`. Invoked via `python -m ingest.mhr_loader`.

Determinism: no RNG, no `datetime.now()` in any serialized output, stable sort, ISO dates → byte-identical
files. (Same discipline as `harness/run.py`'s report.)

### Step 3 — `reports/real-data-quality.md` (generated, deterministic)

A short, honest one-pager generated by the loader (regenerable; do not hand-edit). Include: source +
division + season; raw rows (3,174) → unique games (2,130) with the **dedup math** (intra 2,088→1,044,
outside 1,086); 50 teams + 215 outside opponents; tie count; week histogram (call out the long week-1
bucket); doubleheader count; empty-time count; and the **mirror-consistency result** (0 unmatched / 0 score
mismatches) as the data-integrity proof. Plus a one-line scope note: *outside-top-50 teams are retained for
schedule strength; no model run and no accuracy metric here (real data has no planted truth — separate
follow-up).*

Also write `data/real/README.md`: what the dataset is, that it is generated by `python -m ingest.mhr_loader`
from the vendored raw dump, the schema, and the keep-outside-teams decision.

### Step 4 — verify

`python -m ingest.mhr_loader` to generate both artifacts; `pytest -q` whole suite green; `ruff check .`
clean. Re-run the loader and confirm `git diff` on the two generated files is empty (byte-identical).

---

## Acceptance / Definition of done

- [ ] New `ingest/` package: `mhr_loader.py` (pure transforms + dedup + CLI) and `test_mhr_loader.py`,
      written test-first.
- [ ] Raw input vendored at `data/real/raw/mhr-teams-games-2025-a2-v123-top50.json` (committed, so the build
      is reproducible without an external path).
- [ ] `data/real/mhr-2025-top50.json` generated: **2,130** Level-0 games (1,044 intra + 1,086 outside), 7
      §8 camelCase fields each, **no `groundTruth`**, sorted, **byte-identical** on re-run; loads back via
      `generator.io.dataset_from_dict`.
- [ ] Dedup proven: mirrored intra pair → one canonical row; outside one-sided game kept; doubleheaders kept
      distinct (time in key); **score-mismatch input raises** (no silent corruption).
- [ ] Week + year + time derivations proven at the boundaries (9/9↔9/10 seam, Aug↔Jan year split, am/pm +
      empty-time edges).
- [ ] `reports/real-data-quality.md` generated (deterministic), with the dedup math, week histogram, and the
      0-mismatch mirror-integrity proof; `data/real/README.md` written.
- [ ] `models/*`, `generator/*`, `harness/*`, `scenarios/*`, `core/*` **untouched**.
- [ ] `pytest -q` whole suite green; `ruff check .` clean; `git diff` on the two generated artifacts empty
      after a second `python -m ingest.mhr_loader`.
- [ ] **`spec-keeper`** run on the diff — confirm: week is a derived calendar field (observed-vs-derived wall
      intact, not a rating fed back), determinism preserved (no RNG / no wall-clock in serialized output),
      and outside teams are retained (not silently dropped). Include its verdict in the PR.
      (`invariant-auditor` is **not** required — no model and no scoring change; note that in the PR.)
- [ ] `docs/work/BOARD.md` row 15 flipped (loop handles `in-progress`/`in-review`; merge → `done`).
- [ ] PR body (plain English, reviewer won't open the file): lead with *why* (games are listed per-team, so
      top-50 matchups are double-counted; the model needs one row per physical game plus a week index), and
      *what was produced* (a deterministic Level-0 dataset of 2,130 games + a quality report), the validated
      counts, and the explicit note that outside teams are kept for schedule strength and **no model/metric
      runs here**.

---

## Out of scope

- **Any model run or accuracy metric.** Real data has no planted truth; designing the comparison yardstick
  (walk-forward prediction / head-to-head agreement, à la the deferred Stage-B evaluation) is a separate
  follow-up task. This task ends at clean data + report.
- **Touching `models/*`, `generator/*`, `harness/*`, `scenarios/*`, `reports/comparison.md`.** Purely
  additive ingest.
- **Fuzzy opponent-name matching / cross-division resolution.** Top-50 names match verbatim; outside
  opponents are kept by name as-is. No name-normalization beyond what the tests require.
- **Importing the generator into production ingest code.** Read its schema; keep ingest decoupled (a test
  may import `dataset_from_dict` only to prove the round-trip).
- **Tier labels / `groundTruth`.** None exist for real data; emit none.
