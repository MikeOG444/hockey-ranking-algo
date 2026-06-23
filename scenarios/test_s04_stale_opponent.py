"""Scenario 4 — Stale opponent / float (I10).

T_EARLY_STRONG is strong at the start but uses a 'falling' trajectory (declining attack).
T_BENEFICIARY beats T_EARLY_STRONG in week 1 (when it's at peak strength).
T_CONTROL beats a constant-strength opponent of average strength (same margin, also week 1).

By end of season, T_EARLY_STRONG has declined — the solver (re-)rates it lower. The floating
schedule term (I10) should de-inflate T_BENEFICIARY's credit relative to T_CONTROL, because
the opponent it beat is now recognized as weak.

Assert: T_BENEFICIARY's rating ≤ T_CONTROL's rating (the stale inflated credit was washed away).

Invariants stressed: I10 (floating opponent strength re-rates schedule credit).
"""

from models.bespoke import rate_weekly
from scenarios.builders import build_s04_stale_opponent


def test_s04_beneficiary_not_inflated():
    """T_BENEFICIARY's rating should be ≤ T_CONTROL after the stale opponent declines."""
    dataset, meta = build_s04_stale_opponent()
    result = rate_weekly(dataset.games)
    r = result.ratings

    beneficiary = r["T_BENEFICIARY"]
    control = r["T_CONTROL"]

    # Allow a tiny tolerance: the opponent's decline should de-inflate beneficiary below or at control.
    assert beneficiary <= control + 0.05, (
        f"Expected T_BENEFICIARY ({beneficiary:.4f}) <= T_CONTROL ({control:.4f}): "
        f"I10 stale-credit float failed. Full ratings: {r}"
    )
