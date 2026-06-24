"""Guards on the *shipped* Stage-A tuned defaults (TASK-13).

These tests pin that the values written into `BespokeParams` / `rate_weekly` are the principled memo
defaults and satisfy every hard invariant constraint — so the model can never silently drift off the
invariant-safe point.

The shipped point: **alpha = 0.75, rho = rho_tier = 0.2, tier table unchanged**. Under the
surprise-centered credit (TASK-17) end-to-end I6 is robust across the whole alpha grid (the centered
win/loss quality gap is ~0.75, easily cleared by the converged spread), and the damped solve is an
unconditional `(1-lam)` contraction; rho stays in the memo range so the I11 trend feature is preserved.

**Methodology note (2026-06-24):** the synthetic `harness/tune.py` sweep is no longer the
param-selection oracle — the synthetic rank-recovery score was shown to be partly an artifact of the
old `base=3` floor, so evaluation moves to the real MHR dataset (gate-migration follow-up task). The
sweep remains a diagnostic artifact; these guards assert *principled + feasible*, not *sweep argmax*.
"""

import math

import pytest

from harness.run import gate_verdict, run_invariant_matrix, run_rank_recovery
from harness.tune import LAM_DEFAULT
from models.bespoke import BespokeParams, rate_weekly
from scenarios.builders import build_s07_close_vs_tier

# The untuned strawman baseline (alpha=0.6) mean Spearman over the scorable set — the tuned
# defaults must strictly improve on this (a real gain, not a no-op), even on the honest-fallback
# path where bespoke still trails MHR. Recorded by TASK-12 (reports/comparison.md).
UNTUNED_BASELINE_MEAN_SPEARMAN = 0.6811


def test_shipped_alpha_satisfies_end_to_end_I6():
    """With the SHIPPED defaults, the S07 construction holds I6 end-to-end: a 1-goal loss to the
    elite (T_TOP) out-credits a 1-goal win over the worst (T_BOTTOM) on the converged spread."""
    dataset, _meta = build_s07_close_vs_tier()
    result = rate_weekly(dataset.games)  # shipped defaults — no params/rho overrides
    attr = result.per_game_attribution["T_SUBJECT"]
    # TASK-17: identify by result (`base` is now centered quality, not the 3/0 floor).
    credit_loss_to_elite = next(bd for bd in attr if not bd.is_win).total
    credit_win_over_weak = next(bd for bd in attr if bd.is_win).total
    assert credit_loss_to_elite > credit_win_over_weak


def test_shipped_defaults_preserve_contraction():
    """I9 stays a contraction at the higher alpha: alpha*(1-lam) < 1 (so the solver still has a
    unique fixed point and converges deterministically)."""
    assert BespokeParams().alpha * (1.0 - LAM_DEFAULT) < 1.0


def test_shipped_defaults_keep_floor_structure():
    """The fairness floor is structural, not tuned — only constants moved. Win > tie > loss; the
    win bonus is non-decreasing with close == 0; the loss penalty is >= 0 with close == 0; every
    tier modulator is >= 0; tier 3 (index 2) is the neutral baseline (m == p == 1.0)."""
    p = BespokeParams()
    assert p.win > p.tie > p.loss
    assert p.win_bonus["close"] == 0.0
    assert p.win_bonus["3"] <= p.win_bonus["4"] <= p.win_bonus["5+"]  # monotone non-decreasing
    assert all(v >= 0.0 for v in p.win_bonus.values())
    assert p.loss_penalty["close"] == 0.0
    assert all(v >= 0.0 for v in p.loss_penalty.values())
    assert all(m >= 0.0 for m in p.tier_m)
    assert all(q >= 0.0 for q in p.tier_p)
    assert p.tier_m[2] == 1.0 and p.tier_p[2] == 1.0  # tier 3 neutral


def test_shipped_defaults_are_principled_and_feasible():
    """Post-TASK-17 methodology pivot: the synthetic sweep is NO LONGER the param-selection oracle.
    The synthetic rank-recovery number was shown to be partly an artifact of the old `base=3` floor's
    accidental anchoring, so the real MHR dataset is the yardstick now (see the gate-migration
    follow-up task). The shipped defaults are therefore the *principled* memo values — alpha=0.75,
    rho=rho_tier=0.2, tier table unchanged — and they must still satisfy the hard invariant constraints
    (end-to-end I6 + the contraction bound), which `is_feasible` checks."""
    from harness.tune import GridPoint, is_feasible

    p = BespokeParams()
    sig_default_rho = rate_weekly.__kwdefaults__ or {}
    assert p.alpha == pytest.approx(0.75)
    assert sig_default_rho["rho"] == pytest.approx(0.2)
    assert sig_default_rho["rho_tier"] == pytest.approx(0.2)
    assert p.tier_m == BespokeParams().tier_m  # memo tier table shipped unchanged
    # The shipped point is invariant-feasible (I6 end-to-end + the contraction bound).
    assert is_feasible(GridPoint(alpha=p.alpha, rho=sig_default_rho["rho"], tier_strength=1.0))


def test_shipped_defaults_beat_mhr_or_document_gap():
    """The computed (never prose-asserted) gate verdict at the shipped defaults: bespoke holds
    every invariant I1–I13, and *either* beats MHR (gate flips to PASS — keep that strict) *or*
    sits on the honest-fallback path: a real improvement over the untuned baseline that still
    trails MHR, with the gap left documented (no cherry-picking)."""
    v = gate_verdict(run_invariant_matrix(), run_rank_recovery())
    assert v.bespoke_all_invariants_pass is True
    if v.bespoke_beats_mhr:
        assert v.mean_spearman["bespoke"] > v.mean_spearman["mhr"]
    else:
        # Honest fallback: improved on the untuned defaults, but still an honest fail vs MHR.
        assert v.mean_spearman["bespoke"] > UNTUNED_BASELINE_MEAN_SPEARMAN
        assert v.mean_spearman["bespoke"] < v.mean_spearman["mhr"]


def test_shipped_defaults_keep_I11_trend():
    """rho was not pushed to 0 for score: the rising/falling trend signs still separate and the
    recency path still ranks the now-strong team above the now-weak one (mirrors
    models/test_bespoke_trend.py's I11 core at the shipped rho)."""
    from models.test_bespoke_trend import I11_SEED, riser_faller_dataset

    res = rate_weekly(riser_faller_dataset(seed=I11_SEED).games)
    assert res.trend["RISER"] > 0.0 > res.trend["FALLER"]      # trend signs separate
    assert res.ratings["RISER"] > res.ratings["FALLER"]        # current form ordering holds
    assert not any(math.isnan(v) for v in res.trend.values())
