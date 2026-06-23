"""Truth-scoring metrics for the model-agnostic harness (TASK-10).

Scores a RateResult against the generator's planted ground truth. Three metrics:

  spearman_rho   — rank correlation between recovered and true ratings (primary Stage-A signal).
  centered_rmse  — RMS error after centering both vectors to zero mean (scale-invariant).
  tier_accuracy  — fraction placed in the correct tier under the best label permutation.

All three are pure output consumers — they never feed scores back into any solve (observed-vs-
derived wall, brief §5). No scipy: Spearman is computed via numpy argsort + corrcoef.
"""

import itertools
from dataclasses import dataclass

import numpy as np

from generator.simulate import TeamParams, week_params
from models.bespoke import RateResult


@dataclass(frozen=True)
class MetricsResult:
    spearman_rho: float      # Spearman rank correlation vs true ratings; range [-1, 1]
    centered_rmse: float     # RMSE after centering both vectors; >= 0; lower is better
    tier_accuracy: float     # fraction correct under best-matching permutation; [0, 1]
    n_teams: int             # teams present in both ground_truth and result.ratings
    n_tiers_scored: int      # teams with a non-None true tier included in tier_accuracy


def spearman_rho(true_ratings: dict[str, float], model_ratings: dict[str, float]) -> float:
    """Spearman rank correlation between true and model ratings over the key intersection.

    Uses dense ranks via argsort(argsort(v)) and numpy.corrcoef. Returns 0.0 when fewer
    than 2 teams are in the intersection (correlation is undefined).
    """
    keys = sorted(set(true_ratings) & set(model_ratings))
    if len(keys) < 2:
        return 0.0
    t = np.array([true_ratings[k] for k in keys], dtype=float)
    m = np.array([model_ratings[k] for k in keys], dtype=float)
    t_rank = np.argsort(np.argsort(t)).astype(float)
    m_rank = np.argsort(np.argsort(m)).astype(float)
    return float(np.corrcoef(t_rank, m_rank)[0, 1])


def centered_rmse(true_ratings: dict[str, float], model_ratings: dict[str, float]) -> float:
    """RMSE after centering both vectors to zero mean over the key intersection.

    Centering makes the metric independent of absolute scale conventions (both bespoke's
    zero-mean gauge and any benchmark's arbitrary offset vanish before the comparison).
    Returns 0.0 when the intersection is empty.
    """
    keys = sorted(set(true_ratings) & set(model_ratings))
    if not keys:
        return 0.0
    t = np.array([true_ratings[k] for k in keys], dtype=float)
    m = np.array([model_ratings[k] for k in keys], dtype=float)
    t_c = t - t.mean()
    m_c = m - m.mean()
    return float(np.sqrt(np.mean((t_c - m_c) ** 2)))


def tier_accuracy(true_tiers: dict[str, int], model_tiers: dict[str, int]) -> float:
    """Fraction of teams placed in the correct tier under the best label permutation.

    Finds the bijection between the union of all label values that maximises the match
    fraction, using itertools.permutations. For <=5 tiers the search space is <=120.
    Returns 0.0 when the intersection of teams in both dicts is empty.
    """
    common = sorted(set(true_tiers) & set(model_tiers))
    if not common:
        return 0.0
    true_vals = [true_tiers[k] for k in common]
    model_vals = [model_tiers[k] for k in common]
    # Try all bijections over the union of label values that appear in either dict.
    all_labels = sorted(set(true_vals) | set(model_vals))
    best = 0
    for perm in itertools.permutations(all_labels):
        mapping = {label: perm[i] for i, label in enumerate(all_labels)}
        matches = sum(mapping[t] == m for t, m in zip(true_vals, model_vals))
        if matches > best:
            best = matches
    return best / len(common)


def point_in_time_truth(
    ground_truth: list[TeamParams],
    n_weeks: int,
) -> dict[str, float]:
    """Return each team's realized end-of-season rating via the generator's week_params.

    For a flat team week_params returns the raw baseline (attack, defense), so
    attack − defense == TeamParams.rating — static scenarios score byte-identically.
    For a drifting team (rising/falling/blip) this returns the end-of-season form,
    which is the correct truth for a recency-aware model (I11).

    This is generator ground truth accessed through week_params — it is never a
    recovered model rating fed back in (observed-vs-derived wall, brief §5). week_params
    is a pure function (no RNG, no wall-clock), so determinism (I8) is preserved.
    """
    result: dict[str, float] = {}
    for t in ground_truth:
        atk, dfn = week_params(t, n_weeks)
        result[t.id] = atk - dfn
    return result


def score_model(
    ground_truth: list[TeamParams],
    result: RateResult,
    truth_ratings: dict[str, float] | None = None,
) -> MetricsResult:
    """Score a RateResult against the generator's planted ground truth.

    Only teams present in both ground_truth (by .id) and result.ratings (by key) are
    included. n_teams records the intersection size. Teams with TeamParams.tier=None are
    excluded from tier scoring; if result.tiers is empty, n_tiers_scored is 0.

    truth_ratings — optional override for Spearman/RMSE comparison. When provided,
    these values replace the static TeamParams.rating for each team. Tier scoring always
    uses the static TeamParams.tier (tier labels don't drift week to week). Pass
    point_in_time_truth(ground_truth, n_weeks) here for trajectory scenarios.
    Default None → today's static behaviour exactly (no existing test moves).
    """
    true_map = {t.id: t for t in ground_truth}
    common = sorted(set(true_map) & set(result.ratings))
    n_teams = len(common)

    # Use the caller-supplied truth override when provided; fall back to static rating.
    # truth_ratings must cover every team in common — a missing key is a caller contract
    # violation (point_in_time_truth always covers all ground_truth teams, so this can't
    # fire in production, but a KeyError here is better than a silently biased metric).
    if truth_ratings is not None:
        true_ratings = {k: truth_ratings[k] for k in common}
    else:
        true_ratings = {k: true_map[k].rating for k in common}
    model_ratings_sub = {k: result.ratings[k] for k in common}

    # True tiers restricted to teams with non-None true tier in the intersection.
    true_tiers_notnone: dict[str, int] = {
        k: true_map[k].tier  # type: ignore[assignment]
        for k in common
        if true_map[k].tier is not None
    }
    # Model tiers restricted to teams that also have a non-None true tier.
    model_tiers_sub = {k: result.tiers[k] for k in true_tiers_notnone if k in result.tiers}
    n_tiers_scored = len(model_tiers_sub)

    rho = spearman_rho(true_ratings, model_ratings_sub)
    rmse = centered_rmse(true_ratings, model_ratings_sub)
    tier_acc = tier_accuracy(true_tiers_notnone, model_tiers_sub)

    return MetricsResult(
        spearman_rho=rho,
        centered_rmse=rmse,
        tier_accuracy=tier_acc,
        n_teams=n_teams,
        n_tiers_scored=n_tiers_scored,
    )
