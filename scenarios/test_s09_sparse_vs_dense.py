"""Scenario 9 — Sparse early vs dense late (convergence stability).

T_SPARSE plays only 4 games across the season; T_DENSE plays 20+ games; both have the same true
strength and play the same opponents when they do play. Over ≥8 weeks the dense team accumulates
enough evidence to recover its true ordinal position more accurately than the sparse team.

Asserts:
- Both teams have finite, defined ratings.
- T_DENSE's rank is closer to its true ordinal than T_SPARSE's (measured by rank error relative
  to all teams in the league). The inline computation avoids importing harness/metrics.

No numbered invariant — this tests convergence stability under information scarcity.
"""

import math

from models.bespoke import rate_weekly
from scenarios.builders import build_s09_sparse_vs_dense


def test_s09_both_finite():
    dataset, meta = build_s09_sparse_vs_dense()
    result = rate_weekly(dataset.games)
    r = result.ratings
    assert math.isfinite(r["T_SPARSE"]), f"T_SPARSE rating not finite: {r['T_SPARSE']}"
    assert math.isfinite(r["T_DENSE"]), f"T_DENSE rating not finite: {r['T_DENSE']}"


def test_s09_dense_rank_closer_to_truth():
    """T_DENSE's recovered rank should be closer to the true ordinal than T_SPARSE's."""
    dataset, meta = build_s09_sparse_vs_dense()
    result = rate_weekly(dataset.games)
    r = result.ratings

    # True ordinal position: use ground_truth from the dataset (attack - defense = true rating).
    true_ratings = {t.id: t.attack - t.defense for t in dataset.ground_truth}
    sorted_true = sorted(true_ratings, key=lambda t: -true_ratings[t])
    true_rank = {t: i for i, t in enumerate(sorted_true)}

    sorted_recovered = sorted(r, key=lambda t: -r[t])
    recovered_rank = {t: i for i, t in enumerate(sorted_recovered)}

    err_sparse = abs(recovered_rank["T_SPARSE"] - true_rank["T_SPARSE"])
    err_dense = abs(recovered_rank["T_DENSE"] - true_rank["T_DENSE"])

    assert err_dense <= err_sparse, (
        f"Expected T_DENSE rank error ({err_dense}) ≤ T_SPARSE rank error ({err_sparse}). "
        f"Dense true rank={true_rank['T_DENSE']}, recovered={recovered_rank['T_DENSE']}. "
        f"Sparse true rank={true_rank['T_SPARSE']}, recovered={recovered_rank['T_SPARSE']}."
    )
