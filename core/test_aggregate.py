"""Level-1 aggregate tests (brief §5).

Level 1 is pure arithmetic on Level-0 rows: gamesPlayed, gf, ga, goalDiff, w, l, t, winPct.
The hard lesson from the scrape: a team appears as `team` in some rows and `opponent` in
others, so the ONLY correct record comes from folding the game log with the perspective
flipped when the team is the opponent. Never trust a stored summary.
"""


from core.aggregate import TeamAggregate, aggregate_all, aggregate_team
from core.game import GameRow


def row(team, opp, gf, ga, week=1):
    return GameRow(week=week, date="2025-10-03", time="10:45",
                   team=team, opponent=opp, goals_team=gf, goals_opponent=ga)


# A log where T01 is `team` twice and `opponent` once — the perspective-flip case.
LOG = [
    row("T01", "T02", 5, 2),  # T01 win;  T02 loss
    row("T01", "T03", 1, 1),  # T01 tie;  T03 tie
    row("T04", "T01", 4, 3),  # T01 loss (as opponent); T04 win
]


def test_aggregate_counts_from_full_log():
    """T01's record folds all three rows, flipping the row where it is the opponent."""
    agg = aggregate_team(LOG, "T01")
    assert agg == TeamAggregate(
        team="T01",
        games_played=3,
        gf=9,          # 5 + 1 + 3(as opponent)
        ga=7,          # 2 + 1 + 4(as opponent)
        goal_diff=2,
        w=1,
        l=1,
        t=1,
        win_pct=0.5,   # (1 win + 0.5*1 tie) / 3
    )


def test_perspective_flips_when_team_is_opponent():
    """T04 only appears on the opponent side of one row; its 4-3 must read as a win."""
    agg = aggregate_team(LOG, "T04")
    assert (agg.gf, agg.ga, agg.w, agg.l, agg.t) == (4, 3, 1, 0, 0)


def test_win_pct_counts_ties_as_half():
    """Conventional winning percentage: (w + 0.5*t) / gamesPlayed."""
    agg = aggregate_team(LOG, "T03")  # one tie only
    assert agg.games_played == 1
    assert agg.win_pct == 0.5


def test_team_with_no_games_is_empty_not_an_error():
    agg = aggregate_team(LOG, "T99")
    assert (agg.games_played, agg.gf, agg.ga, agg.win_pct) == (0, 0, 0, 0.0)


def test_aggregate_is_order_independent():
    """Determinism (I8): shuffling the log does not change any team's aggregate."""
    forward = aggregate_team(LOG, "T01")
    backward = aggregate_team(list(reversed(LOG)), "T01")
    assert forward == backward


def test_aggregate_all_covers_every_team_in_the_log():
    everyone = aggregate_all(LOG)
    assert set(everyone) == {"T01", "T02", "T03", "T04"}
    assert everyone["T02"].l == 1 and everyone["T02"].w == 0
