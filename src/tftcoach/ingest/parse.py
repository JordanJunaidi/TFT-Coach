"""Validate raw match-v1 payloads into typed models.

Only the fields the project uses are declared; pydantic ignores the rest, so new fields
Riot adds don't break parsing, and a missing required field fails loudly here instead of
surfacing later as a NULL in the database.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

RANKED_QUEUE_ID = 1100


class Trait(BaseModel):
    name: str
    num_units: int
    style: int
    tier_current: int
    tier_total: int


class Unit(BaseModel):
    character_id: str
    tier: int  # star level
    rarity: int
    items: list[str] = Field(default_factory=list, alias="itemNames")


class Participant(BaseModel):
    puuid: str
    placement: int
    level: int
    gold_left: int
    last_round: int
    time_eliminated: float
    players_eliminated: int
    total_damage_to_players: int
    game_name: str | None = Field(default=None, alias="riotIdGameName")
    tag_line: str | None = Field(default=None, alias="riotIdTagline")
    traits: list[Trait] = Field(default_factory=list)
    units: list[Unit] = Field(default_factory=list)


class MatchInfo(BaseModel):
    game_datetime: int  # epoch milliseconds
    game_length: float
    queue_id: int
    tft_set_number: int
    participants: list[Participant]

    @property
    def played_at(self) -> datetime:
        return datetime.fromtimestamp(self.game_datetime / 1000, tz=UTC)


class MatchMetadata(BaseModel):
    match_id: str


class Match(BaseModel):
    metadata: MatchMetadata
    info: MatchInfo


def parse_match(payload: dict[str, Any]) -> Match:
    return Match.model_validate(payload)
