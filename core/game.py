"""Level-0 — the observed game record (brief §5).

One row per game. These are the ONLY true inputs to any rating model. The outcome
(W/L/T) is *inferred* from the two goal numbers, never stored as a primary field,
and there is no concept of home/away — `team` and `opponent` are just the two peers.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GameRow:
    """An immutable Level-0 observation. Field set is the locked data contract."""

    week: int
    date: str
    time: str
    team: str
    opponent: str
    goals_team: int
    goals_opponent: int

    @property
    def outcome(self) -> str:
        """W / L / T, inferred from goals. Never a stored field."""
        if self.goals_team > self.goals_opponent:
            return "W"
        if self.goals_team < self.goals_opponent:
            return "L"
        return "T"
