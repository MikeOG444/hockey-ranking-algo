"""Real-data evaluation gate — the project's headline adjudicator (TASK-19 / Phase B2+).

The 2026-06-24 pivot: the synthetic §7 rank-recovery score is partly an artifact of the
old `base=3` floor's accidental anchoring (see `reports/comparison.md` §4), so it is no
longer trusted as the accuracy gate. This module scores every model against signal we
actually have from the real MHR 2025-26 11U AAA season:

1. **Head-to-head gauntlet agreement** — Spearman ρ between each model's full-season
   rating order and the gauntlet (intra-ranked who-actually-beat-whom record). This is
   the *headline* axis: it scores against real outcomes, never a model-derived value.
2. **Published-rank agreement** — Spearman ρ between each model's order and MHR's own
   published top-50 rank order. MHR's published ranks are an external artifact, not a
   value our models produced, so this respects the observed-vs-derived wall.

The **gate verdict** is bespoke vs the MHR replica on the headline (gauntlet) axis: the
pivot made the gauntlet the adjudicator, so bespoke must agree with real results at least
as well as the replica it intends to replace. The synthetic suite is demoted to targeted
invariant/mechanism unit tests (S01–S14 still guard I1–I13) — diagnostic, not the gate.

Design constraints (CLAUDE.md):
- **Determinism (I8):** pure functions, stable model order, fixed float precision → the
  report regenerates byte-identically.
- **Observed-vs-derived wall:** score against real *results* and *published* ranks; never
  feed a model's own rating back in as truth.
- **No model changes:** consumes the raters read-only.
- Reuses `analysis.head_to_head` primitives (numpy-only — deliberately avoids
  `harness.metrics`, which pulls in the synthetic generator/scipy stack).

Out of scope: B4 walk-forward / log-loss / calibration — this is a ranking-agreement gate,
not a predictive one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from analysis.head_to_head import (
    agreement,
    gauntlet_ranked_list,
    gauntlet_table,
    load_games_from_json,
    load_ranked_set,
    model_ranking,
)
from core.game import GameRow
from models.bespoke import rate_weekly
from models.mhr_replica import rate as mhr_rate
from models.ridge_massey import rate as ridge_rate

# Canonical, deterministic model order used everywhere in this module and the report.
# (name, rate_fn) — bespoke first (the candidate), then the two benchmarks.
CANONICAL_MODELS = [
    ("bespoke", rate_weekly),
    ("mhr_replica", mhr_rate),
    ("ridge_massey", ridge_rate),
]

_FLOAT_FMT = "{:.4f}"
_REPO_ROOT = Path(__file__).parent.parent
_OUT_PATH = _REPO_ROOT / "reports/real-eval.md"


@dataclass(frozen=True)
class ModelScore:
    """One model's agreement with the two real-data yardsticks.

    gauntlet_rho — Spearman ρ vs the head-to-head gauntlet (the headline gate axis).
    mhr_rho      — Spearman ρ vs MHR's published top-50 rank order.
    """

    name: str
    gauntlet_rho: float
    mhr_rho: float


# ---------------------------------------------------------------------------
# Pure scoring
# ---------------------------------------------------------------------------


def score_ranking(
    model_rank: list[str],
    gauntlet_list: list[str],
    mhr_order: list[str],
) -> tuple[float, float]:
    """Score one model's ranking against both real-data yardsticks.

    Returns (gauntlet_rho, mhr_rho). Both use the analysis-module Spearman over the
    team-name intersection, so a model ordering identical to a yardstick scores 1.0 and a
    fully reversed one scores -1.0.
    """
    gauntlet_rho = agreement(model_rank, gauntlet_list)
    mhr_rho = agreement(model_rank, mhr_order)
    return gauntlet_rho, mhr_rho


def evaluate_models(
    games: list[GameRow],
    mhr_order: list[str],
    ranked_set: set[str],
) -> list[ModelScore]:
    """Run every canonical model on the game log and score it on both real-data axes.

    The gauntlet is computed once from the game log (observed-vs-derived wall). Each model
    rates the full log; outside-top-50 teams stay in the rater input (schedule-strength
    signal) but only ranked teams are scored. Returns scores in CANONICAL_MODELS order.
    """
    gauntlet_list = gauntlet_ranked_list(gauntlet_table(games, ranked_set))

    scores: list[ModelScore] = []
    for name, rate_fn in CANONICAL_MODELS:
        rank = model_ranking(rate_fn, games, ranked_set)
        gauntlet_rho, mhr_rho = score_ranking(rank, gauntlet_list, mhr_order)
        scores.append(ModelScore(name=name, gauntlet_rho=gauntlet_rho, mhr_rho=mhr_rho))
    return scores


# ---------------------------------------------------------------------------
# Gate verdict
# ---------------------------------------------------------------------------


def gate_verdict(scores: list[ModelScore]) -> dict:
    """Decide the gate: bespoke vs the MHR replica on the headline (gauntlet) axis.

    PASS iff bespoke's gauntlet agreement is at least the MHR replica's — the candidate
    must agree with who-actually-beat-whom no worse than the model it aims to replace.
    Returns the bespoke/replica gauntlet ρ, their signed margin, and the boolean verdict.
    """
    by_name = {s.name: s for s in scores}
    bespoke = by_name["bespoke"].gauntlet_rho
    mhr = by_name["mhr_replica"].gauntlet_rho
    margin = bespoke - mhr
    return {
        "passed": bespoke >= mhr,
        "bespoke": bespoke,
        "mhr_replica": mhr,
        "margin": margin,
    }


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_report(
    scores: list[ModelScore],
    verdict: dict,
    n_games: int,
    n_ranked: int,
) -> str:
    """Build the deterministic markdown report (reports/real-eval.md).

    All inputs are plain data derived from the game log and model outputs — no wall-clock,
    no RNG, fixed float precision → byte-identical on every call with the same inputs.
    """
    status = "PASS" if verdict["passed"] else "FAIL"
    margin = verdict["margin"]
    margin_str = (f"+{margin:.4f}" if margin >= 0 else f"{margin:.4f}")

    lines: list[str] = [
        "# Real-Data Evaluation Gate — MHR 2025-26 USA 11U AAA Top-50",
        "",
        "Generated by `python -m harness.real_gate`. This file is a committed, diffable",
        "artifact and **regenerates byte-identically** — asserted by",
        "`harness/test_real_gate.py::test_report_is_deterministic`.",
        "",
        "> **This is the headline gate** (owner pivot, 2026-06-24). The synthetic §7",
        "> rank-recovery suite (`reports/comparison.md`) is now **diagnostic, not the gate**:",
        "> its score was partly an artifact of the old `base=3` floor's anchoring, so it no",
        "> longer adjudicates accuracy. The §7 scenarios remain as targeted invariant/mechanism",
        "> unit tests (S01–S14 still guard I1–I13). Walk-forward prediction (log-loss /",
        "> calibration) is Stage-B Phase B4 and remains out of scope here — this is a",
        "> ranking-*agreement* gate, not a predictive one.",
        "",
        "## Gate verdict",
        "",
        f"**{status}** — bespoke vs the MHR replica on head-to-head gauntlet agreement "
        f"(margin {margin_str}).",
        "",
        "The gauntlet (intra-ranked who-actually-beat-whom record) is the adjudicator the",
        "pivot chose: bespoke must agree with real results at least as well as the MHR replica",
        "it intends to replace. The gauntlet is computed purely from the game log — no model",
        "rating is ever fed back in as truth (observed-vs-derived wall).",
        "",
        "## Agreement with real-data yardsticks",
        "",
        "Spearman ρ (rank correlation, higher is better) of each model's full-season rating",
        "order against two yardsticks scored over the top-50 ranked teams:",
        "",
        "- **vs Gauntlet** — the head-to-head record (real outcomes). *Headline axis.*",
        "- **vs MHR published** — MHR's own published rank order (external artifact, not a",
        "  value our models derived).",
        "",
        "| Model | ρ vs Gauntlet | ρ vs MHR published |",
        "|-------|---------------|--------------------|",
    ]
    for s in scores:
        lines.append(
            f"| {s.name} | {_FLOAT_FMT.format(s.gauntlet_rho)} "
            f"| {_FLOAT_FMT.format(s.mhr_rho)} |"
        )

    lines += [
        "",
        "**Reading the table.** The gauntlet column is the gate; the MHR-published column is",
        "context. A high MHR-published ρ for `mhr_replica` is expected — it reverse-engineers",
        "MHR's own method, so agreeing with MHR's ranks is reproduction, not independent",
        "accuracy. Bespoke is judged on the *gauntlet*, where the yardstick is who won.",
        "",
        "## Scope",
        "",
        f"- Dataset: {n_games} deduped Level-0 games; {n_ranked} ranked teams "
        "(plus outside-top-50 opponents kept in rater input for schedule strength).",
        "- **Full-season single-shot run** (not walk-forward; that is B4).",
        "- No model changes — models consumed read-only; `invariant-auditor` not required.",
        "- Companion analysis (biggest movers, giant-killer case studies): `reports/real-h2h.md`.",
        "",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Real-data inputs + CLI entry point
# ---------------------------------------------------------------------------


def load_real_inputs() -> tuple[list[GameRow], list[str], set[str]]:
    """Load the real MHR game log + published rank order + ranked set."""
    games = load_games_from_json()
    mhr_order, ranked_set = load_ranked_set()
    return games, mhr_order, ranked_set


def run_full_evaluation() -> str:
    """Load real data, score all models, decide the gate, return the report text."""
    games, mhr_order, ranked_set = load_real_inputs()
    scores = evaluate_models(games, mhr_order, ranked_set)
    verdict = gate_verdict(scores)
    return build_report(scores, verdict, n_games=len(games), n_ranked=len(ranked_set))


def main() -> None:
    """Load real data, run the gate, write reports/real-eval.md."""
    report = run_full_evaluation()
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OUT_PATH.write_text(report)
    print(f"Wrote → {_OUT_PATH}")


if __name__ == "__main__":
    main()
