"""Scenario 14 — Closing-schedule disparity (TASK-17).

The deterministic synthetic mirror of the real Woodbridge/Mid-Fairfield finding
(`docs/analysis/closing-schedule-floor-cost.md`). Two subjects with an IDENTICAL early body of work
diverge only in their closing schedule:

  - HONEST loses every late game by 1 goal (2-3) to a genuine elite — honorable losses.
  - PADDER beats every late game 4-1 over a genuine bottom team — soft padding.

Planted truth: HONEST is the stronger team (+0.9 vs +0.3). Hanging within one goal of elites
demonstrates more strength than beating cans, so the model MUST rank HONEST >= PADDER.

This test FAILS on the pre-TASK-17 model: the 3.0 win floor lets a cheap win out-credit an honorable
elite loss (whose credit is capped at alpha*R_elite < 3), and recency amplifies the late games, so the
old model ranks PADDER above HONEST — inverting the truth. It passes once per-game credit is recentered
on `own_rating + surprise` (TASK-17), which makes the soft win ~neutral and the elite loss ~neutral-or-up.

Do NOT weaken this assertion to make it pass; the fix is in the model, not the test.
"""

from models.bespoke import rate_weekly
from scenarios.builders import build_s14_closing_schedule


def test_s14_honest_at_least_padder():
    """HONEST (honorable elite losses late) must rank >= PADDER (soft wins late)."""
    dataset, meta = build_s14_closing_schedule()
    result = rate_weekly(dataset.games)
    r = result.ratings

    # Context guard (mirrors S07): the tier spread must actually materialize, else the test is vacuous.
    elite_mean = sum(r[e] for e in meta["elite_ids"]) / len(meta["elite_ids"])
    weak_mean = sum(r[w] for w in meta["weak_ids"]) / len(meta["weak_ids"])
    assert elite_mean > 0 > weak_mean, (
        f"Tier spread did not form: elite_mean={elite_mean:.4f}, weak_mean={weak_mean:.4f}. "
        f"S14 needs genuine elites (above mean) and genuine weak teams (below mean)."
    )

    honest = r["HONEST"]
    padder = r["PADDER"]
    assert honest >= padder, (
        f"Closing-schedule inversion: HONEST ({honest:.4f}) ranked BELOW PADDER ({padder:.4f}). "
        f"A team padding soft late wins out-ranks a team losing honorably to elites. "
        f"Full ratings: {r}"
    )
