from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from tftcoach.ingest.parse import RANKED_QUEUE_ID, parse_match


def test_parses_fixture_match(match_payload: dict[str, Any]) -> None:
    match = parse_match(match_payload)

    assert match.metadata.match_id == "NA1_5656832942"
    assert match.info.tft_set_number == 18
    assert match.info.queue_id == RANKED_QUEUE_ID
    assert match.info.played_at == datetime(2026, 10, 9, 3, 55, 58, 744000, tzinfo=UTC)
    assert sorted(p.placement for p in match.info.participants) == list(range(1, 9))


def test_maps_riot_field_names(match_payload: dict[str, Any]) -> None:
    participant = parse_match(match_payload).info.participants[0]

    assert participant.game_name == match_payload["info"]["participants"][0]["riotIdGameName"]
    assert any(unit.items for unit in participant.units)  # from "itemNames"
    assert all(1 <= unit.tier <= 4 for unit in participant.units)


def test_missing_required_field_fails_loudly(match_payload: dict[str, Any]) -> None:
    del match_payload["info"]["participants"][0]["placement"]
    with pytest.raises(ValidationError):
        parse_match(match_payload)
