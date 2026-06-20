"""The synthetic generator (brief §6, §8).

Turns a seeded world config (team true strengths + a schedule) into Level-0 game rows plus a
hidden ground-truth key. Emits ONLY Level-0 rows; Levels 1-3 are the harness's job. Every
dataset is fully reproducible from (config, seed) — determinism is sacred (I8).
"""

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from core.game import GameRow
from generator.world import draw_scoreline, expected_goals

# League calendar anchor: week 1 begins here; each week is 7 days later. Deterministic, no "now".
_SEASON_START = date(2025, 9, 29)  # a Monday
_DEFAULT_TIME = "10:45"

# Trajectory magnitude constants.  Per-week drift on attack for rising/falling; one-week
# attack+defense boost magnitude for blip@wN.  Both chosen so the signal is comfortably above
# statistical noise in 300-rep tests while remaining plausible as a within-season swing.
_TRAJ_STEP = 0.05   # attack drift per week-beyond-1 for rising/falling
_TRAJ_BLIP = 0.40   # one-week attack boost (defence tightens by the same amount) for blip@wN


@dataclass(frozen=True)
class TeamParams:
    """A team's hidden true strength. `defense` is defensive *weakness* (higher = concedes more),
    so the brief's true rating = attack - defense."""

    id: str
    attack: float
    defense: float
    tier: int | None = None
    trajectory: str = "flat"

    @property
    def rating(self) -> float:
        return self.attack - self.defense


@dataclass(frozen=True)
class Matchup:
    """One scheduled game: who plays whom, in which week. Goals are drawn by the generator."""

    week: int
    team: str
    opponent: str


@dataclass(frozen=True)
class WorldConfig:
    teams: list[TeamParams]
    schedule: list[Matchup]
    seed: int
    mu: float = math.log(3.0)  # league baseline scoring level (~3 goals between neutral teams)


@dataclass(frozen=True)
class Dataset:
    games: list[GameRow]
    ground_truth: list[TeamParams] = field(default_factory=list)


def _week_date(week: int) -> str:
    return (_SEASON_START + timedelta(weeks=week - 1)).isoformat()


def week_params(team: TeamParams, week: int) -> tuple[float, float]:
    """Return (attack, defense) for *team* at *week*, applying its trajectory.

    Week 1 is always the team's raw baseline.  Exported so the harness can reconstruct
    per-week true ratings for I11 (momentum recovery) scoring without re-running the generator.

    Trajectories
    ------------
    flat      — unchanged every week (default; preserves I8 — byte-identical to prior behaviour).
    rising    — attack grows by _TRAJ_STEP each week beyond 1; defense unchanged.
    falling   — attack shrinks by _TRAJ_STEP each week beyond 1; defense unchanged.
    blip@wN   — attack boosted by _TRAJ_BLIP and defense tightened by _TRAJ_BLIP only in week N.
    """
    traj = team.trajectory
    if traj == "flat":
        return team.attack, team.defense
    if traj == "rising":
        return team.attack + _TRAJ_STEP * (week - 1), team.defense
    if traj == "falling":
        return team.attack - _TRAJ_STEP * (week - 1), team.defense
    if traj.startswith("blip@w"):
        blip_week = int(traj[len("blip@w"):])
        if week == blip_week:
            # Temporarily stronger on both ends: scores more, concedes less.
            return team.attack + _TRAJ_BLIP, team.defense - _TRAJ_BLIP
        return team.attack, team.defense
    raise ValueError(f"Unknown trajectory {traj!r} for team {team.id!r}")


def simulate(config: WorldConfig) -> Dataset:
    rng = np.random.default_rng(config.seed)
    by_id = {t.id: t for t in config.teams}

    games: list[GameRow] = []
    for m in config.schedule:
        p, q = by_id[m.team], by_id[m.opponent]
        p_atk, p_def = week_params(p, m.week)
        q_atk, q_def = week_params(q, m.week)
        lam_team = expected_goals(p_atk, q_def, config.mu)
        lam_opp = expected_goals(q_atk, p_def, config.mu)
        g_team, g_opp = draw_scoreline(rng, lam_team, lam_opp)
        games.append(
            GameRow(
                week=m.week,
                date=_week_date(m.week),
                time=_DEFAULT_TIME,
                team=m.team,
                opponent=m.opponent,
                goals_team=g_team,
                goals_opponent=g_opp,
            )
        )
    return Dataset(games=games, ground_truth=list(config.teams))
