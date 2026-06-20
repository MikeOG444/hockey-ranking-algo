"""The bespoke rating model (memo §1, §9) — the primary candidate.

Per-game credit is an additive decomposition so the fairness floor is structural, not tuned:

    credit = base(result) + marginAdj(result, bucket, tier) + alpha * (opp_rating - own_rating)

- base(result) is a pure floor (W > T > L); nothing may override it -> guarantees I1.
- marginAdj modulates only the bonus/penalty: wins add a bounded, diminishing bonus; losses
  subtract a penalty that is zero for close (1-2) losses -> I2/I3/I4. Ties get nothing -> I5.
- the schedule term is result-INDEPENDENT (a refinement of memo §1.3, which had a result-
  dependent weight that could flip same-opponent ordering): identical for win/tie/loss vs the
  same opponent, so it never threatens I1, yet still rewards playing up / debits playing down (I6/I10).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CreditBreakdown:
    """The named drivers of one game's credit — this IS the per-game attribution (I12)."""

    base: float
    margin_adj: float
    schedule_term: float

    @property
    def total(self) -> float:
        return self.base + self.margin_adj + self.schedule_term


@dataclass(frozen=True)
class BespokeParams:
    """Strawman parameterization (memo §9), to be tuned in Stage A."""

    win: float = 3.0
    tie: float = 1.0
    loss: float = 0.0
    # Margin bonus for wins (diminishing, capped) and penalty for losses (close = 0, increasing).
    win_bonus: dict[str, float] = field(default_factory=lambda: {"close": 0.0, "3": 0.6, "4": 0.9, "5+": 1.0})
    loss_penalty: dict[str, float] = field(default_factory=lambda: {"close": 0.0, "3": 0.5, "4": 0.8, "5+": 1.0})
    alpha: float = 0.5  # strength of the schedule (play-up / play-down) signal


def margin_bucket(margin_abs: int) -> str:
    """Bucket an absolute goal margin (brief §1.3): 1-2 close, 3, 4, 5+."""
    if margin_abs <= 2:
        return "close"
    if margin_abs == 3:
        return "3"
    if margin_abs == 4:
        return "4"
    return "5+"


def _base(result: str, p: BespokeParams) -> float:
    return {"W": p.win, "T": p.tie, "L": p.loss}[result]


def per_game_credit(
    goals_for: int,
    goals_against: int,
    *,
    opp_rating: float,
    own_rating: float,
    opp_tier: int,
    params: BespokeParams,
) -> CreditBreakdown:
    if goals_for > goals_against:
        result = "W"
    elif goals_for < goals_against:
        result = "L"
    else:
        result = "T"

    base = _base(result, params)
    bucket = margin_bucket(abs(goals_for - goals_against))
    if result == "W":
        margin_adj = params.win_bonus[bucket]  # bounded, diminishing bonus on top of the win floor
    elif result == "L":
        margin_adj = -params.loss_penalty[bucket]  # penalty below the loss floor; zero for close
    else:
        margin_adj = 0.0  # a tie earns no margin adjustment (I5: no big bump)
    schedule_term = params.alpha * (opp_rating - own_rating)
    return CreditBreakdown(base=base, margin_adj=margin_adj, schedule_term=schedule_term)
