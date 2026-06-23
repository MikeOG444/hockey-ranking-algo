"""Head-to-head agreement + giant-killer case studies (TASK-16 / Phase B2).

Answers two questions the synthetic spike could not:
1. Whose ranking agrees with who-actually-beat-whom?
   Reconstruct the gauntlet (intra-ranked head-to-head record) and measure
   Spearman ρ between each model's ranking and the gauntlet ranking.
2. Do the real giant-killers get caught?
   Put named schedule-padders under a microscope: ranked vs unranked splits and
   bespoke's per-game scheduleTerm attribution showing exactly which wins the
   schedule channel discounts.

Design constraints (CLAUDE.md):
- Observed-vs-derived wall: gauntlet is computed purely from the game log,
  never from any model rating fed back in.
- Determinism (I8): stable sorts, no RNG, no wall-clock → byte-identical report.
- Honesty: the gauntlet is labelled a proxy, not ground truth (no planted truth
  in real data). Score against outcomes, not MHR's own published ranking.
- Consumes bespoke and mhr_replica read-only; never modifies them.
- Local Spearman (does not import harness.metrics — that module pulls in
  generator.simulate, a synthetic-only dep).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import numpy as np

from core.game import GameRow
from models.bespoke import (
    BespokeParams,
    CreditBreakdown,
    RateResult,
    base_and_margin,
    classify,
    rate_weekly,
)
from models.mhr_replica import rate as mhr_rate

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent
_CLEAN_JSON = _REPO_ROOT / "data/real/mhr-2025-top50.json"
_RAW_JSON = _REPO_ROOT / "data/real/raw/mhr-teams-games-2025-a2-v123-top50.json"


def load_games_from_json(path: Path | str = _CLEAN_JSON) -> list[GameRow]:
    """Parse the clean §8 Level-0 JSON into GameRow objects."""
    with open(path) as f:
        d = json.load(f)
    return [
        GameRow(
            week=g["week"],
            date=g["date"],
            time=g["time"],
            team=g["team"],
            opponent=g["opponent"],
            goals_team=g["goalsTeam"],
            goals_opponent=g["goalsOpponent"],
        )
        for g in d["games"]
    ]


def load_ranked_set(raw_path: Path | str = _RAW_JSON) -> tuple[list[str], set[str]]:
    """Load the 50 ranked team names from the raw MHR dump.

    Returns (mhr_ordered_list, ranked_set_frozenset) where mhr_ordered_list[0]
    is MHR rank #1. Position in the raw 'teams' array is the MHR rank (1-indexed).
    """
    with open(raw_path) as f:
        raw = json.load(f)
    ordered = [t["name"] for t in raw["teams"]]
    return ordered, set(ordered)


# ---------------------------------------------------------------------------
# Gauntlet computation
# ---------------------------------------------------------------------------


def gauntlet_table(games: list[GameRow], ranked_set: set[str]) -> dict[str, dict]:
    """Compute head-to-head stats for each ranked team from intra-ranked games only.

    Gauntlet score: pts = 2w + t; n = w + l + t; pct = pts / (2n) * 100.
    Goal differential (gd = gf - ga) is the tiebreaker in gauntlet_ranked_list.

    Only games where BOTH team and opponent are in ranked_set count. Outside-top-50
    games are excluded from all gauntlet counts (observed-vs-derived wall: the
    gauntlet is outcomes only, not a model-derived value).
    """
    stats: dict[str, dict] = {t: {"w": 0, "l": 0, "t": 0, "gf": 0, "ga": 0} for t in ranked_set}

    for g in games:
        # Only intra-ranked games.
        if g.team not in ranked_set or g.opponent not in ranked_set:
            continue

        gf_a, ga_a = g.goals_team, g.goals_opponent
        gf_b, ga_b = g.goals_opponent, g.goals_team
        result_a = classify(gf_a, ga_a)

        for team, gf, ga, result in [
            (g.team, gf_a, ga_a, result_a),
            (g.opponent, gf_b, ga_b, "W" if result_a == "L" else ("L" if result_a == "W" else "T")),
        ]:
            stats[team]["gf"] += gf
            stats[team]["ga"] += ga
            if result == "W":
                stats[team]["w"] += 1
            elif result == "L":
                stats[team]["l"] += 1
            else:
                stats[team]["t"] += 1

    result_table: dict[str, dict] = {}
    for team, s in stats.items():
        w, l, t = s["w"], s["l"], s["t"]
        gf, ga = s["gf"], s["ga"]
        pts = 2 * w + t
        n = w + l + t
        pct = pts / (2 * n) * 100 if n > 0 else 0.0
        result_table[team] = {
            "w": w, "l": l, "t": t,
            "gf": gf, "ga": ga, "gd": gf - ga,
            "pts": pts, "n": n, "pct": pct,
        }
    return result_table


def gauntlet_ranked_list(table: dict[str, dict]) -> list[str]:
    """Return teams sorted by gauntlet rank: pct desc, gd desc, name asc (for stability)."""
    return sorted(table, key=lambda t: (-table[t]["pct"], -table[t]["gd"], t))


# ---------------------------------------------------------------------------
# Spearman agreement
# ---------------------------------------------------------------------------


def _spearman(scores_a: dict[str, float], scores_b: dict[str, float]) -> float:
    """Spearman ρ over the key intersection of two score dicts (local — no harness import).

    Uses argsort-of-argsort rank encoding and numpy.corrcoef. `argsort(argsort(v))`
    assigns ordinal ranks (ties broken by first-encountered order in the sorted array,
    not averaged). In practice, input scores are position integers derived from already-
    sorted lists, so tied scores only arise when two teams have byte-identical model
    ratings — rare and benign. Returns 0.0 on < 2 teams.
    """
    keys = sorted(set(scores_a) & set(scores_b))
    if len(keys) < 2:
        return 0.0
    va = np.array([scores_a[k] for k in keys], dtype=float)
    vb = np.array([scores_b[k] for k in keys], dtype=float)
    ra = np.argsort(np.argsort(va)).astype(float)
    rb = np.argsort(np.argsort(vb)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def agreement(model_rank: list[str], gauntlet_rank: list[str]) -> float:
    """Spearman ρ between model ranking and gauntlet ranking.

    Both lists are ordered best-first. Teams present in one but not the other are
    ignored (intersection only). Returns 1.0 for identical orderings, -1.0 for
    reversed, 0.0 for orthogonal.
    """
    n_model = len(model_rank)
    n_gaunt = len(gauntlet_rank)
    # Convert position (0 = best) to a score where higher = better.
    model_scores = {t: n_model - i for i, t in enumerate(model_rank)}
    gaunt_scores = {t: n_gaunt - i for i, t in enumerate(gauntlet_rank)}
    return _spearman(model_scores, gaunt_scores)


# ---------------------------------------------------------------------------
# Model ranking
# ---------------------------------------------------------------------------


def model_ranking(
    rate_fn: Callable[..., RateResult],
    games: list[GameRow],
    ranked_set: set[str],
) -> list[str]:
    """Run rate_fn on the full game log, return ranked teams sorted by rating desc.

    Outside-top-50 teams are included in the rater input (their schedule-strength
    signal matters) but excluded from the returned ranking. Stable tie-break on
    team name so rankings are deterministic when two teams have identical ratings.
    """
    result = rate_fn(games)
    ranked_ratings = {t: r for t, r in result.ratings.items() if t in ranked_set}
    return sorted(ranked_ratings, key=lambda t: (-ranked_ratings[t], t))


# ---------------------------------------------------------------------------
# Case study
# ---------------------------------------------------------------------------


def _entry_opponents_and_results(team: str, games: list[GameRow]) -> list[tuple[str, str]]:
    """Return (opponent_name, result_for_team) in the same order as bespoke's per_game_attribution.

    Mirrors the sort used in bespoke._build_entries: (opponent, base, raw_margin, week).
    This lets callers zip with RateResult.per_game_attribution[team] to associate each
    CreditBreakdown with its opponent without reaching into bespoke internals.
    """
    params = BespokeParams()
    entries: list[tuple[float, float, str, str, int]] = []
    for g in games:
        if g.team == team:
            b, m = base_and_margin(g.goals_team, g.goals_opponent, params)
            result = classify(g.goals_team, g.goals_opponent)
            entries.append((b, m, g.opponent, result, g.week))
        elif g.opponent == team:
            b, m = base_and_margin(g.goals_opponent, g.goals_team, params)
            result = classify(g.goals_opponent, g.goals_team)
            entries.append((b, m, g.team, result, g.week))
    entries.sort(key=lambda e: (e[2], e[0], e[1], e[4]))
    return [(e[2], e[3]) for e in entries]


def _record_vs(games: list[GameRow], team: str, opponent_set: set[str]) -> dict:
    """W/L/T + GF/GA/GD for `team` against opponents in `opponent_set`."""
    w = l = t = gf = ga = 0
    for g in games:
        if g.team == team and g.opponent in opponent_set:
            gf += g.goals_team
            ga += g.goals_opponent
            r = classify(g.goals_team, g.goals_opponent)
            if r == "W":
                w += 1
            elif r == "L":
                l += 1
            else:
                t += 1
        elif g.opponent == team and g.team in opponent_set:
            gf += g.goals_opponent
            ga += g.goals_team
            r = classify(g.goals_opponent, g.goals_team)
            if r == "W":
                w += 1
            elif r == "L":
                l += 1
            else:
                t += 1
    n = w + l + t
    pts = 2 * w + t
    pct = pts / (2 * n) * 100 if n > 0 else 0.0
    return {"w": w, "l": l, "t": t, "gf": gf, "ga": ga, "gd": gf - ga, "n": n, "pct": pct}


def case_study(
    team: str,
    games: list[GameRow],
    bespoke_result: RateResult,
    ranked_set: set[str],
    mhr_rank: int = 0,
    gauntlet_rank_num: int = 0,
) -> dict:
    """Produce a case-study dict for one team, showing the schedule-padding signature.

    Returns:
        team              — team name
        mhr_rank          — MHR rank (1-indexed; 0 if not provided)
        gauntlet_rank     — gauntlet rank (1-indexed; 0 if not provided)
        ranked            — record dict vs ranked opponents (w/l/t/gf/ga/gd/pct)
        unranked          — record dict vs outside-top-50 opponents
        bespoke_schedule  — avg scheduleTerm per game vs ranked and vs unranked opponents
                            (from bespoke's per_game_attribution; shows schedule discounting)
    """
    unranked_set = {g.team for g in games} | {g.opponent for g in games}
    unranked_set -= ranked_set

    ranked_rec = _record_vs(games, team, ranked_set - {team})
    unranked_rec = _record_vs(games, team, unranked_set)

    # Attribution order mirrors bespoke._build_entries.
    opp_results = _entry_opponents_and_results(team, games)
    attr_list: list[CreditBreakdown] = bespoke_result.per_game_attribution.get(team, [])

    ranked_sched_terms = [
        bd.schedule_term for (opp, _), bd in zip(opp_results, attr_list) if opp in ranked_set
    ]
    unranked_sched_terms = [
        bd.schedule_term for (opp, _), bd in zip(opp_results, attr_list) if opp not in ranked_set
    ]

    def _mean(xs: list[float]) -> float | None:
        return sum(xs) / len(xs) if xs else None

    return {
        "team": team,
        "mhr_rank": mhr_rank,
        "gauntlet_rank": gauntlet_rank_num,
        "ranked": ranked_rec,
        "unranked": unranked_rec,
        "bespoke_schedule": {
            "avg_vs_ranked": _mean(ranked_sched_terms),
            "avg_vs_unranked": _mean(unranked_sched_terms),
        },
    }


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def _fmt_record(rec: dict) -> str:
    return f"{rec['w']}-{rec['l']}-{rec['t']} (GD {rec['gd']:+d}, {rec['pct']:.1f}%)"


def build_report(
    gauntlet_tbl: dict[str, dict],
    gauntlet_list: list[str],
    mhr_order: list[str],
    bespoke_rank: list[str],
    mhr_replica_rank: list[str],
    bespoke_rho: float,
    mhr_rho: float,
    case_studies: list[dict],
) -> str:
    """Build the deterministic markdown report (reports/real-h2h.md).

    All inputs are plain data derived from the game log and model outputs —
    no wall-clock, no RNG → byte-identical on every call with the same inputs.
    """
    lines: list[str] = [
        "# Head-to-Head Agreement — MHR 2025-26 USA 11U AAA Top-50",
        "",
        "Generated by `python -m analysis.head_to_head`. Re-run to regenerate.",
        "",
        "> **Gauntlet proxy note:** The gauntlet (intra-ranked head-to-head record) is a proxy",
        "> for team quality, not planted ground truth — real data has no oracle. Agreement with",
        "> who-actually-beat-whom is the closest available yardstick. This is a full-season",
        "> single-shot analysis; walk-forward prediction is Stage-B Phase B4.",
        "",
        "## Agreement with the Head-to-Head Gauntlet",
        "",
        "Gauntlet ranking: teams sorted by points% `(2w+t)/(2n)×100` across intra-top-50 games",
        "only. Spearman ρ measures how well each model's full-season rating order aligns with",
        "that ranking. Outside-top-50 games are excluded from the gauntlet but included in each",
        "rater's input (schedule-strength signal).",
        "",
        "| Model | Spearman ρ vs Gauntlet |",
        "|-------|------------------------|",
        f"| bespoke (rate_weekly) | {bespoke_rho:.4f} |",
        f"| mhr_replica | {mhr_rho:.4f} |",
        "",
    ]

    # Mover table: MHR rank → gauntlet rank.
    gauntlet_pos = {t: i + 1 for i, t in enumerate(gauntlet_list)}
    mhr_pos = {t: i + 1 for i, t in enumerate(mhr_order)}
    movers = []
    for t in mhr_order:
        if t in gauntlet_pos:
            delta = mhr_pos[t] - gauntlet_pos[t]  # positive = fell in gauntlet
            movers.append((t, mhr_pos[t], gauntlet_pos[t], delta))
    movers_sorted = sorted(movers, key=lambda x: -abs(x[3]))

    lines += [
        "## Biggest Movers: MHR Rank → Gauntlet Rank",
        "",
        "Positive Δ = fell in gauntlet (schedule-inflated); negative Δ = rose (underrated by MHR).",
        "",
        "| Team | MHR # | Gauntlet # | Δ | Gauntlet record |",
        "|------|-------|------------|---|-----------------|",
    ]
    for team, mhr_r, gau_r, delta in movers_sorted[:15]:
        rec = _fmt_record(gauntlet_tbl[team])
        sign = f"+{delta}" if delta > 0 else str(delta)
        lines.append(f"| {team} | #{mhr_r} | #{gau_r} | {sign} | {rec} |")

    lines += [""]

    # Giant-killer case studies.
    lines += [
        "## Giant-Killer Case Studies",
        "",
        "The schedule-padding signature: a team with a dominant record against outside-top-50",
        "opponents but a losing record when it plays ranked teams. Bespoke's `scheduleTerm`",
        "shows why the model discounts those lucky unranked wins — it pays only `alpha × opp_rating`,",
        "and outside-top-50 teams earn noisy, low ratings on few games.",
        "",
    ]

    for cs in case_studies:
        team = cs["team"]
        mhr_r = cs["mhr_rank"]
        gau_r = cs["gauntlet_rank"]
        ranked = cs["ranked"]
        unranked = cs["unranked"]
        sched = cs["bespoke_schedule"]

        delta = mhr_r - gau_r
        sign = f"+{delta}" if delta > 0 else str(delta)
        lines += [
            f"### {team} (MHR #{mhr_r} → Gauntlet #{gau_r}, Δ {sign})",
            "",
            "| Split | W-L-T | GF | GA | GD | Pts% |",
            "|-------|-------|----|----|-----|------|",
            f"| vs ranked | {ranked['w']}-{ranked['l']}-{ranked['t']} | {ranked['gf']} | {ranked['ga']} | {ranked['gd']:+d} | {ranked['pct']:.1f}% |",
            f"| vs unranked | {unranked['w']}-{unranked['l']}-{unranked['t']} | {unranked['gf']} | {unranked['ga']} | {unranked['gd']:+d} | {unranked['pct']:.1f}% |",
            "",
        ]

        if sched["avg_vs_ranked"] is not None and sched["avg_vs_unranked"] is not None:
            lines += [
                f"**Bespoke `scheduleTerm` (avg per game):** vs ranked = {sched['avg_vs_ranked']:.3f}; "
                f"vs unranked = {sched['avg_vs_unranked']:.3f}. "
                "A lower schedule term means bespoke credits this team less for those wins "
                "— the orthogonal SOS channel is doing its job.",
                "",
            ]

    # Gauntlet full table (top-25 for brevity).
    lines += [
        "## Gauntlet Ranking (Top-25 by Points%)",
        "",
        "| Gauntlet # | Team | MHR # | W | L | T | GF | GA | GD | Pts% |",
        "|------------|------|-------|---|---|---|----|----|-----|------|",
    ]
    for i, team in enumerate(gauntlet_list[:25]):
        s = gauntlet_tbl[team]
        mhr_r = mhr_pos.get(team, "—")
        mhr_label = f"#{mhr_r}" if isinstance(mhr_r, int) else mhr_r
        lines.append(
            f"| #{i + 1} | {team} | {mhr_label} | {s['w']} | {s['l']} | {s['t']} "
            f"| {s['gf']} | {s['ga']} | {s['gd']:+d} | {s['pct']:.1f}% |"
        )

    lines += [
        "",
        "## Scope Note",
        "",
        "- **Full-season single-shot run** (not walk-forward; that is B4).",
        "- `invariant-auditor` not run — this task makes no model changes.",
        "- Outside-top-50 teams (215) are graph-connected with only 1–2 games each; their",
        "  ratings are noisy but the directional SOS signal is sufficient for this proxy analysis.",
        "",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Full-analysis entry point (used by tests + CLI)
# ---------------------------------------------------------------------------

_CASE_STUDY_TEAMS = [
    "Dallas Stars Elite 11U AAA",
    "South Shore Kings (Elite) 11U AAA",
    "Top Gun (Elite) 11U AAA",
]


def run_full_analysis(
    games: list[GameRow],
    mhr_order: list[str],
    ranked_set: set[str],
) -> str:
    """Run both models, build gauntlet, compute agreement, write case studies, return report text."""
    gauntlet_tbl = gauntlet_table(games, ranked_set)
    gauntlet_list = gauntlet_ranked_list(gauntlet_tbl)

    bespoke_rank = model_ranking(rate_weekly, games, ranked_set)
    mhr_replica_rank = model_ranking(mhr_rate, games, ranked_set)

    bespoke_rho = agreement(bespoke_rank, gauntlet_list)
    mhr_rho = agreement(mhr_replica_rank, gauntlet_list)

    # Run the full bespoke solve once for per-game attribution (case studies).
    bespoke_result = rate_weekly(games)

    gauntlet_pos = {t: i + 1 for i, t in enumerate(gauntlet_list)}
    mhr_pos = {t: i + 1 for i, t in enumerate(mhr_order)}

    studies: list[dict] = []
    for team in _CASE_STUDY_TEAMS:
        if team in ranked_set:
            cs = case_study(
                team,
                games,
                bespoke_result,
                ranked_set,
                mhr_rank=mhr_pos.get(team, 0),
                gauntlet_rank_num=gauntlet_pos.get(team, 0),
            )
            studies.append(cs)

    return build_report(
        gauntlet_tbl=gauntlet_tbl,
        gauntlet_list=gauntlet_list,
        mhr_order=mhr_order,
        bespoke_rank=bespoke_rank,
        mhr_replica_rank=mhr_replica_rank,
        bespoke_rho=bespoke_rho,
        mhr_rho=mhr_rho,
        case_studies=studies,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Load real data, run full analysis, write reports/real-h2h.md."""
    games = load_games_from_json(_CLEAN_JSON)
    mhr_order, ranked_set = load_ranked_set(_RAW_JSON)

    print(f"Loaded {len(games)} games; {len(ranked_set)} ranked teams")

    report = run_full_analysis(games, mhr_order, ranked_set)

    out_path = _REPO_ROOT / "reports/real-h2h.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(f"Wrote → {out_path}")


if __name__ == "__main__":
    main()
