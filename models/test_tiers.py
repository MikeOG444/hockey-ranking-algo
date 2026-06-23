"""Tier detection + frozen-window tests (memo §4, §5; brief §1.8, §2).

`detect_tiers` turns a converged rating vector into 1-indexed bands by natural gaps (no hardcoded
ranks). `TierWindow` is the anti-whipsaw machinery (I13): a recency-weighted read of an opponent's
tier over the last ≤4 finalized weeks, plus a consistency measure that reads low for a team that
bounces between tiers. These are pure, deterministic functions (I8) with no RNG.
"""

import pytest

from models.tiers import TierWindow, detect_tiers


# --- detect_tiers ---------------------------------------------------------------------------


def test_detect_tiers_splits_on_known_gap():
    """auto mode, c=2.0: the only gap that exceeds 2*median splits A,B from C,D.

    Ratings A=1.0, B=0.9 (gap 0.1), then a 0.9 gap down to C=0.0, D=-0.1 (gap 0.1).
    median gap = 0.1, threshold = 0.2; only the 0.9 gap cuts. Top band = tier 1."""
    ratings = {"A": 1.0, "B": 0.9, "C": 0.0, "D": -0.1}
    tiers = detect_tiers(ratings, tier_count="auto", gap_c=2.0)
    assert tiers == {"A": 1, "B": 1, "C": 2, "D": 2}


def test_detect_tiers_integer_count():
    """tierCount=3 pins exactly two cuts (the two largest gaps) → three monotone bands."""
    ratings = {"A": 1.0, "B": 0.9, "C": 0.0, "D": -0.1}
    tiers = detect_tiers(ratings, tier_count=3)
    assert len(set(tiers.values())) == 3
    # The widest gap (B|C) must be a band boundary, and tiers only descend with rating (I8 stable).
    assert tiers["A"] <= tiers["B"] < tiers["C"] <= tiers["D"]
    assert tiers["A"] == 1


def test_detect_tiers_single_tier_fallback():
    """Even gaps → no gap beats the threshold → everyone in tier 1 (the field, brief §2)."""
    ratings = {"A": 1.0, "B": 0.9, "C": 0.8, "D": 0.7}
    tiers = detect_tiers(ratings, tier_count="auto", gap_c=2.0)
    assert set(tiers.values()) == {1}


def test_detect_tiers_integer_count_raises_on_too_few_values():
    """tierCount=N with fewer than N distinct ratings cannot place N-1 cuts → error."""
    with pytest.raises(ValueError):
        detect_tiers({"A": 1.0, "B": 1.0}, tier_count=3)


def test_detect_tiers_is_order_independent():
    """I8: the input dict order never changes the assignment."""
    a = detect_tiers({"A": 1.0, "B": 0.9, "C": 0.0, "D": -0.1})
    b = detect_tiers({"D": -0.1, "C": 0.0, "B": 0.9, "A": 1.0})
    assert a == b


# --- TierWindow: frozen read + consistency --------------------------------------------------


def test_tier_window_cold_start_returns_none():
    """No finalized weeks yet → frozen_tier is None (caller runs tier-agnostic, m=p=1)."""
    window = TierWindow(max_weeks=4)
    assert window.frozen_tier("X") is None


def test_tier_window_single_week_is_exact():
    """One finalized week → the frozen read is just that week's tier (weight = 1)."""
    window = TierWindow(max_weeks=4)
    window.add_week(1, {"A": 2, "B": 3})
    assert window.frozen_tier("A") == pytest.approx(2.0)
    assert window.frozen_tier("B") == pytest.approx(3.0)


def test_tier_window_damps_blip():
    """A one-week blip (tier 1 in week 2) leaves the recency-weighted read much nearer the
    sustained tier 3 than the blip value of 1 → the heart of I13 at the window level."""
    window = TierWindow(max_weeks=4)
    window.add_week(1, {"X": 3})
    window.add_week(2, {"X": 1})  # blip
    window.add_week(3, {"X": 3})
    window.add_week(4, {"X": 3})
    frozen = window.frozen_tier("X", rho=1.0)
    assert abs(frozen - 3.0) < abs(frozen - 1.0)
    assert frozen > 2.5  # clearly closer to 3 than to the blip


def test_tier_window_keeps_only_last_four_weeks():
    """max_weeks=4: a fifth week evicts week 1 (the window is a sliding ≤4-week read)."""
    window = TierWindow(max_weeks=4)
    for w in range(1, 6):  # weeks 1..5; team Y is tier 4 in week 1, tier 1 afterwards
        window.add_week(w, {"Y": 4 if w == 1 else 1})
    # Week 1 (tier 4) is gone; only weeks 2-5 (all tier 1) remain → exactly 1.0.
    assert window.frozen_tier("Y", rho=1.0) == pytest.approx(1.0)


def test_consistency_stable_team():
    """A team that holds one tier across the window reads maximal consistency (≈ 1.0)."""
    window = TierWindow(max_weeks=4)
    for w in range(1, 5):
        window.add_week(w, {"A": 2})
    assert window.consistency("A") == pytest.approx(1.0)


def test_consistency_volatile_team():
    """A team alternating between the extreme tiers reads low consistency (< 0.5)."""
    window = TierWindow(max_weeks=4)
    for w, t in zip(range(1, 5), (1, 4, 1, 4)):
        window.add_week(w, {"B": t})
    assert window.consistency("B") < 0.5
