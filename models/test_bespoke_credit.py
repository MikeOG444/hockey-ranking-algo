"""Bespoke credit-function invariants (brief §4 I1-I5, memo §1).

These test the per-game CREDIT function — the heart of the fairness floor. The full-model
invariants (I6-I13) come later, on rate(). Here we fix the opponent so the schedule term is
identical across results, isolating base + margin behavior.

Credit decomposition (memo §1, with both §1.3 corrections applied — the result-dependent schedule
weight removed and the own-rating self-reference dropped — so I1 holds structurally and the solve
converges): credit = base(result) + marginAdj(result, bucket, tier) + alpha*R_j.
"""


from models.bespoke import BespokeParams, per_game_credit

P = BespokeParams()  # strawman defaults (memo §9)


def credit(gf, ga, opp_rating=0.0, opp_tier=3):
    """Total per-game credit from the team's perspective (goals_for, goals_against)."""
    return per_game_credit(gf, ga, opp_rating=opp_rating, opp_tier=opp_tier, params=P).total


WIN_SCORES = [(1, 0), (3, 0), (4, 0), (5, 0), (8, 0)]
LOSS_SCORES = [(0, 1), (0, 3), (0, 4), (0, 5), (0, 8)]


def test_I1_win_beats_tie_beats_loss_same_opponent():
    """I1: holding opponent fixed, every win >= a tie >= every loss. No exceptions."""
    wins = [credit(gf, ga) for gf, ga in WIN_SCORES]
    tie = credit(2, 2)
    losses = [credit(gf, ga) for gf, ga in LOSS_SCORES]
    assert min(wins) >= tie >= max(losses)
    # And strictly: winning really is better than tying, which is better than losing.
    assert min(wins) > tie > max(losses)


def test_I2_win_credit_never_decreases_with_margin():
    """I2: for wins, more goals never reduce credit (monotone non-decreasing)."""
    margins = [credit(gf, 0) for gf in (1, 2, 3, 4, 5, 8)]
    assert margins == sorted(margins)


def test_margin_bonus_actually_rewards_a_bigger_win():
    """Behavioral: a 3-goal win earns strictly more than a close (1-goal) win — the bonus exists."""
    assert credit(3, 0) > credit(1, 0)


def test_I3_blowout_bonus_is_capped_and_diminishing():
    """I3: gains from running up the score diminish and cap (no runaway for blowouts)."""
    c_close, c3, c4, c5, c8 = (credit(g, 0) for g in (2, 3, 4, 5, 8))
    assert c8 == c5  # 8-0 and 5-0 share the 5+ bucket: the bonus is capped
    inc3, inc4, inc5 = c3 - c_close, c4 - c3, c5 - c4
    assert inc3 > inc4 > inc5 >= 0  # diminishing increments, never negative


def test_I4_close_loss_floored_and_never_above_a_tie():
    """I4: a close (1-2) loss is credited >= a deeper loss, and a loss never out-rates a tie."""
    assert credit(0, 2) >= credit(0, 3) >= credit(0, 5)
    assert credit(0, 2) < credit(2, 2)


def test_deeper_loss_is_penalized_more_than_a_close_loss():
    """Behavioral: a 4-goal loss is strictly worse than a close loss — the penalty exists,
    and the close bucket carries none of it."""
    assert credit(0, 4) < credit(0, 2)


def test_I5_tie_is_strictly_between_with_no_big_bump():
    """I5: a tie sits strictly between win and loss, and is closer to a loss than a win
    (ties earn no 'big bump')."""
    t, w, l = credit(2, 2), credit(1, 0), credit(0, 1)
    assert l < t < w
    assert (t - l) < (w - t)
