"""The bespoke rating model (memo §1, §3.1, §9) — the primary candidate.

Per-game credit is **surprise-centered** (TASK-17, memo §3.1): it anchors on the team's own rating and
adds the surprise of the result against the opponent —

    raw    = base(result) + marginAdj(result, bucket, tier) + alpha*opp_rating + (1-alpha)*own_rating
    credit = max(raw, own_rating)  for a WIN  (the win-floor: a win never lowers you);  raw otherwise

- ``base(result)`` is now the CENTERED result quality (win=0.5, tie=0.0, loss=-0.25 — *not* the old
  3/1/0 floor); the fairness floor is structural via the **win-floor** (a win is floored at your own
  rating), which realizes "a win is not a loss" while making an *expected* win ~neutral.
- ``marginAdj`` modulates only the bonus/penalty: wins add a bounded, diminishing bonus; losses
  subtract a penalty that is zero for close (1-2) losses -> I2/I3/I4. Ties get nothing -> I5.
- ``schedule_term = alpha*opp_rating`` (strength of schedule) and ``self_term = (1-alpha)*own_rating``
  (the recentering anchor) are BOTH result-INDEPENDENT: identical for win/tie/loss vs the same
  opponent, so they never threaten same-opponent ordering (I1), yet still reward playing up / debit
  playing down (I6/I10). The damped solve is an unconditional ``(1-lambda)`` contraction for any
  alpha in [0,1) because the self-weight ``(1-alpha)`` and opponent-weight ``alpha`` form a convex
  split (memo §3.1) — this is the SAFE convex form of the self-reference, distinct from the divergent
  ``-r_i`` form rejected in memo §1.3 (coefficient +(1-alpha), not -alpha).
"""

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from core.game import GameRow
from models.tiers import TierWindow, detect_tiers


@dataclass(frozen=True)
class CreditBreakdown:
    """The named drivers of one game's credit — this IS the per-game attribution (I12).

    Credit is *surprise-centered* (TASK-17): a game's credit is the team's OWN current rating plus the
    surprise of the result against this opponent. Concretely

        raw   = base + margin_adj + schedule_term + self_term
        total = max(raw, own_rating)  for a WIN  (the win-floor: a win never lowers you);  raw otherwise

    where ``schedule_term = alpha*r_opp`` (who you played) and ``self_term = (1-alpha)*own_rating`` (the
    recentering anchor). Equivalently ``total = own_rating + [clamp_{>=0} for wins] (base + margin_adj +
    alpha*(r_opp - own_rating))`` — beating a much weaker team yields surprise <= 0, so the win-floor
    pins the credit to your own rating (neutral: a cheap win shows nothing but never costs you); a close
    loss to a much stronger team yields a small positive surprise (an honorable near-upset nudges you up).
    """

    base: float
    margin_adj: float
    schedule_term: float
    # The recentering anchor (1-alpha)*own_rating — the self-reference that makes credit relative to the
    # team's own strength (memo §3.1, re-derived in TASK-17). Default 0.0 keeps legacy construction sites
    # (own_rating absent) byte-identical to the pre-surprise behaviour.
    self_term: float = 0.0
    # The team's own current rating — the win-floor level and the anchor (own_rating == self_term/(1-alpha)).
    own_rating: float = 0.0
    # Whether this game is a win — only wins are floored at own_rating (ties/losses carry full downside, I1).
    is_win: bool = False
    # The game's recency weight w_g = exp(-rho*(now - week_g)) ∈ (0, 1] (memo §2, §7-§8). It scales
    # the *whole* credit inside the per-game weighted mean — it is NOT part of `total` (which is the
    # raw per-game credit). Defaults to 1.0 so the flat (rho=0) path and every existing construction
    # site are unchanged.
    w: float = 1.0

    @property
    def raw(self) -> float:
        """The unclamped surprise-centered credit (sum of the four named drivers)."""
        return self.base + self.margin_adj + self.schedule_term + self.self_term

    @property
    def total(self) -> float:
        """Per-game credit. Wins are floored at ``own_rating`` (a win never lowers you); a tie/loss is the
        raw value, so it can fall below your rating when you under-perform a weaker opponent (I1 intact:
        vs the SAME opponent the win-floor only ever raises a win above the tie/loss raw value)."""
        return max(self.raw, self.own_rating) if self.is_win else self.raw


@dataclass(frozen=True)
class BespokeParams:
    """Stage-A-tuned parameterization (memo §9, tuned in TASK-13).

    The structural fields (W/T/L floor, the margin-bucket bonus/penalty tables, the tier modulators)
    are the memo strawman unchanged — they are what make I1–I5/I7 hold by construction, so they are
    *not* a tuning surface. The single value Stage A moved is ``alpha`` (0.6 → 0.75): re-derived
    against the solver's reachable converged spread so end-to-end I6 holds, and the argmax of the
    `harness/tune.py` rank-recovery sweep. ``rho``/``rho_tier`` (on `rate_weekly`) stay at the memo
    0.2 — also the sweep's pick, and kept off 0 so the I11 trend feature survives.
    """

    # Surprise-centered result quality (TASK-17). These are NO LONGER an absolute floor (the old
    # 3/1/0) — they are *centered* values measuring how good a result is, so the expectation term
    # alpha*(r_opp - own) can cancel them. Centering is what makes an expected win neutral: beating a
    # team ~0.67 below you (win=0.5, alpha=0.75 ⇒ 0.5/0.75) yields surprise <= 0, and the win-floor pins
    # the credit to your own rating (a cheap win shows nothing). tie = 0 is the neutral baseline; a close
    # loss starts at -0.25 (honorable — small) and deepens with the margin penalty. The ordering
    # win > tie > loss is preserved (I1-I5 are relational, not tied to the old magnitudes).
    win: float = 0.5
    tie: float = 0.0
    loss: float = -0.25
    # Margin bonus for wins (diminishing, capped) and penalty for losses (close = 0, increasing).
    win_bonus: dict[str, float] = field(default_factory=lambda: {"close": 0.0, "3": 0.6, "4": 0.9, "5+": 1.0})
    loss_penalty: dict[str, float] = field(default_factory=lambda: {"close": 0.0, "3": 0.5, "4": 0.8, "5+": 1.0})
    # Strength of the schedule (play-up / play-down) signal. DERIVED against the solver's
    # *reachable* converged spread, not a hand-picked example (memo Q1; tuned in TASK-13). End-to-end
    # I6 needs alpha*(R_TOP - R_BOTTOM) > W - L = 3; on the Scenario-7 league the centered spread
    # converges to R_TOP - R_BOTTOM ≈ 4.38, so the threshold is alpha ≈ 3/4.38 ≈ 0.69 — the
    # hand-picked +4/-2 (gap 6) alpha=0.6 is *below* it and inverts I6 end-to-end (the S07 red).
    # alpha=0.75 clears I6 with margin (credit(loss→elite) 1.67 > credit(win→weak) 1.42 on the
    # converged ratings) AND is the Stage-A sweep's argmax for mean rank recovery over the scorable
    # §7 scenarios (harness/tune.py). Still a contraction for I9: alpha*(1-lam) = 0.75*0.95 = 0.71
    # < 1. Confirming test: scenarios/test_s07_close_vs_tier.py (green at this shipped default).
    alpha: float = 0.75
    # Tier modulators (memo §1.2, §4): scale the *margin adjustment* by the OPPONENT's frozen tier
    # — never `base`. Indexed by (tier - 1); tier 3 is the neutral baseline (m = p = 1.0) so the
    # I1-I5 credit tests, which fix opp_tier=3, are untouched. Beating up a tier (lower index)
    # raises the win bonus and softens the loss penalty (p < 1); playing down does the reverse.
    # These stay orthogonal to `scheduleTerm` (Q3): strength-of-schedule lives there, "how margin
    # reads by tier" lives here — we never pay for opponent strength twice.
    tier_m: tuple[float, ...] = (1.3, 1.15, 1.0, 0.85)  # win-bonus scale; tier 3 = 1.0 (neutral)
    tier_p: tuple[float, ...] = (0.7, 0.85, 1.0, 1.15)  # loss-penalty scale; tier 3 = 1.0 (neutral)
    tier_default_m: float = 0.7  # beyond the table (the deep field): smallest bonus for beating it
    tier_default_p: float = 1.3  # beyond the table: harshest penalty for losing to it

    def m_for(self, tier_float: float) -> float:
        """Win-bonus modulator for an opponent at (possibly fractional) ``tier_float``.

        Round to the nearest integer tier, clamp at the top (tier 1), and read the table; tiers
        beyond the table fall back to ``tier_default_m``. Always >= 0 so the bonus sign can't flip.
        """
        t = max(1, round(tier_float))
        return self.tier_m[t - 1] if t <= len(self.tier_m) else self.tier_default_m

    def p_for(self, tier_float: float) -> float:
        """Loss-penalty modulator (same rounding/clamp rules as :meth:`m_for`). Always >= 0, so
        scaling a (negative) loss penalty never flips it positive → I4 holds structurally."""
        t = max(1, round(tier_float))
        return self.tier_p[t - 1] if t <= len(self.tier_p) else self.tier_default_p


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
    """The opponent- and self-independent part of credit: (centered result quality, margin adjustment).

    ``base`` is the CENTERED result quality (win/tie/loss = 0.5/0.0/-0.25 by default — TASK-17, not the
    old 3/1/0 floor). This is the piece that holds invariants I1-I5; it depends on no rating, so in the
    schedule solve it is a constant per game (only the schedule term and the self-anchor re-rate each
    iteration). The fairness floor now lives in the per_game_credit win-floor (max(raw, own_rating)),
    not in the magnitude of ``base``.
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


def scaled_margin(
    raw_margin: float, result: str, opp_tier: float | None, params: BespokeParams
) -> float:
    """Apply the opponent's tier modulator to a raw (signed) margin adjustment (memo §1.2).

    `raw_margin` is the opponent-independent adjustment from `base_and_margin` (>= 0 for a win,
    <= 0 for a loss, 0 for a tie). We scale the *win bonus* by `m(tier)` and the *loss penalty* by
    `p(tier)`; both modulators are >= 0, so the sign never flips (I4) and `base` is never involved
    (I1/I7). `opp_tier is None` is the cold-start signal (memo §5): credit tier-agnostically with
    m = p = 1, i.e. leave the raw margin alone.
    """
    if opp_tier is None:
        return raw_margin
    if result == "W":
        return raw_margin * params.m_for(opp_tier)
    if result == "L":
        return raw_margin * params.p_for(opp_tier)
    return 0.0  # tie: no adjustment (I5)


def per_game_credit(
    goals_for: int,
    goals_against: int,
    *,
    opp_rating: float,
    opp_tier: int,
    params: BespokeParams,
    own_rating: float = 0.0,
) -> CreditBreakdown:
    """One game's surprise-centered credit from a team's perspective (TASK-17).

    Credit anchors on the team's OWN rating and adds the surprise of the result against this opponent:
    ``total = max(raw, own_rating)`` for a win, ``raw`` otherwise, with
    ``raw = base + margin_adj + schedule_term + self_term``. The schedule term ``alpha*r_opp`` (who you
    played) and the self term ``(1-alpha)*own_rating`` (the recentering anchor) are both result-
    INDEPENDENT, so they never disturb same-opponent ordering (I1); the win-floor only ever *raises* a
    win, never a tie/loss, so a win still out-credits a tie/loss vs the SAME opponent. The margin
    adjustment is scaled by the opponent's tier modulator (memo §1.2), always on the adjustment and
    never on `base`. ``own_rating`` defaults to 0 so the isolated credit-function invariant tests
    (which fix the opponent and the self anchor at 0) read the centered quality directly."""
    base, raw_margin = base_and_margin(goals_for, goals_against, params)
    result = classify(goals_for, goals_against)
    margin_adj = scaled_margin(raw_margin, result, opp_tier, params)
    schedule_term = params.alpha * opp_rating
    self_term = (1.0 - params.alpha) * own_rating
    return CreditBreakdown(
        base=base,
        margin_adj=margin_adj,
        schedule_term=schedule_term,
        self_term=self_term,
        own_rating=own_rating,
        is_win=(result == "W"),
    )


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


# A per-team perspective entry: (base, raw_margin, opponent_id, result, week). Both base and the
# *raw* (un-modulated) margin are kept separate so the same entries drive the solve and the
# attribution (I12) without recomputing the floor; `result` lets a tier-aware caller scale the margin
# by the opponent's frozen tier without re-deriving W/L/T; `week` drives the recency weight (memo §2).
_Entry = tuple[float, float, str, str, int]
# Maps (raw_margin, result, opponent_id) -> the effective margin to use this solve. `rate` passes
# the identity (no tiers); `rate_weekly` passes one that applies the frozen-tier modulator.
_MarginFn = Callable[[float, str, str], float]


def _build_entries(games: list[GameRow], params: BespokeParams) -> tuple[list[str], dict[str, list[_Entry]]]:
    """Both sides of every game, grouped per team, in a canonical order (I8 determinism)."""
    teams = _teams_of(games)
    entries: dict[str, list[_Entry]] = {t: [] for t in teams}
    for g in games:
        b, m = base_and_margin(g.goals_team, g.goals_opponent, params)
        entries[g.team].append((b, m, g.opponent, classify(g.goals_team, g.goals_opponent), g.week))
        b, m = base_and_margin(g.goals_opponent, g.goals_team, params)
        entries[g.opponent].append((b, m, g.team, classify(g.goals_opponent, g.goals_team), g.week))
    # Canonical summation order so the result is byte-identical regardless of input order (I8);
    # week is part of the key so two games vs the same opponent never sort ambiguously.
    for t in teams:
        entries[t].sort(key=lambda e: (e[2], e[0], e[1], e[4]))
    return teams, entries


def _now_of(entries: dict[str, list[_Entry]]) -> int:
    """The latest week present in a solve's entry set — the reference point for recency decay
    (memo §2): w_g = exp(-rho*(now - week_g)). 0 when there are no games."""
    weeks = [e[4] for ent in entries.values() for e in ent]
    return max(weeks) if weeks else 0


def _recency_weight(week: int, now: int, rho: float) -> float:
    """w_g = exp(-rho*(now - week)) ∈ (0, 1]. A pure function of week (I8: no RNG). rho=0 ⇒ 1.0."""
    return math.exp(-rho * (now - week))


def _solve(
    teams: list[str],
    entries: dict[str, list[_Entry]],
    params: BespokeParams,
    margin_fn: _MarginFn,
    *,
    rho: float,
    lam: float,
    tol: float,
    max_iter: int,
    init: Mapping[str, float] | None,
) -> dict[str, float]:
    """Damped batch fixed-point iteration with recency-weighted aggregation (memo §2):

        r_i <- (1 - lam) * [ Σ_g w_g*(base_g + margin_fn(...) + alpha*r_opp) / Σ_g w_g ]  (re-center)

    where w_g = exp(-rho*(now - week_g)) and now is the latest week in `entries`. Per game
    `base + margin_fn(...)` is constant; only the schedule term re-rates each pass. The recency
    weights are fixed non-negative per-game scalars applied inside the average, so they never enter
    the alpha coupling: with lam>0 and alpha<1 the map is still a contraction → a unique fixed point
    from any start (memo §3 unchanged; I8/I9). rho=0 ⇒ all w_g=1 ⇒ the plain uniform mean.
    """
    now = _now_of(entries)
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
            wsum = 0.0
            own = r[t]  # the team's CURRENT rating — the surprise anchor and win-floor level (TASK-17)
            for base, raw_margin, opp, result, week in ent:
                w = _recency_weight(week, now, rho)
                # Surprise-centered credit: anchor on own rating, add who-you-played + result surprise.
                raw = base + margin_fn(raw_margin, result, opp) + params.alpha * r[opp] + (1.0 - params.alpha) * own
                credit = max(raw, own) if result == "W" else raw  # win-floor: a win never lowers you (I1)
                total += w * credit
                wsum += w
            new[t] = (1.0 - lam) * (total / wsum)
        mean = sum(new.values()) / len(new)
        for t in teams:
            new[t] -= mean  # re-center (gauge fix + regularization target)
        delta = max(abs(new[t] - r[t]) for t in teams)
        r = new
        if delta < tol:
            break
    return r


def _attribute(
    teams: list[str],
    entries: dict[str, list[_Entry]],
    r: dict[str, float],
    params: BespokeParams,
    margin_fn: _MarginFn,
    lam: float,
    rho: float,
) -> tuple[dict[str, list[CreditBreakdown]], dict[str, float], float]:
    """Replay each team's games against the converged ratings to record the four named drivers
    (base, margin_adj, schedule_term, w — I12 + memo §8), then rebuild ratings from them so
    `rating == (1-lam)*(Σ w_g*total_g / Σ w_g) - center_offset` is exact, not merely within tolerance
    (memo §7, weight-aware). Uses opponents' FINAL ratings → I10."""
    now = _now_of(entries)
    attribution: dict[str, list[CreditBreakdown]] = {}
    pre: dict[str, float] = {}
    for t in teams:
        ent = entries[t]
        own = r[t]  # converged own rating — the surprise anchor + win-floor level (I12 attribution)
        breakdowns = [
            CreditBreakdown(
                base=base,
                margin_adj=margin_fn(raw_margin, result, opp),
                schedule_term=params.alpha * r[opp],
                self_term=(1.0 - params.alpha) * own,
                own_rating=own,
                is_win=(result == "W"),
                w=_recency_weight(week, now, rho),
            )
            for base, raw_margin, opp, result, week in ent
        ]
        attribution[t] = breakdowns
        wsum = sum(bd.w for bd in breakdowns)
        pre[t] = (1.0 - lam) * (sum(bd.w * bd.total for bd in breakdowns) / wsum) if ent else 0.0
    center_offset = sum(pre.values()) / len(pre)
    ratings = {t: pre[t] - center_offset for t in teams}
    return attribution, ratings, center_offset


def rate(
    games: Iterable[GameRow],
    params: BespokeParams | None = None,
    *,
    lam: float = 0.05,
    tol: float = 1e-12,
    max_iter: int = 1000,
    init: Mapping[str, float] | None = None,
) -> RateResult:
    """Flat, single-pass season solve with NO tier modulation (the tier-agnostic baseline).

    Solves the damped fixed point over all games at once. `tiers`/`trend` are left empty here;
    the tier-aware per-week solve is `rate_weekly`. Deterministic and order-independent (I8/I9).
    """
    params = params or BespokeParams()
    teams, entries = _build_entries(list(games), params)
    identity_margin: _MarginFn = lambda raw, result, opp: raw  # noqa: E731 — no tiers in flat rate
    # rho=0 ⇒ every recency weight is exactly 1.0, so the weighted mean collapses to the uniform mean
    # and this flat baseline is byte-identical to its pre-recency behaviour (I8/I9 tests stay green).
    r = _solve(teams, entries, params, identity_margin, rho=0.0, lam=lam, tol=tol, max_iter=max_iter, init=init)
    attribution, ratings, center_offset = _attribute(teams, entries, r, params, identity_margin, lam, rho=0.0)
    return RateResult(
        ratings=ratings,
        tiers={},
        per_game_attribution=attribution,
        trend={},
        center_offset=center_offset,
    )


def _ols_slope(points: list[tuple[int, float]]) -> float:
    """Ordinary-least-squares slope of y over x for a fixed (week, rating) series — the trend signal
    (memo §6). Closed form, no RNG (I8). Chosen over a two-point `r_recent - r_baseline` because it
    uses the whole window and so is less jumpy; both are sanctioned by §6. A series with < 2 points or
    zero week-variance (a single recorded week) has no defined slope → 0.0, by convention."""
    n = len(points)
    if n < 2:
        return 0.0
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    sxx = sum((x - mean_x) ** 2 for x, _ in points)
    if sxx == 0.0:
        return 0.0
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in points)
    return sxy / sxx


def rate_weekly(
    games: Iterable[GameRow],
    params: BespokeParams | None = None,
    *,
    tier_count: int | str = "auto",
    gap_c: float = 2.0,
    max_window: int = 4,
    rho_tier: float = 0.2,
    rho: float = 0.2,
    trend_window: int = 4,
    lam: float = 0.05,
    tol: float = 1e-12,
    max_iter: int = 1000,
) -> RateResult:
    """Tier-aware season solve (memo §5): walk weeks in order with a frozen-tier window.

    For each week W (ascending — I8):
      a. read every team's FROZEN tier from the ≤``max_window`` prior finalized weeks (recency-
         weighted, ``rho_tier``); a team with no usable history reads ``None`` → tier-agnostic
         (m = p = 1) credit for that game;
      b. run the damped fixed-point solve on ALL games through week W, applying the tier modulator
         to each game's margin via the opponent's frozen tier;
      c. derive week W's tiers from the converged ratings (natural gaps, §4) and push them into the
         window for later weeks to read.

    **Cold start (memo §5):** the window only modulates once **>= 2 finalized weeks** exist, so
    weeks 1-2 run tier-agnostic (a single provisional pass); the frozen window activates from week 3.
    A one-week tier blip in an opponent is averaged across the window, so the credit it confers this
    week moves only a bounded, damped amount → I13. With recency weighting on (``rho`` > 0) an old
    blip game is further down-weighted as weeks advance, so its inflation *decays* rather than
    persisting as a permanent step. The final week's solve produces the returned ratings/tiers/
    attribution.

    **Trend (memo §6, I11).** Each team's converged rating is captured per finalized week; after the
    walk ``trend[t]`` is the OLS slope of that team's rating series over the last ``trend_window``
    weeks. A rising team shows a positive slope, a falling team a negative one, even when their
    season-average strength is equal — and recency weighting (below) makes the point-in-time ratings
    track current form. Trend is an *output only*; it never re-enters the solve (observed-vs-derived
    wall, brief §5).

    **`rho` (game recency, = 0.2, ~3.5-week half-life)** weights each game in the per-week aggregate
    by ``exp(-rho*(W - week_g))`` (memo §2, §9: `ρ` half-life 3-4 weeks; `ρ = ρ_tier`). At ρ=0 the
    solve is the uniform mean (the flat baseline). A ~1-week half-life would let the latest game swamp
    everything and collapse the trend window into a single jump; the gentler memo decay lets a
    trajectory register as a slope. Kept a parameter for Stage-A/B sweeps.

    **`rho_tier` (= 0.2, ~3.5-week half-life)** follows memo §9 (`ρ_tier = ρ`, half-life 3-4 weeks),
    NOT the task-template placeholder of 1.0. With a ~1-week half-life the most recent finalized week
    dominates the read regardless of `max_window`, so a longer window cannot damp a single-week blip
    and I13's "windowed freeze does not whipsaw" claim fails on the shipped default. The gentler memo
    decay lets older weeks dilute a blip, which is what makes the window length actually matter (the
    brief §7 scenario-13 sweep). Owner-confirmed (2026-06-22). Stage-B may retune within 0.1-0.4.
    """
    params = params or BespokeParams()
    games = list(games)
    weeks = sorted({g.week for g in games})
    window = TierWindow(max_weeks=max_window)

    attribution: dict[str, list[CreditBreakdown]] = {}
    ratings: dict[str, float] = {}
    tiers: dict[str, int] = {}
    center_offset = 0.0
    # Per-team rating series across finalized weeks → the trend signal (memo §6). Keyed by team; each
    # value is the (week, converged rating) points, in week order (I8: a fixed, deterministic series).
    rating_series: dict[str, list[tuple[int, float]]] = {}

    # Count weeks *finalized so far*, not weeks the window retains: with a short window (e.g.
    # max_window=1) the window holds one week yet history may still be long enough to activate.
    n_finalized = 0
    for w in weeks:
        teams_w, entries_w = _build_entries([g for g in games if g.week <= w], params)
        # Cold start: need >= 2 finalized weeks before the frozen window is trustworthy (memo §5),
        # so weeks 1-2 run tier-agnostic and the window activates from week 3 regardless of length.
        active = n_finalized >= 2
        frozen = {t: (window.frozen_tier(t, rho=rho_tier) if active else None) for t in teams_w}

        def margin_fn(raw: float, result: str, opp: str, _frozen: dict = frozen) -> float:
            return scaled_margin(raw, result, _frozen.get(opp), params)

        r = _solve(teams_w, entries_w, params, margin_fn, rho=rho, lam=lam, tol=tol, max_iter=max_iter, init=None)
        attribution, ratings, center_offset = _attribute(teams_w, entries_w, r, params, margin_fn, lam, rho=rho)
        tiers = detect_tiers(ratings, tier_count=tier_count, gap_c=gap_c)
        window.add_week(w, tiers)
        for t, rt in ratings.items():
            rating_series.setdefault(t, []).append((w, rt))
        n_finalized += 1

    # Trend = OLS slope of each team's rating over the last `trend_window` finalized weeks (memo §6).
    trend = {t: _ols_slope(series[-trend_window:]) for t, series in rating_series.items()}

    return RateResult(
        ratings=ratings,
        tiers=tiers,
        per_game_attribution=attribution,
        trend=trend,
        center_offset=center_offset,
    )
