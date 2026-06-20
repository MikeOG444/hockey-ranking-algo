"""Level-1 — team aggregates (brief §5).

Pure arithmetic on Level-0 rows. The only honest record of a team comes from folding the
game log itself: a team is `team` in some rows and `opponent` in others, so we flip the
perspective when it appears as the opponent. We never read a stored summary — those were
unreliable in the scrape; totals computed from the log were exact.
"""

from dataclasses import dataclass
from collections.abc import Iterable

from core.game import GameRow


@dataclass(frozen=True)
class TeamAggregate:
    """A team's record, counted deterministically from the game log."""

    team: str
    games_played: int
    gf: int
    ga: int
    goal_diff: int
    w: int
    l: int
    t: int
    win_pct: float


def _team_view(g: GameRow, team: str) -> tuple[int, int, str] | None:
    """This game from `team`'s perspective: (goals_for, goals_against, outcome).

    Returns None if `team` did not play in this game. Outcome is flipped when the team
    is the opponent (a W for one side is an L for the other; a T stays a T).
    """
    if g.team == team:
        return g.goals_team, g.goals_opponent, g.outcome
    if g.opponent == team:
        flip = {"W": "L", "L": "W", "T": "T"}
        return g.goals_opponent, g.goals_team, flip[g.outcome]
    return None


def aggregate_team(games: Iterable[GameRow], team: str) -> TeamAggregate:
    gf = ga = w = l = t = 0
    games_played = 0
    for g in games:
        view = _team_view(g, team)
        if view is None:
            continue
        for_goals, against_goals, outcome = view
        games_played += 1
        gf += for_goals
        ga += against_goals
        if outcome == "W":
            w += 1
        elif outcome == "L":
            l += 1
        else:
            t += 1
    win_pct = (w + 0.5 * t) / games_played if games_played else 0.0
    return TeamAggregate(
        team=team,
        games_played=games_played,
        gf=gf,
        ga=ga,
        goal_diff=gf - ga,
        w=w,
        l=l,
        t=t,
        win_pct=win_pct,
    )


def aggregate_all(games: Iterable[GameRow]) -> dict[str, TeamAggregate]:
    """Aggregate every team that appears anywhere in the log."""
    games = list(games)
    teams: set[str] = set()
    for g in games:
        teams.add(g.team)
        teams.add(g.opponent)
    # Sorted for deterministic construction order (I8); dict order is then stable.
    return {team: aggregate_team(games, team) for team in sorted(teams)}
