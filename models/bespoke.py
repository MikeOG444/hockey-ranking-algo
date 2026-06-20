"""The bespoke rating model (memo §1, §9) — the primary candidate.

Per-game credit is an additive decomposition so the fairness floor is structural, not tuned:

    credit = base(result) + marginAdj(result, bucket, tier) + alpha * opp_rating

- base(result) is a pure floor (W > T > L); nothing may override it -> guarantees I1.
- marginAdj modulates only the bonus/penalty: wins add a bounded, diminishing bonus; losses
  subtract a penalty that is zero for close (1-2) losses -> I2/I3/I4. Ties get nothing -> I5.
- the schedule term is result-INDEPENDENT (a refinement of memo §1.3, which had a result-
  dependent weight that could flip same-opponent ordering): identical for win/tie/loss vs the
  same opponent, so it never threatens I1, yet still rewards playing up / debits playing down (I6/I10).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from core.game import GameRow


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
    # Strength of the schedule (play-up / play-down) signal. Derived, not guessed (memo Q1): I6
    # pins it just above (W - L) / (elite - field gap). For the canonical +4 / -2 example that gap
    # is 6, so alpha=0.5 ties (0.5*6 == W-L == 3) and fails I6; alpha=0.6 clears it with margin
    # (0.6*6 = 3.6 > 3). Still a contraction for I9 since alpha*(1-lam) = 0.6*0.95 = 0.57 < 1.
    alpha: float = 0.6


def margin_bucket(margin_abs: int) -> str:
    """Bucket an absolute goal margin (brief §1.3): 1-2 close, 3, 4, 5+."""
    if margin_abs <= 2:
        return "close"
    if margin_abs == 3:
        return "3"
    if margin_abs == 4:
        return "4"
    return "5+"


def classify(goals_for: int, goals_against: int) -> str:
    """Infer W / L / T from a team's goals_for vs goals_against."""
    if goals_for > goals_against:
        return "W"
    if goals_for < goals_against:
        return "L"
    return "T"


def base_and_margin(goals_for: int, goals_against: int, params: BespokeParams) -> tuple[float, float]:
    """The opponent-independent part of credit: (base floor, margin adjustment).

    This is the piece that holds invariants I1-I5; it does not depend on any rating, so in the
    schedule solve it is a constant per game (only the schedule term re-rates each iteration).
    """
    result = classify(goals_for, goals_against)
    base = {"W": params.win, "T": params.tie, "L": params.loss}[result]
    bucket = margin_bucket(abs(goals_for - goals_against))
    if result == "W":
        margin_adj = params.win_bonus[bucket]  # bounded, diminishing bonus on top of the win floor
    elif result == "L":
        margin_adj = -params.loss_penalty[bucket]  # penalty below the loss floor; zero for close
    else:
        margin_adj = 0.0  # a tie earns no margin adjustment (I5: no big bump)
    return base, margin_adj


def per_game_credit(
    goals_for: int,
    goals_against: int,
    *,
    opp_rating: float,
    opp_tier: int,
    params: BespokeParams,
) -> CreditBreakdown:
    """One game's credit from a team's perspective.

    The schedule term is the opponent's CURRENT rating scaled by alpha (strength of schedule,
    floating per I10) — result-independent, so it never disturbs same-opponent ordering (I1).
    """
    base, margin_adj = base_and_margin(goals_for, goals_against, params)
    schedule_term = params.alpha * opp_rating
    return CreditBreakdown(base=base, margin_adj=margin_adj, schedule_term=schedule_term)


# --- the schedule solve (memo §2-§3) ---------------------------------------


@dataclass(frozen=True)
class RateResult:
    """The common model output (memo §8). tiers/trend are filled in as the later invariants
    (I11/I13) bring them online.

    `per_game_attribution` maps each team to a list of CreditBreakdown — one per game it played,
    built from the opponents' CONVERGED ratings (I12). `center_offset` is the single scalar
    subtracted from every team's pre-centered value to gauge-fix the ratings to mean 0; storing it
    makes the reconciliation `rating_i == (1 - lam) * mean_g(breakdown.total) - center_offset`
    exact rather than merely approximate (memo §7)."""

    ratings: dict[str, float]
    tiers: dict[str, int]
    per_game_attribution: dict[str, list[CreditBreakdown]]
    trend: dict[str, float]
    center_offset: float = 0.0


def _teams_of(games: Iterable[GameRow]) -> list[str]:
    seen: set[str] = set()
    for g in games:
        seen.add(g.team)
        seen.add(g.opponent)
    return sorted(seen)  # deterministic team order (I8)


def rate(
    games: Iterable[GameRow],
    params: BespokeParams | None = None,
    *,
    lam: float = 0.05,
    tol: float = 1e-12,
    max_iter: int = 1000,
    init: Mapping[str, float] | None = None,
) -> RateResult:
    """Solve season ratings as the fixed point of a damped batch iteration:

        r_i <- (1 - lam) * mean_g[ const_g + alpha * r_opp ]   (+ lam * mean, which is 0 after centering)

    `const_g` (base + margin) is fixed per game; only the schedule term re-rates each pass. With lam>0
    and alpha<1 the map is a contraction -> a unique fixed point reached from any start (I8/I9). Ratings
    are re-centered to mean 0 each pass (they are relative), which also pins the gauge on disconnected
    graphs together with the pull toward the mean.
    """
    params = params or BespokeParams()
    games = list(games)
    teams = _teams_of(games)

    # Per-team perspective entries: (base, margin, opponent_id). Both sides of every game. We keep
    # base and margin separate (not pre-summed) so the same entries drive both the solve and the
    # per-game attribution (I12) without recomputing the floor.
    entries: dict[str, list[tuple[float, float, str]]] = {t: [] for t in teams}
    for g in games:
        b, m = base_and_margin(g.goals_team, g.goals_opponent, params)
        entries[g.team].append((b, m, g.opponent))
        b, m = base_and_margin(g.goals_opponent, g.goals_team, params)
        entries[g.opponent].append((b, m, g.team))
    # Canonical summation order so the result is byte-identical regardless of input order (I8).
    for t in teams:
        entries[t].sort(key=lambda e: (e[2], e[0], e[1]))

    r = {t: 0.0 for t in teams}
    if init is not None:
        r = {t: float(init.get(t, 0.0)) for t in teams}

    for _ in range(max_iter):
        new = {}
        for t in teams:
            ent = entries[t]
            if not ent:
                new[t] = 0.0
                continue
            total = 0.0
            for base, margin, opp in ent:
                total += base + margin + params.alpha * r[opp]
            new[t] = (1.0 - lam) * (total / len(ent))
        mean = sum(new.values()) / len(new)
        for t in teams:
            new[t] -= mean  # re-center (gauge fix + regularization target)
        delta = max(abs(new[t] - r[t]) for t in teams)
        r = new
        if delta < tol:
            break

    # Attribution pass (I12): with the ratings converged, replay each team's games once more to
    # record the three named drivers per game, using opponents' FINAL ratings for the schedule term.
    # The same algebra as a solve step (pre-center value = (1-lam)*mean of breakdown totals) then a
    # single shared centering offset; we rebuild ratings from these so the reconciliation
    # `rating == (1-lam)*mean(breakdown.total) - center_offset` is exact, not merely within tolerance.
    # The breakdown already splits result-driven credit (base + margin_adj) from schedule-driven
    # credit (schedule_term); the weekly result-vs-schedule *delta* split (memo §7) waits on the
    # per-week solve that arrives with tiers/trend (TASK-05/06).
    attribution: dict[str, list[CreditBreakdown]] = {}
    pre: dict[str, float] = {}
    for t in teams:
        ent = entries[t]
        breakdowns = [
            CreditBreakdown(base=base, margin_adj=margin, schedule_term=params.alpha * r[opp])
            for base, margin, opp in ent
        ]
        attribution[t] = breakdowns
        pre[t] = (1.0 - lam) * (sum(bd.total for bd in breakdowns) / len(ent)) if ent else 0.0
    center_offset = sum(pre.values()) / len(pre)
    ratings = {t: pre[t] - center_offset for t in teams}

    return RateResult(
        ratings=ratings,
        tiers={},
        per_game_attribution=attribution,
        trend={},
        center_offset=center_offset,
    )
