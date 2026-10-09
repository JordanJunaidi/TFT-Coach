import json

from tests.conftest import FIXTURES
from tftcoach.db.static_data import extract_names


def test_extracts_units_traits_and_items() -> None:
    data = json.loads((FIXTURES / "cdragon_tft_sample.json").read_text())
    names = {api: (kind, name) for api, kind, name, _, _ in extract_names(data)}

    assert names["DA_18_Diana"] == ("unit", "Diana")
    assert names["DA_18_Adaptor"] == ("trait", "Adaptor")
    assert names["DA_InfinityEdge"] == ("item", "Infinity Edge")


def test_first_set_entry_wins_for_duplicates() -> None:
    data = {
        "setData": [
            {"number": 18, "champions": [{"apiName": "X_Unit", "name": "Standard"}]},
            {"number": 18, "champions": [{"apiName": "X_Unit", "name": "Double Up"}]},
        ],
        "items": [],
    }
    assert extract_names(data) == [("X_Unit", "unit", "Standard", 18, None)]
