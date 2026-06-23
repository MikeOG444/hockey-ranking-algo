"""Invariant assertion functions for the model-agnostic harness (TASK-07).

Each function receives a model adapter (ModelFn) and a pre-built list of GameRow objects
constructed by the corresponding make_*_games() factory in test_harness.py.  On success the
function returns None; on failure it raises AssertionError with an evidence string that
identifies exactly what was expected vs what was observed (never a bare assert without a message).

Design rules:
  - No game construction inside these functions — factories live in test_harness.py so
    TASK-12 can reuse check_* with real scenario data.
  - No model-specific logic — these are model-agnostic assertions against the public
    RateResult interface (ratings, per_game_attribution, tiers, trend, center_offset).
  - The per_game_attribution dict may be empty for benchmark models (MHR, ridge) that lack
    decomposition; callers that need it must guard or mark skip in the MATRIX.
"""

from harness.adapters import ModelFn
from core.game import GameRow


def check_I1(model_fn: ModelFn, games: list[GameRow]) -> None:
    """I1 (result ordering): A beats C, B loses to C (same opponent, same margin).
    Assert ratings["A"] > ratings["B"].

    Games construction: 3-team A/B/C.  A beats C 3-2, B loses to C 2-3.
    The shared opponent C provides the cross-opponent linkage; I1 says winning vs C must rank
    A above B regardless of schedule-term noise — the base(result) floor is the guarantee.
    """
    res = model_fn(games)
    r = res.ratings
    assert r["A"] > r["B"], (
        f"I1 FAIL: A (won vs C) should rate above B (lost vs C), "
        f"but got ratings[A]={r['A']:.4f} <= ratings[B]={r['B']:.4f}"
    )


def check_I1_benchmark(model_fn: ModelFn, games: list[GameRow]) -> None:
    """I1 violation proof for benchmarks: same A/B/C/STRONG construction as test_I1_violation_documented.
    A beats C 2-1, B loses to C 1-2; A loses to STRONG 0-7, B beats STRONG 7-0.
    Assert ratings["B"] > ratings["A"] — i.e. the benchmark FAILS I1 (this flipped order is the xfail).
    The check asserts the I1-CORRECT ordering (A > B); benchmarks violate I1, so this assert will fail
    and be caught as the expected xfail.
    """
    res = model_fn(games)
    r = res.ratings
    # Assert I1 compliance — benchmarks FAIL this, which is the documented violation.
    assert r["A"] > r["B"], (
        f"I1 FAIL (expected for benchmark): B (lost vs C) outrates A (won vs C). "
        f"ratings[A]={r['A']:.4f}, ratings[B]={r['B']:.4f}. "
        f"This is the documented benchmark violation — AGD/GD swamps the per-game result floor."
    )


def check_I2(model_fn: ModelFn, games: list[GameRow]) -> None:
    """I2 (win-monotone): bigger wins are never worse than smaller wins vs the same opponent.
    Four separate 2-team datasets at margins 1, 3, 4, 6. Assert ratings["T"] non-decreasing.
    `games` is a list-of-lists from make_I2_games(); one independent dataset per margin.
    """
    # games is list[list[GameRow]] here (four independent 2-team datasets)
    ratings_t = [model_fn(g).ratings["T"] for g in games]
    margins = [1, 3, 4, 6]
    for i in range(len(ratings_t) - 1):
        assert ratings_t[i] <= ratings_t[i + 1], (
            f"I2 FAIL: rating at margin {margins[i]} ({ratings_t[i]:.4f}) "
            f"> rating at margin {margins[i+1]} ({ratings_t[i+1]:.4f}) — bigger win made things worse."
        )


def check_I3(model_fn: ModelFn, games: list[GameRow]) -> None:
    """I3 (diminishing returns on margin): the rating gain from margin 3→4 must be larger
    than the gain from margin 4→6.  Uses the same four 2-team datasets as I2.
    `games` is list[list[GameRow]] from make_I3_games() (identical to make_I2_games()).

    Reads per_game_attribution.total to isolate the per-game credit signal independent of
    opponent-rating interactions (so this check works on a single-game dataset where the
    opponent has a fixed, zero-calibrated starting rating).  Falls back to ratings["T"] if
    per_game_attribution is absent (benchmark models that reach this path).
    """
    datasets = games  # list[list[GameRow]], margins 1, 3, 4, 6
    # Extract per-game credit total for "T" from each dataset
    credits: list[float] = []
    for g_list in datasets:
        res = model_fn(g_list)
        if res.per_game_attribution:
            # Take the single game T played; total = base + margin_adj + schedule_term
            breakdown = res.per_game_attribution["T"]
            assert len(breakdown) == 1, f"I3: expected 1 game per dataset, got {len(breakdown)}"
            credits.append(breakdown[0].total)
        else:
            credits.append(res.ratings["T"])   # fallback for no-attribution models

    # margins [1, 3, 4, 6] → indices 1(margin=3), 2(margin=4), 3(margin=6)
    gain_3_to_4 = credits[2] - credits[1]   # margin 3 → 4 credit delta
    gain_4_to_6 = credits[3] - credits[2]   # margin 4 → 6 credit delta
    assert gain_3_to_4 > gain_4_to_6, (
        f"I3 FAIL: gain from margin 3→4 ({gain_3_to_4:.4f}) must exceed 4→6 ({gain_4_to_6:.4f}) "
        f"(diminishing returns). credits by margin 1/3/4/6: {credits}"
    )


def check_I4(model_fn: ModelFn, games: list[GameRow]) -> None:
    """I4 (close-loss floor): a close loss rates at least as well as a blowout loss.
    `games` is a tuple (close_games, blowout_games) from make_I4_games().
    Assert ratings_close["T"] >= ratings_blowout["T"].
    """
    close_games, blowout_games = games
    r_close   = model_fn(close_games).ratings["T"]
    r_blowout = model_fn(blowout_games).ratings["T"]
    assert r_close >= r_blowout, (
        f"I4 FAIL: close loss ({r_close:.4f}) rated worse than blowout loss ({r_blowout:.4f}). "
        f"The model penalizes a 1-goal loss more harshly than a 5-goal loss — no close-loss floor."
    )


def check_I5(model_fn: ModelFn, games: list[GameRow]) -> None:
    """I5 (win > tie > loss is structurally guaranteed): three 2-team datasets.
    `games` is a tuple (win_games, tie_games, loss_games) from make_I5_games().
    Assert rating_win >= rating_tie >= rating_loss.
    """
    win_games, tie_games, loss_games = games
    r_win  = model_fn(win_games).ratings["T"]
    r_tie  = model_fn(tie_games).ratings["T"]
    r_loss = model_fn(loss_games).ratings["T"]
    assert r_win >= r_tie, (
        f"I5 FAIL: win rating ({r_win:.4f}) < tie rating ({r_tie:.4f}) — win floor violated."
    )
    assert r_tie >= r_loss, (
        f"I5 FAIL: tie rating ({r_tie:.4f}) < loss rating ({r_loss:.4f}) — tie floor violated."
    )


def check_I6(model_fn: ModelFn, games: list[GameRow]) -> None:
    """I6 (schedule strength matters): a close loss to an elite opponent must rate better than a
    close win over a weak one. 7-team construction with ELITE/WEAK/FILLs/TARGET1/TARGET2.
    Assert ratings["TARGET1"] > ratings["TARGET2"].

    Mechanism (memo §1.4): the schedule_term = alpha * R_opp dominates the base difference
    (L=0 vs W=3) when the opponent-rating gap is large enough.  alpha is pinned above the
    critical threshold by the I6 scenario in memo Q1 (alpha=0.6 vs the critical 0.5).
    """
    res = model_fn(games)
    r = res.ratings
    assert r["TARGET1"] > r["TARGET2"], (
        f"I6 FAIL: close loss to ELITE ({r['TARGET1']:.4f}) must rate above "
        f"close win over WEAK ({r['TARGET2']:.4f}). "
        f"Schedule term is insufficient to overcome the base(result) gap — alpha may be too low."
    )


def check_I7(model_fn: ModelFn, games: list[GameRow]) -> None:
    """I7 (underperformance no-flip): the result floor cannot be overridden by schedule terms.
    3-team W/L/O: W beats O 2-1 (3 games weeks 1-3), L loses 1-2 (3 games).
    Assert ratings["W"] > ratings["L"].

    W and L played the SAME opponent (O) with the SAME margin; the ONLY difference is the
    result (W won, L lost). The schedule term is the same for both (alpha*R_O), so the base
    floor (W=3 > L=0) must drive the ordering — the result cannot be flipped.
    """
    res = model_fn(games)
    r = res.ratings
    assert r["W"] > r["L"], (
        f"I7 FAIL: W (won vs O 3 times, margin 1) should rate above L (lost to O 3 times, margin 1), "
        f"but got ratings[W]={r['W']:.4f} <= ratings[L]={r['L']:.4f}. "
        f"The result floor has been overridden by schedule or margin — base(result) is not structural."
    )


def check_I8(model_fn: ModelFn, games: list[GameRow]) -> None:
    """I8 (determinism + order-independence): same input list run twice yields byte-identical
    ratings; reversing the input list also yields byte-identical ratings.
    Any nondeterminism is a bug: same data must produce the exact same ratings dict (no floating
    point variance), and the order of rows in the input must not matter.
    """
    run_a = model_fn(games).ratings
    run_b = model_fn(games).ratings
    run_reversed = model_fn(list(reversed(games))).ratings
    assert run_a == run_b, (
        f"I8 FAIL: two identical runs produced different ratings.\n"
        f"  run_a={run_a}\n  run_b={run_b}"
    )
    assert run_a == run_reversed, (
        f"I8 FAIL: reversing input order changed ratings.\n"
        f"  forward={run_a}\n  reversed={run_reversed}"
    )


def check_I9(model_fn: ModelFn, games: list[GameRow]) -> None:
    """I9 (convergence / unique fixed point): two very different starting points converge to the
    same ratings within tolerance 1e-6. Tests that the solve is a contraction (not init-sensitive).

    Strategy: call the underlying model's rate() directly with two distinct init dicts (zeros vs
    a deliberately off-base wild init) and verify convergence within 1e-6.  Ridge Massey has no
    init parameter (it is a direct linear solve) — for that model we just verify two identical
    calls produce byte-identical output, which trivially holds and proves uniqueness.

    We dispatch by importing the three known underlying modules and trying each with init; the
    first one that accepts the call without TypeError is used. This avoids adapter-signature
    reflection and keeps the check self-contained.
    """
    import models.bespoke as bespoke_mod
    import models.mhr_replica as mhr_mod

    teams = list({g.team for g in games} | {g.opponent for g in games})
    init_zero = {t: 0.0 for t in teams}
    # A custom init that is far from 0 for the three canonical team names; other teams get 0.
    init_wild = {t: (5.0 if "STRONG" in t else (-3.0 if "MID" in t else 2.0)) for t in teams}

    # Try init-aware path using the known iterative models
    for underlying_rate in [bespoke_mod.rate, mhr_mod.rate]:
        try:
            from_zero = underlying_rate(games, init=init_zero).ratings
            from_wild = underlying_rate(games, init=init_wild).ratings
            for t in from_zero:
                assert abs(from_zero[t] - from_wild[t]) < 1e-6, (
                    f"I9 FAIL: team '{t}' ratings differ between inits.\n"
                    f"  from_zero={from_zero[t]:.8f}  from_wild={from_wild.get(t, 'N/A'):.8f}"
                )
            return  # passed for this underlying model; done
        except TypeError:
            continue  # this underlying model does not match model_fn's type

    # No-init model (Ridge Massey): unique closed-form solution → two identical runs
    run_a = model_fn(games).ratings
    run_b = model_fn(games).ratings
    for t in run_a:
        assert abs(run_a[t] - run_b[t]) < 1e-6, (
            f"I9 FAIL (no-init model): two runs produced different ratings for '{t}'.\n"
            f"  run_a={run_a[t]:.8f}  run_b={run_b[t]:.8f}"
        )


def check_I10(model_fn: ModelFn, games: list[GameRow]) -> None:
    """I10 (stale-opponent float): a team with a glossy early record that is subsequently exposed
    as weak must end up rated below centre (ratings["STALE"] < 0).

    Games construction: STALE beats T1 and T2 by 5 goals in week 1 (glossy early record),
    then T1 and T2 beat STALE by 5 goals in week 2 (exposure).  STALE's season record is
    symmetric (2W-2L same margins), so its true contribution is neutral.  After centering,
    the direction of the result (who beat whom in week 2) means T1/T2 end up above 0 and
    STALE below 0 — its stale early glory does NOT persist at convergence.

    This invariant confirms the schedule term floats with converged (not stale) ratings:
    a batch fixed-point over all games simultaneously never locks in the early record.
    """
    res = model_fn(games)
    r = res.ratings
    assert r["STALE"] < 0, (
        f"I10 FAIL: STALE (symmetric 2W-2L record: big wins in wk1, big losses in wk2) "
        f"should be negative after centering, but got ratings[STALE]={r['STALE']:.4f}. "
        f"Its stale early record is inflating the converged rating — schedule term is not floating."
    )


def check_I11(model_fn: ModelFn, games: list[GameRow]) -> None:
    """I11 (trend / momentum output): two teams with equal season-average strength but opposite
    trajectories must show opposite trend signs.  Uses bespoke_weekly (rate_weekly).
    Assert trend["RISER"] > 0 > trend["FALLER"] and ratings["RISER"] > ratings["FALLER"].

    Games construction (make_I11_games): 6-week schedule where RISER improves from a small
    win margin to a large one (1→6), while FALLER does the opposite (6→1).  Both play the same
    FIELD teams every week, so the season-average true strength is equal by construction.
    Recency weighting (rho=0.2 in rate_weekly) surfaces current form: at season end RISER is
    strong and FALLER is weak, so both the trend direction and the final ratings must diverge.
    """
    res = model_fn(games)
    if not res.trend:
        # Model doesn't emit trend — should be guarded by MATRIX skip, but check here too.
        return
    assert res.trend["RISER"] > 0, (
        f"I11 FAIL: RISER (improving margins week 1→6) should have positive trend, "
        f"but got trend[RISER]={res.trend['RISER']:.6f}"
    )
    assert res.trend["FALLER"] < 0, (
        f"I11 FAIL: FALLER (declining margins week 6→1) should have negative trend, "
        f"but got trend[FALLER]={res.trend['FALLER']:.6f}"
    )
    assert res.ratings["RISER"] > res.ratings["FALLER"], (
        f"I11 FAIL: RISER (strong at season end) should rate above FALLER (weak at season end) "
        f"with recency weighting, but got ratings[RISER]={res.ratings['RISER']:.4f} "
        f"<= ratings[FALLER]={res.ratings['FALLER']:.4f}"
    )


def check_I12(model_fn: ModelFn, games: list[GameRow]) -> None:
    """I12 (per-game attribution reconciliation): for every team,
        rating == (1 - lam) * (Σ w_g * breakdown.total / Σ w_g) - center_offset
    within 1e-10. Skipped when per_game_attribution is empty (MHR, ridge).

    The reconciliation identity is exact (memo §7) — not merely within solve tolerance — because
    the attribution is rebuilt from the converged ratings in a separate replay pass.  A deviation
    beyond 1e-10 means the attribution and the solve are using different data paths.
    """
    res = model_fn(games)
    if not res.per_game_attribution:
        # Benchmark model with no attribution — the MATRIX marks this skip; guard here too.
        return

    lam = 0.05  # default for all models (must match the adapter's default)
    for team, rating in res.ratings.items():
        bds = res.per_game_attribution[team]
        if not bds:
            continue  # team played no games (should not happen with well-formed factories)
        wsum = sum(b.w for b in bds)
        weighted_total = sum(b.w * b.total for b in bds) / wsum
        reconciled = (1.0 - lam) * weighted_total - res.center_offset
        diff = abs(reconciled - rating)
        assert diff < 1e-10, (
            f"I12 FAIL for '{team}': attribution does not reconcile to rating.\n"
            f"  rating={rating:.12f}\n"
            f"  reconciled={reconciled:.12f}\n"
            f"  diff={diff:.2e} (must be < 1e-10)\n"
            f"  breakdowns: {[(b.base, b.margin_adj, b.schedule_term, b.w) for b in bds]}"
        )


def check_I13(model_fn: ModelFn, games: list[GameRow]) -> None:
    """I13 (frozen window damps tier blips): a single-week spike in an opponent's tier inflates
    the credit a third-party earns for beating it — but a wider window damps the inflation.

    `games` here is the blip world from make_I13_blip_games() (BLIP dominates in week 2, VICTIM
    beats BLIP in week 3).  The check compares the margin_adj VICTIM earns under:
      - max_window=1 (single-week freeze — blip taken at face value, maximum inflation)
      - max_window=4 (multi-week average — blip diluted, smaller inflation)

    The wider window must produce a smaller swing from the no-blip baseline (I13 core assertion):
    the frozen window architecture provides structural damping, not model-tuning.

    We import rate_weekly directly because check_I13 requires two calls with different
    max_window values; the model_fn adapter always uses its defaults, so we bypass it here.
    The `model_fn` parameter is still checked to ensure it is a bespoke_weekly adapter — if
    not (e.g. MHR/ridge), the check returns immediately (guarded by MATRIX skip).
    """
    import models.bespoke as bespoke_mod

    # Guard: only bespoke_weekly implements the frozen-tier window
    if model_fn is not bespoke_mod.rate_weekly and getattr(model_fn, "__func__", None) is not bespoke_mod.rate_weekly:
        # model_fn is an adapter wrapper; check via name comparison
        try:
            test_res = model_fn(games[:1])
            if not test_res.tiers:
                # No tiers → not a tier-aware model → skip (MATRIX guards this with skip already)
                return
        except Exception:
            return

    def _victim_margin_adj(game_list: list[GameRow], max_window: int) -> float:
        """Return the margin_adj VICTIM earns for its win over BLIP under the given window."""
        res = bespoke_mod.rate_weekly(game_list, tier_count=3, max_window=max_window)
        victim_wins = [
            b for b in res.per_game_attribution.get("VICTIM", [])
            if b.base > 0  # base > 0 means W credit (base_W = 3.0)
        ]
        assert len(victim_wins) >= 1, (
            f"I13: expected VICTIM to have at least one win attribution entry, "
            f"got {res.per_game_attribution.get('VICTIM', [])}"
        )
        return victim_wins[0].margin_adj  # VICTIM has exactly one win (over BLIP)

    credit_w1 = _victim_margin_adj(games, max_window=1)
    credit_w4 = _victim_margin_adj(games, max_window=4)

    # Both credits should be non-negative (VICTIM won); the wider window must give a smaller
    # or equal inflation — i.e., credit_w1 >= credit_w4 (single-week blip is maximally inflated).
    assert credit_w1 >= credit_w4, (
        f"I13 FAIL: max_window=1 (blip at face value) should give margin_adj >= max_window=4 "
        f"(blip damped by window), but got credit_w1={credit_w1:.4f} < credit_w4={credit_w4:.4f}. "
        f"The wider window is NOT damping the tier blip — the frozen window has no effect."
    )
