"""Scenario 5 — Giant-killer / noise (robustness).

T_LUCKY has a weak true rating (-0.5) but the seeded Poisson draws produce a lucky early run
(4/5 wins in the opening weeks). T_ACTUAL_STRONG has a strong true rating (+1.0) and a similar
record. Over enough games the model should surface T_ACTUAL_STRONG above T_LUCKY because their
opponents' actual strength tells the real story.

The trend signal should expose T_LUCKY's lucky run: its rating trend should be ≤ 0 or very small
(not steadily rising) since its underlying strength is weak.

Invariants stressed: noise robustness (not a numbered invariant but a foundational requirement).
"""

from models.bespoke import rate_weekly
from scenarios.builders import build_s05_giant_killer


def test_s05_strong_above_lucky():
    dataset, meta = build_s05_giant_killer()
    result = rate_weekly(dataset.games)
    r = result.ratings

    actual = r["T_ACTUAL_STRONG"]
    lucky = r["T_LUCKY"]
    assert actual > lucky, (
        f"Expected T_ACTUAL_STRONG ({actual:.4f}) > T_LUCKY ({lucky:.4f}). "
        f"Model fooled by lucky run. Full ratings: {r}"
    )


def test_s05_lucky_trend_nonpositive():
    """T_LUCKY's trend should be ≤ 0 or negligible — luck doesn't produce a sustained rise."""
    dataset, _ = build_s05_giant_killer()
    result = rate_weekly(dataset.games)
    trend = result.trend.get("T_LUCKY", 0.0)
    assert trend <= 0.1, (
        f"T_LUCKY trend = {trend:.4f} — model sees a sustained upward trend for a weak team (threshold 0.1)"
    )
