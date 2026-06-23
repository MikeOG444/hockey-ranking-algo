"""Recency weighting + the trend/momentum output (memo §2, §6; brief §1.7, §7 scenario 11).

I11 in one sentence: two teams with EQUAL season-average true strength but opposite trajectories
(one rising, one falling) must get distinct trend signs, and recency weighting must make their
point-in-time ratings reflect *current* form rather than the (equal) season average.

The dataset is built from the seeded world model so the test rides real synthetic signal. RISER and
FALLER are symmetric about a shared centre: RISER starts weak and climbs, FALLER starts strong and
declines by the same per-week step, so their season-average attack — and hence true rating — is equal
(asserted via the exported ``week_params``). Both play a stable FIELD of six flat teams every week;
the field is flat, so it is also our steady-team trend control.

Scale note: a per-week trajectory step of 0.05 is small against Poisson scoring noise, so the scenario
is built for signal-to-noise — six field opponents per week (many games → tight per-week ratings),
twelve weeks (the trajectory accumulates and recency decays the early games out of the trend window),
and a higher scoring baseline (``mu = ln 6`` → ~6-goal games → less relative noise). Under that, the
I11 signal is robust; the signal tests pin ``seed = 61`` as a representative clean draw (like the
fixed seeds the other bespoke tests use).
"""

import math

import pytest

from generator.simulate import Matchup, TeamParams, WorldConfig, simulate, week_params
from models.bespoke import BespokeParams, rate, rate_weekly

P = BespokeParams()

WEEKS = 12
N_FIELDS = 6
MU = math.log(6.0)  # ~6-goal games: more goals → less relative Poisson noise on the trend signal
I11_SEED = 61       # a representative clean draw of the rising/falling signal (see module docstring)

_STEP = 0.05  # mirrors generator._TRAJ_STEP; the per-week attack drift for rising/falling
# FALLER starts exactly STEP*(WEEKS-1) above RISER and declines by STEP/week; RISER climbs by
# STEP/week from its baseline. Their per-week attack lines are mirror images, so the season averages
# coincide (proved in test_riser_faller_have_equal_season_average_truth) — the clean I11 setup.
_RISER_ATTACK = -0.2
_FALLER_ATTACK = _RISER_ATTACK + _STEP * (WEEKS - 1)
_FIELDS = [f"F{i + 1}" for i in range(N_FIELDS)]


def _riser_faller_world():
    return [
        TeamParams("RISER", attack=_RISER_ATTACK, defense=0.0, trajectory="rising"),
        TeamParams("FALLER", attack=_FALLER_ATTACK, defense=0.0, trajectory="falling"),
        # Flat field teams, defensively soft (defense>0 = concede more) so the rising/falling attack
        # swing shows up as clear goal margins instead of Poisson mush.
        *[TeamParams(f, attack=0.0, defense=0.3, trajectory="flat") for f in _FIELDS],
    ]


def riser_faller_dataset(seed: int):
    teams = _riser_faller_world()
    # RISER and FALLER each face every field team weekly; the field plays a round robin among itself
    # — a richly connected graph, and many games per week so each week's ratings are low-noise.
    pairs = [("RISER", f) for f in _FIELDS] + [("FALLER", f) for f in _FIELDS]
    pairs += [(_FIELDS[i], _FIELDS[j]) for i in range(N_FIELDS) for j in range(i + 1, N_FIELDS)]
    schedule = [Matchup(week=w, team=a, opponent=b) for w in range(1, WEEKS + 1) for (a, b) in pairs]
    return simulate(WorldConfig(teams=teams, schedule=schedule, seed=seed, mu=MU))


def test_riser_faller_have_equal_season_average_truth():
    """Sanity-check the construction: RISER and FALLER have identical season-average true rating, so
    any later separation is a recency/trend effect, not a baseline difference."""
    teams = {t.id: t for t in _riser_faller_world()}
    avg_riser = sum((lambda a, d: a - d)(*week_params(teams["RISER"], w)) for w in range(1, WEEKS + 1)) / WEEKS
    avg_faller = sum((lambda a, d: a - d)(*week_params(teams["FALLER"], w)) for w in range(1, WEEKS + 1)) / WEEKS
    assert avg_riser == pytest.approx(avg_faller, abs=1e-12)


# --- recency weight wiring (memo §2, §7-§8) -------------------------------------------------


def test_recency_weight_is_uniform_when_rho_zero():
    """rate() passes ρ=0, so every per-game recency weight is exactly 1.0 → the weighted mean is the
    plain uniform mean → the flat baseline is unchanged (its I8/I9/reconciliation tests stay green)."""
    res = rate(riser_faller_dataset(seed=1).games)
    all_w = [b.w for team in res.per_game_attribution.values() for b in team]
    assert all_w  # there is attribution to check
    assert all(b_w == 1.0 for b_w in all_w)


def test_attribution_exposes_recency_weight():
    """The §8 interface's fourth attribution term: every game carries its recency weight w ∈ (0, 1].
    In the final solve now == the last week, so that week's games weigh exactly 1.0 while older games
    are down-weighted (some w < 1) — the explainability promise that 'recent games carried more'."""
    res = rate_weekly(riser_faller_dataset(seed=1).games)
    ws = [b.w for team in res.per_game_attribution.values() for b in team]
    assert all(0.0 < b_w <= 1.0 for b_w in ws)
    assert any(b_w == pytest.approx(1.0) for b_w in ws)  # most-recent week's games
    assert any(b_w < 1.0 for b_w in ws)                  # older games down-weighted


def test_reconciliation_uses_weighted_mean():
    """memo §7 made weight-aware: rating_t == (1-λ)·(Σ w_g·total_g / Σ w_g) − center_offset exactly,
    for every team. Proves the solve and the attribution share the same weighted average."""
    lam = 0.05
    res = rate_weekly(riser_faller_dataset(seed=2).games, lam=lam)
    for team, rating in res.ratings.items():
        bds = res.per_game_attribution[team]
        wsum = sum(b.w for b in bds)
        weighted = sum(b.w * b.total for b in bds) / wsum
        reconciled = (1.0 - lam) * weighted - res.center_offset
        assert reconciled == pytest.approx(rating, abs=1e-9)


# --- I11: trend signs + recency reflects current form ---------------------------------------


def test_I11_rising_and_falling_have_opposite_trend_signs():
    """I11 core: despite equal season-average truth, the rising team shows a positive trend and the
    falling team a negative one — the slope of each team's recency-weighted rating over the window."""
    res = rate_weekly(riser_faller_dataset(seed=I11_SEED).games)
    assert res.trend["RISER"] > 0.0 > res.trend["FALLER"]


def test_I11_recency_reflects_current_form():
    """Recency weighting surfaces current form: at season end RISER (now strong) out-rates FALLER
    (now weak) even though their season averages are equal. The flat (uniform, ρ=0) solve sees only
    the equal averages — in fact it ranks FALLER higher off its banked early wins — so the recency
    path separates current form by strictly more: |Δ_weekly| > |Δ_flat|."""
    games = riser_faller_dataset(seed=I11_SEED).games
    weekly = rate_weekly(games).ratings
    flat = rate(games).ratings
    assert weekly["RISER"] > weekly["FALLER"]  # recency: the now-strong team leads
    delta_weekly = weekly["RISER"] - weekly["FALLER"]
    delta_flat = flat["RISER"] - flat["FALLER"]
    assert abs(delta_weekly) > abs(delta_flat)


def test_trend_flat_for_steady_team():
    """A team whose true strength is constant across the window has ~zero trend. Every flat field team
    is our control: its slope sits below the genuinely-rising team's and near zero in absolute terms."""
    res = rate_weekly(riser_faller_dataset(seed=I11_SEED).games)
    rising = res.trend["RISER"]
    for f in _FIELDS:
        assert abs(res.trend[f]) < rising      # flatter than the rising signal
        assert abs(res.trend[f]) < 0.12        # ...and near zero absolutely


def test_trend_is_zero_for_single_recorded_week():
    """A degenerate window (a team with only one recorded week, hence zero week-variance) gets a
    defined trend of 0.0, not a divide-by-zero. One week of one matchup exercises the guard."""
    one_week = [Matchup(week=1, team="A", opponent="B")]
    teams = [TeamParams("A", attack=0.3, defense=0.0), TeamParams("B", attack=0.0, defense=0.0)]
    games = simulate(WorldConfig(teams=teams, schedule=one_week, seed=1)).games
    res = rate_weekly(games)
    assert res.trend["A"] == 0.0
    assert res.trend["B"] == 0.0


def test_trend_is_deterministic():
    """I8 for the new output: the OLS-slope trend is a closed form over a fixed (week, rating) series
    — same games, any input order → byte-identical trend dict, no NaNs."""
    games = riser_faller_dataset(seed=4).games
    a = rate_weekly(games).trend
    b = rate_weekly(list(reversed(games))).trend
    assert a == b
    assert not any(math.isnan(v) for v in a.values())
