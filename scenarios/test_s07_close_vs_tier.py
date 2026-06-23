"""Scenario 7 — Close-vs-tier / I6 end-to-end (I6) ← MOST CRITICAL; see memo §11 Q1.

A league of 10+ teams: T_TOP is a genuine elite (high attack, low defense); T_BOTTOM is the
weakest field team; the rest fill the middle. After ≥8 weeks of round-robin play the solver
converges to a spread where T_TOP's rating is substantially above mean and T_BOTTOM's is below.

T_SUBJECT plays two seeded games:
  (a) a 1-goal LOSS to T_TOP — hard game against elite
  (b) a 1-goal WIN over T_BOTTOM — soft game against the weakest team

I6: credit(a) must exceed credit(b). The schedule_term for (a) is α * R_TOP > 0 (positive, large);
the schedule_term for (b) is α * R_BOTTOM < 0 (negative). Combined with base(L=0) vs base(W=3),
I6 holds only when α*(R_TOP - R_BOTTOM) > W - L = 3, which requires the solver's converged
spread to be large enough.

MEMO §11 Q1 CAVEAT: If the converged spread is too small (e.g. because the league is evenly
matched), α=0.6 may not satisfy I6 end-to-end. This test must FAIL LOUDLY — print attribution
values and the actual gap — and NOT silently weaken the assertion. Document the finding.

A secondary sweep at α=0.8 tests whether I6 is achievable with a higher α.
"""

import pytest

from models.bespoke import BespokeParams, rate_weekly
from scenarios.builders import build_s07_close_vs_tier


def test_s07_i6_credit_loss_elite_beats_win_weak():
    """I6 end-to-end: a 1-goal loss to T_TOP must earn more credit than a 1-goal win over T_BOTTOM.

    If this fails at α=0.6, the test FAILS LOUDLY with diagnostic output. Do not weaken.
    See memo §11 Q1 for the derivation.
    """
    dataset, meta = build_s07_close_vs_tier()
    result = rate_weekly(dataset.games)

    # Verify the tier gap actually materialized: T_TOP must rate above mean, T_BOTTOM below.
    # Without this, the I6 assertion could silently test against a flat-field where the
    # converged gap is too small to be meaningful (spec-keeper finding, TASK-11).
    r_top = result.ratings["T_TOP"]
    r_bottom = result.ratings["T_BOTTOM"]
    assert r_top > 0, f"T_TOP must be above-average after 8 weeks; got {r_top:.4f}"
    assert r_bottom < 0, f"T_BOTTOM must be below-average after 8 weeks; got {r_bottom:.4f}"

    # Pull T_SUBJECT's per-game attribution for games (a) and (b).
    # (a) = the 1-goal loss to T_TOP: base == 0 (loss), schedule_term should be large positive.
    # (b) = the 1-goal win over T_BOTTOM: base == 3 (win), schedule_term should be negative.
    subject_attr = result.per_game_attribution.get("T_SUBJECT", [])
    assert subject_attr, "T_SUBJECT has no per-game attribution"

    game_vs_top = None
    game_vs_bottom = None

    # The attribution entries are ordered canonically; find by base value.
    # game_vs_top: schedule_term ≈ α * r_top (positive, large)
    # game_vs_bottom: schedule_term ≈ α * r_bottom (negative)
    for bd in subject_attr:
        if bd.base == 0.0:  # a loss — must be vs T_TOP (T_SUBJECT lost to T_TOP)
            game_vs_top = bd
        elif bd.base == 3.0:  # a win — must be vs T_BOTTOM
            game_vs_bottom = bd

    assert game_vs_top is not None, (
        f"Could not identify the game vs T_TOP in T_SUBJECT's attribution. "
        f"Attribution entries: {subject_attr}"
    )
    assert game_vs_bottom is not None, (
        f"Could not identify the game vs T_BOTTOM in T_SUBJECT's attribution. "
        f"Attribution entries: {subject_attr}"
    )

    credit_a = game_vs_top.total     # credit for loss to elite
    credit_b = game_vs_bottom.total  # credit for win over weak

    alpha = BespokeParams().alpha
    actual_gap = r_top - r_bottom

    if credit_a <= credit_b:
        # FAIL LOUDLY as required by memo §11 Q1 — print diagnostic, then raise.
        print(
            f"\n[SCENARIO 7 I6 FAILURE] α={alpha:.2f}, converged gap R_TOP-R_BOTTOM={actual_gap:.4f}\n"
            f"  credit(loss to T_TOP)  = {credit_a:.4f}  "
            f"(base={game_vs_top.base:.1f}, margin={game_vs_top.margin_adj:.4f}, sched={game_vs_top.schedule_term:.4f})\n"
            f"  credit(win over T_BOTTOM) = {credit_b:.4f}  "
            f"(base={game_vs_bottom.base:.1f}, margin={game_vs_bottom.margin_adj:.4f}, sched={game_vs_bottom.schedule_term:.4f})\n"
            f"  I6 requires α*gap > W-L: {alpha}*{actual_gap:.4f}={alpha*actual_gap:.4f} vs {BespokeParams().win - BespokeParams().loss}\n"
            f"  FINDING: The solver's converged spread is insufficient for I6 at α={alpha:.2f}. "
            f"Re-derive α against the reachable gap ({actual_gap:.4f}) as per memo §11 Q1."
        )
        pytest.fail(
            f"I6 FAILED at α={alpha:.2f}: credit(loss→elite)={credit_a:.4f} ≤ credit(win→weak)={credit_b:.4f}. "
            f"Converged gap={actual_gap:.4f}. See printed diagnostic for α re-derivation target."
        )

    assert credit_a > credit_b, "I6 holds: loss to elite rates better than win over weak"


def test_s07_i6_alpha08_sweep():
    """Secondary α sweep: at α=0.8 the same direction must hold (I6 achievable even if α=0.6 is tight)."""
    dataset, meta = build_s07_close_vs_tier()
    params_08 = BespokeParams(alpha=0.8)
    result = rate_weekly(dataset.games, params_08)

    subject_attr = result.per_game_attribution.get("T_SUBJECT", [])
    assert subject_attr

    game_vs_top = next((bd for bd in subject_attr if bd.base == 0.0), None)
    game_vs_bottom = next((bd for bd in subject_attr if bd.base == 3.0), None)

    assert game_vs_top is not None, "Cannot find loss-to-T_TOP game in attribution at α=0.8"
    assert game_vs_bottom is not None, "Cannot find win-over-T_BOTTOM game in attribution at α=0.8"

    credit_a = game_vs_top.total
    credit_b = game_vs_bottom.total
    assert credit_a > credit_b, (
        f"I6 failed even at α=0.8: credit_a={credit_a:.4f} ≤ credit_b={credit_b:.4f}. "
        f"Gap R_TOP-R_BOTTOM={result.ratings['T_TOP']-result.ratings['T_BOTTOM']:.4f}"
    )
