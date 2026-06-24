"""§7 scenario builder functions — one per edge case.

Each builder returns ``(Dataset, dict)`` where:
- ``Dataset`` is a seeded simulate() output — purely Level-0 game rows + ground truth team params.
- ``dict`` is a plain-Python assertion metadata dict (no lambdas, safe to serialize later for
  TASK-12's comparison runner).

Design constraints (non-negotiable):
- Observed-vs-derived wall: TeamParams attributes (attack, defense, trajectory) are the ground
  truth. Never feed ratings or tiers back in as generator inputs.
- Determinism: every build_sNN is seeded; same seed → byte-identical Dataset (I8).
- No harness imports: these call rate_weekly() directly in their test files.
"""

from core.game import GameRow
from generator.simulate import Dataset, Matchup, TeamParams, WorldConfig, simulate


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _round_robin(teams: list[str], week_offset: int = 0) -> list[Matchup]:
    """One round-robin pass (each ordered pair once) starting at week 1 + week_offset."""
    matchups = []
    week = 1 + week_offset
    for i, a in enumerate(teams):
        for b in teams[i + 1:]:
            matchups.append(Matchup(week=week, team=a, opponent=b))
    return matchups


def _repeated_round_robin(teams: list[str], repeats: int) -> list[Matchup]:
    """repeats full round-robin passes; each pass occupies one week (week = pass index + 1)."""
    matchups = []
    for rep in range(repeats):
        for i, a in enumerate(teams):
            for b in teams[i + 1:]:
                matchups.append(Matchup(week=rep + 1, team=a, opponent=b))
    return matchups


def _pod_round_robin(pod: list[str], repeats: int) -> list[Matchup]:
    """Round-robin within a single pod, repeated across weeks 1..repeats."""
    return _repeated_round_robin(pod, repeats)


# ---------------------------------------------------------------------------
# Scenario 1 — Disconnected clusters (I8, I9)
# ---------------------------------------------------------------------------

def build_s01_disconnected(seed: int = 42) -> tuple[Dataset, dict]:
    """Two pods of 3 (A1–A3, B1–B3); zero cross-pod games; ≥6 weeks.

    The solver's regularization (λ>0) anchors both pods to a shared mean and prevents the
    free-constant explosion that unregularized solvers produce on disconnected graphs (I9).
    Determinism is guaranteed by the seeded RNG (I8).
    """
    pod_a = ["A1", "A2", "A3"]
    pod_b = ["B1", "B2", "B3"]

    # Pod A: moderately strong teams (attack - defense > 0 overall)
    teams = [
        TeamParams(id="A1", attack=0.4, defense=-0.1),   # true rating +0.5
        TeamParams(id="A2", attack=0.1, defense=0.0),    # true rating +0.1
        TeamParams(id="A3", attack=-0.1, defense=0.2),   # true rating -0.3
        TeamParams(id="B1", attack=0.5, defense=-0.2),   # true rating +0.7
        TeamParams(id="B2", attack=0.0, defense=0.1),    # true rating -0.1
        TeamParams(id="B3", attack=-0.2, defense=0.3),   # true rating -0.5
    ]

    # Symmetric 6 weeks: each pod plays a round-robin each week (3 games/week within each pod).
    schedule: list[Matchup] = []
    for week in range(1, 7):
        for i, a in enumerate(pod_a):
            for b in pod_a[i + 1:]:
                schedule.append(Matchup(week=week, team=a, opponent=b))
        for i, a in enumerate(pod_b):
            for b in pod_b[i + 1:]:
                schedule.append(Matchup(week=week, team=a, opponent=b))

    config = WorldConfig(teams=teams, schedule=schedule, seed=seed)
    dataset = simulate(config)
    return dataset, {
        "two_pods_no_cross": (pod_a, pod_b),
        "invariants": ["I8", "I9"],
    }


# ---------------------------------------------------------------------------
# Scenario 2 — Single bridge game (I8, I9)
# ---------------------------------------------------------------------------

def build_s02_bridge_game(seed: int = 42) -> tuple[Dataset, dict]:
    """Same pods as S01 with exactly one cross-game: A2 vs B2 in week 3.

    The bridge game is the only cross-pod evidence. After convergence, both A2 and B2 carry a
    non-zero schedule_term from that game (I12). The solver must still converge (I9).
    """
    pod_a = ["A1", "A2", "A3"]
    pod_b = ["B1", "B2", "B3"]

    teams = [
        TeamParams(id="A1", attack=0.4, defense=-0.1),
        TeamParams(id="A2", attack=0.1, defense=0.0),
        TeamParams(id="A3", attack=-0.1, defense=0.2),
        TeamParams(id="B1", attack=0.5, defense=-0.2),
        TeamParams(id="B2", attack=0.0, defense=0.1),
        TeamParams(id="B3", attack=-0.2, defense=0.3),
    ]

    schedule: list[Matchup] = []
    for week in range(1, 7):
        for i, a in enumerate(pod_a):
            for b in pod_a[i + 1:]:
                schedule.append(Matchup(week=week, team=a, opponent=b))
        for i, a in enumerate(pod_b):
            for b in pod_b[i + 1:]:
                schedule.append(Matchup(week=week, team=a, opponent=b))

    # The single bridge game in week 3.
    schedule.append(Matchup(week=3, team="A2", opponent="B2"))

    config = WorldConfig(teams=teams, schedule=schedule, seed=seed)
    dataset = simulate(config)
    return dataset, {
        "bridge_participants": ("A2", "B2"),
        "bridge_week": 3,
        "invariants": ["I8", "I9", "I12"],
    }


# ---------------------------------------------------------------------------
# Scenario 3 — Schedule inflation "Dallas" (I6, I10)
# ---------------------------------------------------------------------------

def build_s03_schedule_inflation(seed: int = 42) -> tuple[Dataset, dict]:
    """T_PADDED beats bottom-tier opponents; T_GAUNTLET beats top-tier opponents; same record.

    Both teams win 5 games by 2 goals each (controlled exact outcomes via GameRow). The
    difference is entirely in opponent strength — the schedule_term channel (I6, I10) should
    make T_GAUNTLET rate higher because it beat stronger teams.

    We plant exact GameRows to guarantee the W/L outcome regardless of Poisson variance.
    The STRONG and WEAK opponents also play each other to let the solver discover the tier gap.

    Opponent strengths (used by the solver via their game results):
    - WEAK_1..5:  attack-defense ≈ -1.5 (they lose heavily to STRONG teams)
    - STRONG_1..5: attack-defense ≈ +1.5 (they beat WEAK teams convincingly)
    """
    ground_truth = [
        TeamParams(id="T_PADDED",   attack=0.3, defense=0.0),
        TeamParams(id="T_GAUNTLET", attack=0.3, defense=0.0),
        TeamParams(id="WEAK_1",   attack=-0.5, defense=1.0),
        TeamParams(id="WEAK_2",   attack=-0.5, defense=1.0),
        TeamParams(id="WEAK_3",   attack=-0.5, defense=1.0),
        TeamParams(id="WEAK_4",   attack=-0.5, defense=1.0),
        TeamParams(id="WEAK_5",   attack=-0.5, defense=1.0),
        TeamParams(id="STRONG_1", attack=0.75, defense=-0.75),
        TeamParams(id="STRONG_2", attack=0.75, defense=-0.75),
        TeamParams(id="STRONG_3", attack=0.75, defense=-0.75),
        TeamParams(id="STRONG_4", attack=0.75, defense=-0.75),
        TeamParams(id="STRONG_5", attack=0.75, defense=-0.75),
    ]

    games: list[GameRow] = []
    weak_ids = [f"WEAK_{i}" for i in range(1, 6)]
    strong_ids = [f"STRONG_{i}" for i in range(1, 6)]

    # Weeks 1-5: T_PADDED beats WEAK opponents; T_GAUNTLET beats STRONG opponents (both 3-1, 2-goal margin).
    for week, (weak, strong) in enumerate(zip(weak_ids, strong_ids), start=1):
        # T_PADDED beats WEAK — 3-1 (2-goal margin → "close" → bonus=0.0).
        games.append(GameRow(week=week, date=f"2025-10-{week:02d}", time="10:45",
                             team="T_PADDED", opponent=weak, goals_team=3, goals_opponent=1))
        games.append(GameRow(week=week, date=f"2025-10-{week:02d}", time="10:45",
                             team=weak, opponent="T_PADDED", goals_team=1, goals_opponent=3))
        # T_GAUNTLET beats STRONG — same margin 3-1.
        games.append(GameRow(week=week, date=f"2025-10-{week:02d}", time="10:45",
                             team="T_GAUNTLET", opponent=strong, goals_team=3, goals_opponent=1))
        games.append(GameRow(week=week, date=f"2025-10-{week:02d}", time="10:45",
                             team=strong, opponent="T_GAUNTLET", goals_team=1, goals_opponent=3))

    # Weeks 6-8: STRONG beats WEAK convincingly (8-0) to establish the tier gap the solver uses.
    for week in range(6, 9):
        for strong in strong_ids:
            for weak in weak_ids:
                games.append(GameRow(week=week, date=f"2025-1{week:01d}-01", time="10:45",
                                     team=strong, opponent=weak, goals_team=8, goals_opponent=0))
                games.append(GameRow(week=week, date=f"2025-1{week:01d}-01", time="10:45",
                                     team=weak, opponent=strong, goals_team=0, goals_opponent=8))

    dataset = Dataset(games=games, ground_truth=ground_truth)
    return dataset, {
        "padded_rates_below_gauntlet": ("T_PADDED", "T_GAUNTLET"),
        "invariants": ["I6", "I10"],
    }


# ---------------------------------------------------------------------------
# Scenario 4 — Stale opponent / float (I10)
# ---------------------------------------------------------------------------

def build_s04_stale_opponent(seed: int = 42) -> tuple[Dataset, dict]:
    """T_EARLY_STRONG declines (trajectory='falling'); T_BENEFICIARY beat it in week 1.
    T_CONTROL beat a constant mid-strength opponent in week 1.

    I10 (floating): by end of season T_EARLY_STRONG's converged rating is low (it's now weak),
    so the schedule credit T_BENEFICIARY earned from that week-1 win is re-rated downward. The
    solver uses T_EARLY_STRONG's current (low) rating in the schedule term, not the inflated
    early reading. T_BENEFICIARY should therefore rate ≤ T_CONTROL.

    Background teams (FILLER_1..5) play each other to establish a league context.
    """
    # T_EARLY_STRONG starts strong (attack=1.0) but falls -0.05/week. By week 8: attack ≈ 0.65.
    # T_CONTROL_OPP is constant at attack≈0.3 (mid-field) — T_CONTROL beats it in week 1.
    teams = [
        TeamParams(id="T_EARLY_STRONG",  attack=1.0, defense=-0.3, trajectory="falling"),
        TeamParams(id="T_BENEFICIARY",   attack=0.0, defense=0.0),
        TeamParams(id="T_CONTROL",       attack=0.0, defense=0.0),
        TeamParams(id="T_CONTROL_OPP",   attack=0.3, defense=-0.3),   # constant ~mid strength
        TeamParams(id="FILLER_1",        attack=0.2, defense=-0.1),
        TeamParams(id="FILLER_2",        attack=-0.1, defense=0.2),
        TeamParams(id="FILLER_3",        attack=0.0, defense=0.1),
    ]

    schedule: list[Matchup] = []

    # Week 1: the key planted games.
    # T_BENEFICIARY beats T_EARLY_STRONG (who is at peak attack=1.0 this week).
    schedule.append(Matchup(week=1, team="T_BENEFICIARY", opponent="T_EARLY_STRONG"))
    # T_CONTROL beats T_CONTROL_OPP (constant mid-strength) with the same approach.
    schedule.append(Matchup(week=1, team="T_CONTROL", opponent="T_CONTROL_OPP"))

    # Weeks 2-8: T_EARLY_STRONG continues to play (declining), fillers play each other.
    fillers = ["FILLER_1", "FILLER_2", "FILLER_3"]
    for week in range(2, 9):
        # T_EARLY_STRONG loses to fillers (declining, now visibly weak by later weeks).
        for f in fillers:
            schedule.append(Matchup(week=week, team=f, opponent="T_EARLY_STRONG"))
        # T_CONTROL_OPP plays fillers (establishes it as constant mid-field).
        schedule.append(Matchup(week=week, team="T_CONTROL_OPP", opponent="FILLER_1"))
        # Fillers round-robin to fill out the league.
        for i, a in enumerate(fillers):
            for b in fillers[i + 1:]:
                schedule.append(Matchup(week=week, team=a, opponent=b))

    config = WorldConfig(teams=teams, schedule=schedule, seed=seed)
    dataset = simulate(config)
    return dataset, {
        "beneficiary_not_inflated": ("T_BENEFICIARY", "T_CONTROL"),
        "invariants": ["I10"],
    }


# ---------------------------------------------------------------------------
# Scenario 5 — Giant-killer / noise (robustness)
# ---------------------------------------------------------------------------

def build_s05_giant_killer(seed: int = 42) -> tuple[Dataset, dict]:
    """T_LUCKY is weak (true -0.5) but seeded draws produce a lucky early run.
    T_ACTUAL_STRONG is genuinely strong (+1.0). Over enough games with enough opponents
    the model should surface T_ACTUAL_STRONG above T_LUCKY.

    Strategy: T_LUCKY plays against opponents close in strength to itself (so its wins are
    plausible) but accumulates a large enough game count that the underlying weakness shows.
    T_ACTUAL_STRONG plays a broader schedule so its strength is well-established.
    """
    teams = [
        TeamParams(id="T_LUCKY",         attack=-0.1, defense=0.4),  # true rating -0.5
        TeamParams(id="T_ACTUAL_STRONG", attack=0.6, defense=-0.4),  # true rating +1.0
        # Opponents for T_LUCKY: slightly weaker so luck produces wins early.
        TeamParams(id="WEAK_OPP_1",  attack=-0.3, defense=0.3),   # true -0.6
        TeamParams(id="WEAK_OPP_2",  attack=-0.2, defense=0.4),   # true -0.6
        TeamParams(id="WEAK_OPP_3",  attack=-0.1, defense=0.3),   # true -0.4
        # Opponents for T_ACTUAL_STRONG: genuinely mid-field.
        TeamParams(id="MID_OPP_1",   attack=0.1, defense=-0.1),   # true +0.2
        TeamParams(id="MID_OPP_2",   attack=0.0, defense=0.0),    # true 0.0
        TeamParams(id="MID_OPP_3",   attack=0.2, defense=-0.2),   # true +0.4
    ]

    schedule: list[Matchup] = []

    # Repeat schedule over ≥8 weeks so the underlying truth accumulates.
    weak_opps = ["WEAK_OPP_1", "WEAK_OPP_2", "WEAK_OPP_3"]
    mid_opps = ["MID_OPP_1", "MID_OPP_2", "MID_OPP_3"]

    for week in range(1, 9):
        # T_LUCKY plays the weak opponents (plausible wins, but their weakness registers in schedule).
        for opp in weak_opps:
            schedule.append(Matchup(week=week, team="T_LUCKY", opponent=opp))
        # T_ACTUAL_STRONG plays mid opponents (steady wins against quality).
        for opp in mid_opps:
            schedule.append(Matchup(week=week, team="T_ACTUAL_STRONG", opponent=opp))
        # Opponents also play each other to establish their strength in the solver.
        for i, a in enumerate(weak_opps):
            for b in weak_opps[i + 1:]:
                schedule.append(Matchup(week=week, team=a, opponent=b))
        for i, a in enumerate(mid_opps):
            for b in mid_opps[i + 1:]:
                schedule.append(Matchup(week=week, team=a, opponent=b))
        # Cross the two opponent pools so the solver can compare their strengths.
        schedule.append(Matchup(week=week, team="MID_OPP_1", opponent="WEAK_OPP_1"))

    config = WorldConfig(teams=teams, schedule=schedule, seed=seed)
    dataset = simulate(config)
    return dataset, {
        "strong_above_lucky": ("T_ACTUAL_STRONG", "T_LUCKY"),
        "invariants": [],
    }


# ---------------------------------------------------------------------------
# Scenario 6 — Win-but-should-drop (I7)
# ---------------------------------------------------------------------------

def build_s06_win_but_should_drop(seed: int = 42) -> tuple[Dataset, dict]:
    """T_UGLY wins by 1 goal each time; T_DOMINANT wins by 4+ goals. Same opponents, same record.

    We cannot directly control goal margins with the Poisson generator, so we engineer the
    attack/defense gaps to make the outcomes highly likely:
    - T_UGLY vs CLOSE_OPP: very similar strength → expected scores ~3-2 (1-goal margin likely).
    - T_DOMINANT vs CLOSE_OPP: T_DOMINANT has huge attack/defense advantage → expected ~8-0.

    Because the generator is Poisson-based there will be variance, but over 8 games the signal
    should dominate. We use the same set of CLOSE_OPP opponents for both teams.

    Rather than engineering Poisson to produce exactly 1-goal margins (impossible to guarantee),
    we use GameRow directly (bypassing simulate) to plant exact goal counts. This keeps the
    observed-vs-derived wall intact: the goals come from a hand-crafted "deterministic" world
    (the Level-0 contract is game rows, not how they were produced).
    """
    # Plant deterministic games using GameRow directly — this is valid since GameRow IS the
    # Level-0 contract; the generator is one way to produce them, not the only way.
    games: list[GameRow] = []
    ground_truth = [
        TeamParams(id="T_UGLY",      attack=0.0, defense=0.0),
        TeamParams(id="T_DOMINANT",  attack=2.0, defense=-2.0),
        TeamParams(id="SHARED_OPP",  attack=0.0, defense=0.0),
    ]

    for week in range(1, 9):
        # T_UGLY: close wins 2-1 (margin 1 → "close" bucket, no bonus).
        games.append(GameRow(week=week, date=f"2025-10-{week:02d}", time="10:45",
                             team="T_UGLY", opponent="SHARED_OPP",
                             goals_team=2, goals_opponent=1))
        games.append(GameRow(week=week, date=f"2025-10-{week:02d}", time="10:45",
                             team="SHARED_OPP", opponent="T_UGLY",
                             goals_team=1, goals_opponent=2))
        # T_DOMINANT: blowouts 8-0 (margin 8 → "5+" bucket, max bonus).
        games.append(GameRow(week=week, date=f"2025-10-{week:02d}", time="10:45",
                             team="T_DOMINANT", opponent="SHARED_OPP",
                             goals_team=8, goals_opponent=0))
        games.append(GameRow(week=week, date=f"2025-10-{week:02d}", time="10:45",
                             team="SHARED_OPP", opponent="T_DOMINANT",
                             goals_team=0, goals_opponent=8))

    dataset = Dataset(games=games, ground_truth=ground_truth)
    return dataset, {
        "dominant_above_ugly": ("T_DOMINANT", "T_UGLY"),
        "ugly_above_zero": "T_UGLY",
        "invariants": ["I7"],
    }


# ---------------------------------------------------------------------------
# Scenario 7 — Close-vs-tier / I6 end-to-end (I6) ← MOST CRITICAL
# ---------------------------------------------------------------------------

def build_s07_close_vs_tier(seed: int = 42) -> tuple[Dataset, dict]:
    """League of 12 teams with a genuine elite (T_TOP) and a genuine bottom (T_BOTTOM).

    After ≥8 weeks of round-robin play among the field, T_TOP's converged rating should be well
    above the mean and T_BOTTOM's well below. T_SUBJECT has two planted games:
      (a) 1-goal LOSS to T_TOP  → credit = base(L=0) + close_adj(0) + α*R_TOP
      (b) 1-goal WIN  over T_BOTTOM → credit = base(W=3) + close_adj(0) + α*R_BOTTOM

    I6 holds when α*(R_TOP - R_BOTTOM) > W - L = 3. The memo §11 Q1 caveat: the solver's
    centering compresses the converged spread. We use a strong elite (attack=2.0, defense=-2.0)
    and a genuinely weak bottom (attack=-1.5, defense=1.5) to maximize the gap.

    T_SUBJECT is exactly average (attack=0, defense=0) so it does not distort tier detection.
    """
    # T_TOP: genuinely elite — attack 2.0, defense -2.0 → true rating +4.0
    # T_BOTTOM: genuinely weak — attack -1.5, defense 1.5 → true rating -3.0
    # Field teams span the middle.
    teams = [
        TeamParams(id="T_TOP",    attack=2.0, defense=-2.0),   # true +4.0
        TeamParams(id="T_BOTTOM", attack=-1.5, defense=1.5),   # true -3.0
        TeamParams(id="T_SUBJECT", attack=0.0, defense=0.0),   # true 0.0 (observer)
        TeamParams(id="F1",  attack=0.4, defense=-0.3),         # true +0.7
        TeamParams(id="F2",  attack=0.2, defense=-0.1),         # true +0.3
        TeamParams(id="F3",  attack=0.0, defense=0.1),          # true -0.1
        TeamParams(id="F4",  attack=-0.1, defense=0.2),         # true -0.3
        TeamParams(id="F5",  attack=0.3, defense=-0.2),         # true +0.5
        TeamParams(id="F6",  attack=-0.2, defense=0.3),         # true -0.5
        TeamParams(id="F7",  attack=0.1, defense=0.0),          # true +0.1
        TeamParams(id="F8",  attack=-0.3, defense=0.4),         # true -0.7
        TeamParams(id="F9",  attack=0.5, defense=-0.4),         # true +0.9
    ]

    # Field teams for round-robin (excludes T_SUBJECT whose only games are the planted ones).
    field = ["T_TOP", "T_BOTTOM", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9"]
    schedule: list[Matchup] = []

    # 8 weeks of round-robin among the field (establishes tier spread).
    for week in range(1, 9):
        for i, a in enumerate(field):
            for b in field[i + 1:]:
                schedule.append(Matchup(week=week, team=a, opponent=b))

    # Planted games for T_SUBJECT in week 9 (after tiers have stabilized):
    # (a) T_SUBJECT loses to T_TOP by 1 goal — we plant this game.
    # (b) T_SUBJECT beats T_BOTTOM by 1 goal.
    # We use exact GameRow values in the dataset (same approach as S06).
    # But here we use simulate() for the field games, then append the planted games.
    config = WorldConfig(teams=teams, schedule=schedule, seed=seed)
    field_dataset = simulate(config)

    # Plant the two key T_SUBJECT games as exact GameRows (so goals are controlled).
    planted: list[GameRow] = [
        # (a) 1-goal loss to T_TOP: T_TOP scores 2, T_SUBJECT scores 1.
        GameRow(week=9, date="2026-06-01", time="10:45",
                team="T_SUBJECT", opponent="T_TOP",
                goals_team=1, goals_opponent=2),
        GameRow(week=9, date="2026-06-01", time="10:45",
                team="T_TOP", opponent="T_SUBJECT",
                goals_team=2, goals_opponent=1),
        # (b) 1-goal win over T_BOTTOM: T_SUBJECT scores 2, T_BOTTOM scores 1.
        GameRow(week=9, date="2026-06-01", time="10:45",
                team="T_SUBJECT", opponent="T_BOTTOM",
                goals_team=2, goals_opponent=1),
        GameRow(week=9, date="2026-06-01", time="10:45",
                team="T_BOTTOM", opponent="T_SUBJECT",
                goals_team=1, goals_opponent=2),
    ]

    all_games = field_dataset.games + planted
    dataset = Dataset(games=all_games, ground_truth=list(config.teams))
    return dataset, {
        "credit_loss_elite_beats_win_weak": ("T_SUBJECT", "T_TOP", "T_BOTTOM"),
        "invariants": ["I6"],
    }


# ---------------------------------------------------------------------------
# Scenario 8 — Tie handling (I5)
# ---------------------------------------------------------------------------

def build_s08_tie_handling(seed: int = 42) -> tuple[Dataset, dict]:
    """T_WIN, T_TIE, T_LOSE play identical schedules; only the contested game outcomes differ.

    All three teams play the same COMMON_OPP opponents; their contested games (vs each other's
    structural analog) differ by result: win, tie, or loss. We use exact GameRows to guarantee
    the result categories.

    The three teams are structurally identical in schedule — the rating difference comes entirely
    from the W/T/L floor (I5).
    """
    ground_truth = [
        TeamParams(id="T_WIN",   attack=0.0, defense=0.0),
        TeamParams(id="T_TIE",   attack=0.0, defense=0.0),
        TeamParams(id="T_LOSE",  attack=0.0, defense=0.0),
        TeamParams(id="COMMON_OPP", attack=0.0, defense=0.0),
    ]

    games: list[GameRow] = []

    for week in range(1, 9):
        date = f"2025-10-{week:02d}"

        # All three teams beat COMMON_OPP by 3 goals in odd weeks (same positive context).
        if week % 2 == 1:
            for team in ("T_WIN", "T_TIE", "T_LOSE"):
                games.append(GameRow(week=week, date=date, time="10:45",
                                     team=team, opponent="COMMON_OPP",
                                     goals_team=4, goals_opponent=1))
                games.append(GameRow(week=week, date=date, time="10:45",
                                     team="COMMON_OPP", opponent=team,
                                     goals_team=1, goals_opponent=4))
        else:
            # In even weeks: the contested game (the one where result type differs).
            # T_WIN wins their game 2-1.
            games.append(GameRow(week=week, date=date, time="10:45",
                                 team="T_WIN", opponent="COMMON_OPP",
                                 goals_team=2, goals_opponent=1))
            games.append(GameRow(week=week, date=date, time="10:45",
                                 team="COMMON_OPP", opponent="T_WIN",
                                 goals_team=1, goals_opponent=2))
            # T_TIE ties 1-1.
            games.append(GameRow(week=week, date=date, time="10:45",
                                 team="T_TIE", opponent="COMMON_OPP",
                                 goals_team=1, goals_opponent=1))
            games.append(GameRow(week=week, date=date, time="10:45",
                                 team="COMMON_OPP", opponent="T_TIE",
                                 goals_team=1, goals_opponent=1))
            # T_LOSE loses 1-2.
            games.append(GameRow(week=week, date=date, time="10:45",
                                 team="T_LOSE", opponent="COMMON_OPP",
                                 goals_team=1, goals_opponent=2))
            games.append(GameRow(week=week, date=date, time="10:45",
                                 team="COMMON_OPP", opponent="T_LOSE",
                                 goals_team=2, goals_opponent=1))

    dataset = Dataset(games=games, ground_truth=ground_truth)
    return dataset, {
        "ordering": ("T_WIN", "T_TIE", "T_LOSE"),
        "tie_closer_to_loss": True,
        "invariants": ["I5"],
    }


# ---------------------------------------------------------------------------
# Scenario 9 — Sparse early vs dense late (convergence stability)
# ---------------------------------------------------------------------------

def build_s09_sparse_vs_dense(seed: int = 42) -> tuple[Dataset, dict]:
    """T_SPARSE plays 4 games; T_DENSE plays 20+ games. Same true strength. ≥8 weeks.

    Both teams have the same attack/defense. T_DENSE accumulates enough evidence to recover
    its true ordinal more accurately than T_SPARSE. The test verifies finite ratings for both
    and measures rank error inline (no metrics module needed).
    """
    teams = [
        TeamParams(id="T_SPARSE", attack=0.2, defense=-0.1),   # true +0.3
        TeamParams(id="T_DENSE",  attack=0.2, defense=-0.1),   # true +0.3 (same)
        TeamParams(id="STRONG",   attack=0.8, defense=-0.5),   # true +1.3
        TeamParams(id="MID_A",    attack=0.1, defense=0.0),    # true +0.1
        TeamParams(id="MID_B",    attack=0.0, defense=0.1),    # true -0.1
        TeamParams(id="WEAK_A",   attack=-0.3, defense=0.4),   # true -0.7
        TeamParams(id="WEAK_B",   attack=-0.4, defense=0.5),   # true -0.9
    ]

    schedule: list[Matchup] = []

    # T_SPARSE: 4 games only (weeks 1, 3, 5, 7) — spread out so they are represented.
    sparse_schedule = [
        Matchup(week=1, team="T_SPARSE", opponent="MID_A"),
        Matchup(week=3, team="T_SPARSE", opponent="MID_B"),
        Matchup(week=5, team="T_SPARSE", opponent="WEAK_A"),
        Matchup(week=7, team="T_SPARSE", opponent="STRONG"),
    ]
    schedule.extend(sparse_schedule)

    # T_DENSE: 3 games/week × 8 weeks = 24 games.
    dense_opps = ["MID_A", "MID_B", "WEAK_A"]
    for week in range(1, 9):
        for opp in dense_opps:
            schedule.append(Matchup(week=week, team="T_DENSE", opponent=opp))

    # Background round-robin to establish context.
    context = ["STRONG", "MID_A", "MID_B", "WEAK_A", "WEAK_B"]
    for week in range(1, 9):
        for i, a in enumerate(context):
            for b in context[i + 1:]:
                schedule.append(Matchup(week=week, team=a, opponent=b))

    config = WorldConfig(teams=teams, schedule=schedule, seed=seed)
    dataset = simulate(config)
    return dataset, {
        "both_finite": ("T_SPARSE", "T_DENSE"),
        "dense_rank_closer": ("T_DENSE", "T_SPARSE"),
        "invariants": [],
    }


# ---------------------------------------------------------------------------
# Scenario 10 — Transitivity trap A>B>C>A (I8, I9)
# ---------------------------------------------------------------------------

def build_s10_transitivity_trap(seed: int = 42) -> tuple[Dataset, dict]:
    """Rock-paper-scissors: A beats B, B beats C, C beats A, all by ~2 goals. Repeated many times.

    We use exact GameRows to enforce the directed cycle rather than relying on Poisson draws to
    consistently produce the right direction. The cycle is symmetric so the true ordinal is
    ambiguous — only convergence and determinism matter (I8, I9).
    """
    ground_truth = [
        TeamParams(id="A", attack=0.0, defense=0.0),
        TeamParams(id="B", attack=0.0, defense=0.0),
        TeamParams(id="C", attack=0.0, defense=0.0),
    ]

    games: list[GameRow] = []
    # Repeat the cycle 8 times across 8 weeks (one cycle per week).
    for week in range(1, 9):
        date = f"2025-10-{week:02d}"
        # A beats B by 2.
        games.append(GameRow(week=week, date=date, time="10:45",
                             team="A", opponent="B", goals_team=3, goals_opponent=1))
        games.append(GameRow(week=week, date=date, time="10:45",
                             team="B", opponent="A", goals_team=1, goals_opponent=3))
        # B beats C by 2.
        games.append(GameRow(week=week, date=date, time="10:45",
                             team="B", opponent="C", goals_team=3, goals_opponent=1))
        games.append(GameRow(week=week, date=date, time="10:45",
                             team="C", opponent="B", goals_team=1, goals_opponent=3))
        # C beats A by 2.
        games.append(GameRow(week=week, date=date, time="10:45",
                             team="C", opponent="A", goals_team=3, goals_opponent=1))
        games.append(GameRow(week=week, date=date, time="10:45",
                             team="A", opponent="C", goals_team=1, goals_opponent=3))

    dataset = Dataset(games=games, ground_truth=ground_truth)
    return dataset, {
        "all_finite": ("A", "B", "C"),
        "invariants": ["I8", "I9"],
    }


# ---------------------------------------------------------------------------
# Scenario 11 — Momentum (I11)
# ---------------------------------------------------------------------------

def build_s11_momentum(seed: int = 42) -> tuple[Dataset, dict]:
    """RISER (rising trajectory) and FALLER (falling trajectory) start at symmetric extremes.

    The symmetry condition: week_params(RISER, 1).attack == week_params(FALLER, n_weeks).attack.
    With _TRAJ_STEP=0.05 and n_weeks=8:
      RISER.attack = -0.25 (starts weak, grows to 0.10 by week 8)
      FALLER.attack = -0.25 + 7*0.05 = 0.10 (starts at 0.10, falls to -0.25 by week 8)

    Both teams have the same season-average attack (−0.075 over 8 weeks) so their long-run
    rating would be equal without recency weighting. With recency (rho=0.2, ~3.5-week half-life),
    recent games dominate: RISER's recent weeks (when it's at its peak) pull its rating up;
    FALLER's recent weeks (when it's weak) pull its rating down.

    The OLS trend slope over the last trend_window=4 finalized weeks captures this direction.

    FIELD_1..3 are flat baselines at the season-average level providing context for tier detection.
    """
    n_weeks = 8
    # Symmetry: RISER.attack = -A; FALLER.attack = -A + (n_weeks-1)*_TRAJ_STEP
    # => both end at the same week_params value at their respective extremes.
    from generator.simulate import _TRAJ_STEP as traj_step
    A = 0.25
    faller_start = -A + (n_weeks - 1) * traj_step  # = -0.25 + 7*0.05 = 0.10

    teams = [
        TeamParams(id="RISER",   attack=-A,           defense=0.0, trajectory="rising"),
        TeamParams(id="FALLER",  attack=faller_start, defense=0.0, trajectory="falling"),
        TeamParams(id="FIELD_1", attack=0.0,          defense=0.0),
        TeamParams(id="FIELD_2", attack=0.1,          defense=0.0),
        TeamParams(id="FIELD_3", attack=-0.1,         defense=0.0),
    ]

    all_ids = ["RISER", "FALLER", "FIELD_1", "FIELD_2", "FIELD_3"]
    schedule: list[Matchup] = []
    for week in range(1, n_weeks + 1):
        for i, a in enumerate(all_ids):
            for b in all_ids[i + 1:]:
                schedule.append(Matchup(week=week, team=a, opponent=b))

    config = WorldConfig(teams=teams, schedule=schedule, seed=seed)
    dataset = simulate(config)
    return dataset, {
        "trend_signs": ("RISER", "FALLER"),
        "riser_above_faller": ("RISER", "FALLER"),
        "n_weeks": n_weeks,
        "invariants": ["I11"],
    }


# ---------------------------------------------------------------------------
# Scenario 12 — Blowout incentive (I3)
# ---------------------------------------------------------------------------

def build_s12_blowout_incentive(seed: int = 42) -> tuple[Dataset, dict]:
    """T_BLOWOUT wins 8-0 every game; T_CLOSE wins 2-1 every game. Same schedule. ≥8 weeks.

    Uses exact GameRows (as in S06) so goal margins are guaranteed. The rating gap is checked
    to be bounded: win_bonus["5+"] - win_bonus["close"] = 1.0, scaled by (1-lam) ≈ 0.95.
    """
    ground_truth = [
        TeamParams(id="T_BLOWOUT",  attack=3.0, defense=-3.0),
        TeamParams(id="T_CLOSE",    attack=0.1, defense=-0.1),
        TeamParams(id="SHARED_OPP", attack=0.0, defense=0.0),
    ]

    games: list[GameRow] = []
    for week in range(1, 9):
        date = f"2025-10-{week:02d}"
        # T_BLOWOUT: 8-0 blowout.
        games.append(GameRow(week=week, date=date, time="10:45",
                             team="T_BLOWOUT", opponent="SHARED_OPP",
                             goals_team=8, goals_opponent=0))
        games.append(GameRow(week=week, date=date, time="10:45",
                             team="SHARED_OPP", opponent="T_BLOWOUT",
                             goals_team=0, goals_opponent=8))
        # T_CLOSE: 2-1 close win.
        games.append(GameRow(week=week, date=date, time="10:45",
                             team="T_CLOSE", opponent="SHARED_OPP",
                             goals_team=2, goals_opponent=1))
        games.append(GameRow(week=week, date=date, time="10:45",
                             team="SHARED_OPP", opponent="T_CLOSE",
                             goals_team=1, goals_opponent=2))

    dataset = Dataset(games=games, ground_truth=ground_truth)
    return dataset, {
        "blowout_above_close": ("T_BLOWOUT", "T_CLOSE"),
        "gap_bounded": True,
        "invariants": ["I3"],
    }


# ---------------------------------------------------------------------------
# Scenario 13 — Tier instability / freeze window sweep (I13)
# ---------------------------------------------------------------------------

def build_s13_freeze_window(seed: int = 42) -> tuple[Dataset, dict]:
    """8 teams; T_BLIP is normally weak but dramatically outperforms in week 4 only.

    T_BLIP is a bottom-field team (true rating -1.1). In weeks 1-3 and 5-8 it loses to the
    strong/mid teams as expected. In week 4 only, T_BLIP wins against the elite teams by blowout
    (8-0 margins) — a dramatic one-week anomaly that moves its tier. After week 4 it returns
    to losing as normal.

    The blip is implemented via explicit GameRows so the goal margins are guaranteed. The
    structural (non-blip) weeks use the Poisson generator via simulate().

    The sweep test measures T_BLIP's rating swing between week-4 and week-5 cumulative solves
    under max_window ∈ {1, 2, 3, 4}. With window=1, the frozen tier in week 5 is based solely
    on T_BLIP's tier from week 4 (blip tier). With window=4, the blip-week tier is averaged
    with 3 prior normal-week tiers, so the week-5 credit T_BLIP's opponents get is less affected
    by the blip. Therefore:
      swing(window=1) > swing(window=4).

    The measurement: 'swing' is abs(T_BLIP_rating_at_w4_cumulative - T_BLIP_rating_at_w5_cumulative).
    In the week-4 cumulative solve, T_BLIP's blip games ARE included; going to week-5, its return
    to normal baseline further reduces its rating — the size of that drop depends on how the tier
    window handled the blip.
    """
    ground_truth = [
        TeamParams(id="T_BLIP",  attack=-0.5, defense=0.6),   # true -1.1
        TeamParams(id="E1",      attack=0.8,  defense=-0.6),   # true +1.4
        TeamParams(id="E2",      attack=0.7,  defense=-0.5),   # true +1.2
        TeamParams(id="M1",      attack=0.2,  defense=-0.1),   # true +0.3
        TeamParams(id="M2",      attack=0.0,  defense=0.1),    # true -0.1
        TeamParams(id="F1",      attack=-0.3, defense=0.3),    # true -0.6
        TeamParams(id="F2",      attack=-0.4, defense=0.4),    # true -0.8
        TeamParams(id="F3",      attack=-0.6, defense=0.6),    # true -1.2
    ]

    # Normal schedule (T_BLIP loses): weeks 1-3 and 5-8.
    # Elites and mids beat T_BLIP; T_BLIP beats field teams or loses.
    elite_ids = ["E1", "E2"]
    mid_ids = ["M1", "M2"]
    field_ids = ["F1", "F2", "F3"]

    games: list[GameRow] = []

    def _g(week: int, team: str, opp: str, gf: int, ga: int) -> GameRow:
        return GameRow(week=week, date=f"2025-10-{week:02d}", time="10:45",
                       team=team, opponent=opp, goals_team=gf, goals_opponent=ga)

    for week in [1, 2, 3, 5, 6, 7, 8]:
        # Elites beat T_BLIP 8-0.
        for e in elite_ids:
            games.append(_g(week, e, "T_BLIP", 8, 0))
            games.append(_g(week, "T_BLIP", e, 0, 8))
        # Mids beat T_BLIP 6-0.
        for m in mid_ids:
            games.append(_g(week, m, "T_BLIP", 6, 0))
            games.append(_g(week, "T_BLIP", m, 0, 6))
        # Elites beat mids 5-0.
        for e in elite_ids:
            for m in mid_ids:
                games.append(_g(week, e, m, 5, 0))
                games.append(_g(week, m, e, 0, 5))
        # Elites beat field 8-0.
        for e in elite_ids:
            for f in field_ids:
                games.append(_g(week, e, f, 8, 0))
                games.append(_g(week, f, e, 0, 8))
        # Mids beat field 5-0.
        for m in mid_ids:
            for f in field_ids:
                games.append(_g(week, m, f, 5, 0))
                games.append(_g(week, f, m, 0, 5))
        # Field round-robin 2-1 wins (establishes within-field ordering).
        for i, a in enumerate(field_ids):
            for b in field_ids[i + 1:]:
                games.append(_g(week, a, b, 2, 1))
                games.append(_g(week, b, a, 1, 2))

    # Week 4 — the BLIP: T_BLIP crushes the elites and mids.
    week = 4
    for e in elite_ids:
        games.append(_g(week, "T_BLIP", e, 10, 0))
        games.append(_g(week, e, "T_BLIP", 0, 10))
    for m in mid_ids:
        games.append(_g(week, "T_BLIP", m, 10, 0))
        games.append(_g(week, m, "T_BLIP", 0, 10))
    # Normal games among the other teams in week 4.
    for e in elite_ids:
        for m in mid_ids:
            games.append(_g(week, e, m, 5, 0))
            games.append(_g(week, m, e, 0, 5))
    for e in elite_ids:
        for f in field_ids:
            games.append(_g(week, e, f, 8, 0))
            games.append(_g(week, f, e, 0, 8))
    for m in mid_ids:
        for f in field_ids:
            games.append(_g(week, m, f, 5, 0))
            games.append(_g(week, f, m, 0, 5))
    for i, a in enumerate(field_ids):
        for b in field_ids[i + 1:]:
            games.append(_g(week, a, b, 2, 1))
            games.append(_g(week, b, a, 1, 2))

    dataset = Dataset(games=games, ground_truth=ground_truth)
    return dataset, {
        "blip_team": "T_BLIP",
        "blip_week": 4,
        "sweep_windows": [1, 2, 3, 4],
        "invariants": ["I13"],
    }


# ---------------------------------------------------------------------------
# Scenario 14 — Closing-schedule disparity (TASK-17, the Woodbridge/Mid-Fairfield case)
# ---------------------------------------------------------------------------

def build_s14_closing_schedule(seed: int = 42) -> tuple[Dataset, dict]:
    """HONEST loses close to elites late; PADDER pads soft wins late. HONEST is truly stronger.

    This is the deterministic synthetic mirror of the real Woodbridge/Mid-Fairfield finding
    (`docs/analysis/closing-schedule-floor-cost.md`). Two subjects with an **identical early body of
    work** diverge only in their **closing schedule**:

    - **Early (weeks 1-6):** HONEST and PADDER play the *same* mid opponents (M1-M3) with the *same*
      2-1 results — so their early credit, and therefore their early ratings, are identical. Any final
      gap comes solely from the late games.
    - **Late (weeks 7-9):** HONEST loses every game **2-3 (1-goal, "close")** to a genuine elite
      (E1-E3); PADDER beats every game **4-1** over a genuine bottom team (W1-W3). Recency weighting
      (I11) concentrates weight on exactly these late games.

    Planted truth: HONEST is the stronger team (+0.9 vs +0.3) — hanging within one goal of elites
    demonstrates more strength than beating cans. So the model **must** rank HONEST >= PADDER.

    **Why it fails on the pre-TASK-17 model (this is the bug):** per-game credit is
    `base(result) + margin + alpha*opp_rating` with `alpha < 1`. PADDER's soft win banks the 3.0 win
    floor; HONEST's elite loss is capped at `alpha*R_elite < 3`. So a cheap win out-credits an honorable
    loss, recency amplifies it, and the model ranks PADDER above HONEST — inverting the planted truth.
    TASK-17's surprise-centered credit makes the soft win ~neutral (PADDER holds station) and the elite
    loss ~neutral-or-up (HONEST holds/climbs), restoring HONEST >= PADDER.

    Background round-robin (E beats W 8-0, E beats M 5-1, M beats W 5-1, every week 1-9) establishes the
    elite/mid/weak tier spread the schedule term reads. Exact GameRows throughout (as in S03/S06/S07) so
    the outcomes are controlled, not Poisson-dependent; `seed` is accepted for signature parity but the
    dataset is fully deterministic without it (I8).
    """
    ground_truth = [
        TeamParams(id="HONEST", attack=0.5, defense=-0.4),   # true +0.9 (genuinely strong)
        TeamParams(id="PADDER", attack=0.2, defense=-0.1),   # true +0.3 (mediocre; pads weak wins)
        TeamParams(id="E1", attack=1.2, defense=-1.0),       # true +2.2 (elite)
        TeamParams(id="E2", attack=1.2, defense=-1.0),
        TeamParams(id="E3", attack=1.2, defense=-1.0),
        TeamParams(id="M1", attack=0.1, defense=0.0),        # true +0.1 (mid)
        TeamParams(id="M2", attack=0.0, defense=0.0),
        TeamParams(id="M3", attack=-0.1, defense=0.0),
        TeamParams(id="W1", attack=-1.0, defense=1.0),       # true -2.0 (bottom)
        TeamParams(id="W2", attack=-1.0, defense=1.0),
        TeamParams(id="W3", attack=-1.0, defense=1.0),
    ]

    elite_ids = ["E1", "E2", "E3"]
    mid_ids = ["M1", "M2", "M3"]
    weak_ids = ["W1", "W2", "W3"]

    games: list[GameRow] = []

    def _g(week: int, team: str, opp: str, gf: int, ga: int) -> None:
        date = f"2025-W{week:02d}"
        games.append(GameRow(week=week, date=date, time="10:45",
                             team=team, opponent=opp, goals_team=gf, goals_opponent=ga))
        games.append(GameRow(week=week, date=date, time="10:45",
                             team=opp, opponent=team, goals_team=ga, goals_opponent=gf))

    # Background weeks 1-9: establish the elite >> mid >> weak spread the schedule term reads.
    for week in range(1, 10):
        for e in elite_ids:
            for w in weak_ids:
                _g(week, e, w, 8, 0)
            for m in mid_ids:
                _g(week, e, m, 5, 1)
        for m in mid_ids:
            for w in weak_ids:
                _g(week, m, w, 5, 1)

    # Early weeks 1-6: IDENTICAL bodies of work — both subjects beat the mids 2-1.
    for week in range(1, 7):
        for subject in ("HONEST", "PADDER"):
            for m in mid_ids:
                _g(week, subject, m, 2, 1)

    # Late weeks 7-9: the closing-schedule disparity.
    for week, (e, w) in enumerate(zip(elite_ids, weak_ids), start=7):
        _g(week, "HONEST", e, 2, 3)   # close (1-goal) loss to an elite — honorable
        _g(week, "PADDER", w, 4, 1)   # comfortable win over a bottom team — padding

    dataset = Dataset(games=games, ground_truth=ground_truth)
    return dataset, {
        "honest_at_least_padder": ("HONEST", "PADDER"),
        "elite_ids": elite_ids,
        "weak_ids": weak_ids,
        "invariants": [],  # additive confirming scenario (TASK-17); not a numbered invariant
    }


# ---------------------------------------------------------------------------
# Scenario 15 — Opponent-relative goal-profile residual (TASK-18)
# ---------------------------------------------------------------------------

def build_s15_goal_profile(seed: int = 42) -> tuple[Dataset, dict]:
    """OVER over-performs each opponent's goal baseline; UNDER under-performs — same buckets.

    The deterministic confirming scenario for the goal-profile residual
    (`docs/analysis/goal-profile-residual.md`). Two subjects, OVER and UNDER, play the **same
    opponents** with results in the **same margin buckets** (every game a "close" win), so the
    TASK-17 model — which reads only `base`, the margin *bucket*, and who you played — rates them
    **byte-identically equal**. The only difference is the *exact goals*, which the new
    opponent-relative residual reads:

    - **P_OFF** (an offense test): OVER beats it **3-1**, UNDER **2-1** — same concession, but OVER
      scores **above** P_OFF's typical goals-allowed while UNDER does not (offensive residual).
    - **P_DEF** (a defense test): OVER beats it **2-0**, UNDER **2-1** — same goals-for, but OVER
      holds P_DEF **below** its typical goals-for while UNDER concedes more (defensive residual).

    Both subjects' games are 1- or 2-goal wins ("close" bucket → `win_bonus["close"] = 0`), against
    the same two opponents, in the same week — so their `_build_entries` rows are identical and the
    TASK-17 model returns ``r[OVER] == r[UNDER]`` exactly. The residual breaks the tie: OVER beats
    each opponent's own GF/GA baseline by more than UNDER, so OVER must rank strictly above.

    The opponents' baselines are set by filler games (F1/F2): P_OFF typically allows ~2.25 / scores
    ~1.5; P_DEF typically scores ~1.5 / allows ~1.75 (means over all of that opponent's games,
    computed from the Level-0 log — the sanctioned aggregate, never a rating fed back in).

    Planted truth: OVER is the genuinely stronger team (it dominates opponents' baselines), so the
    model **must** rank OVER >= UNDER. Exact GameRows throughout (as in S06/S12/S14) so the goal
    profiles are controlled, not Poisson-dependent; `seed` is accepted for signature parity but the
    dataset is fully deterministic without it (I8).
    """
    ground_truth = [
        TeamParams(id="OVER",  attack=0.4, defense=-0.4),   # genuinely strong: beats baselines
        TeamParams(id="UNDER", attack=0.1, defense=-0.1),   # weaker: meets/undershoots baselines
        TeamParams(id="P_OFF", attack=-0.1, defense=0.2),   # the offense-test opponent
        TeamParams(id="P_DEF", attack=-0.1, defense=0.2),   # the defense-test opponent
        TeamParams(id="F1",    attack=0.0, defense=0.0),
        TeamParams(id="F2",    attack=0.0, defense=0.0),
    ]

    games: list[GameRow] = []

    def _g(week: int, team: str, opp: str, gf: int, ga: int) -> None:
        date = f"2025-W{week:02d}"
        games.append(GameRow(week=week, date=date, time="10:45",
                             team=team, opponent=opp, goals_team=gf, goals_opponent=ga))
        games.append(GameRow(week=week, date=date, time="10:45",
                             team=opp, opponent=team, goals_team=ga, goals_opponent=gf))

    # Week 1 — the two subjects' games. Same opponents, same result (W), same "close" bucket,
    # so TASK-17 sees identical rows; only the exact goals (the residual) differ.
    _g(1, "OVER",  "P_OFF", 3, 1)   # scores 3 (above P_OFF's ~2.25 allowed) — offensive over-perform
    _g(1, "UNDER", "P_OFF", 2, 1)   # scores 2 (below baseline), same concession
    _g(1, "OVER",  "P_DEF", 2, 0)   # holds P_DEF to 0 (below its ~1.5 scored) — defensive over-perform
    _g(1, "UNDER", "P_DEF", 2, 1)   # concedes 1, same goals-for

    # Week 2 — filler games that set the opponents' GF/GA baselines (and anchor the league).
    _g(2, "F1", "P_OFF", 2, 2)
    _g(2, "F2", "P_OFF", 2, 2)
    _g(2, "P_DEF", "F1", 2, 2)
    _g(2, "P_DEF", "F2", 3, 1)
    _g(2, "F1", "F2", 1, 1)

    dataset = Dataset(games=games, ground_truth=ground_truth)
    return dataset, {
        "over_at_least_under": ("OVER", "UNDER"),
        "profile_opponents": ("P_OFF", "P_DEF"),
        "invariants": [],  # additive confirming scenario (TASK-18); not a numbered invariant
    }
