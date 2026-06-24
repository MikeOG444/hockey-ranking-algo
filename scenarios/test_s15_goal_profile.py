"""Scenario 15 — Opponent-relative goal-profile residual (TASK-18).

The deterministic confirming scenario for the goal-profile residual
(`docs/analysis/goal-profile-residual.md`). Two subjects, OVER and UNDER, play the SAME opponents
with results in the SAME margin buckets (every game a "close" win) — so the TASK-17 model, which
reads only `base`, the margin bucket, and who you played, rates them BYTE-IDENTICALLY equal. They
differ only in the exact goals:

  - OVER scores ABOVE each opponent's typical goals-allowed and holds them BELOW their typical
    goals-for (over-performs the baseline).
  - UNDER meets or undershoots those baselines at the same buckets.

Planted truth: OVER is the stronger team. The model MUST rank OVER >= UNDER.

This test FAILS on the shipped model by design: the model does NOT read the goal profile, so it
returns r[OVER] == r[UNDER] exactly and the strict assertion fails. That is the **expected** outcome.

**SHELVED (TASK-18, 2026-06-24).** The opponent-relative residual was prototyped and measured against
the real-data gauntlet (the owner's evaluation gate). It could not be shown to help: a β-sweep found
real-gauntlet agreement falls monotonically as the residual strengthens (β=0.05 dropped bespoke from
0.8351 to 0.8031, below the MHR replica's 0.8296), and no β improved it. The owner shelved the term as
a documented negative result, to be revisited when walk-forward prediction (Stage-B B4) provides a real
accuracy adjudicator. Full write-up: ``docs/analysis/goal-profile-residual.md``.

This scenario is kept as an ``xfail`` so the negative result stays under test: it pins exactly what the
shipped model deliberately does NOT do (read the goal profile), and ``strict=True`` means it will flag
loudly (XPASS) the day a residual is reintroduced — prompting whoever does so to remove this marker.
"""

import pytest

from models.bespoke import rate_weekly
from scenarios.builders import build_s15_goal_profile


@pytest.mark.xfail(
    reason="Goal-profile residual shelved (TASK-18): the model deliberately does not read the goal "
    "profile — it could not be shown to help the real-data gauntlet. See "
    "docs/analysis/goal-profile-residual.md.",
    strict=True,
)
def test_s15_over_at_least_under():
    """OVER (beats opponents' goal baselines) must rank strictly above UNDER (meets/undershoots)."""
    dataset, meta = build_s15_goal_profile()
    result = rate_weekly(dataset.games)
    r = result.ratings

    over = r["OVER"]
    under = r["UNDER"]
    assert over > under, (
        f"Goal-profile residual not read: OVER ({over:.6f}) did not rank above UNDER ({under:.6f}). "
        f"Both have identical records, opponents, and margin buckets — OVER over-performs each "
        f"opponent's GF/GA baseline, so it must rank higher. Full ratings: {r}"
    )
