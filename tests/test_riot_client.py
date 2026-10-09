import httpx
import pytest

from tftcoach.riot.client import RiotAPIError, RiotClient, parse_riot_id

API_KEY = "RGAPI-test-key"


def make_client(handler, sleeps: list[float] | None = None) -> RiotClient:
    recorded = sleeps if sleeps is not None else []
    return RiotClient(
        API_KEY,
        region="americas",
        transport=httpx.MockTransport(handler),
        sleep=recorded.append,
    )


@pytest.mark.parametrize(
    ("riot_id", "expected"),
    [
        ("monk#monke", ("monk", "monke")),
        ("Name With Spaces#NA1", ("Name With Spaces", "NA1")),
        ("weird#name#TAG", ("weird#name", "TAG")),
    ],
)
def test_parse_riot_id(riot_id: str, expected: tuple[str, str]) -> None:
    assert parse_riot_id(riot_id) == expected


@pytest.mark.parametrize("bad", ["noTag", "#TAG", "Name#", ""])
def test_parse_riot_id_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_riot_id(bad)


def test_get_puuid_sends_auth_header_to_regional_host() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "americas.api.riotgames.com"
        assert request.url.path == "/riot/account/v1/accounts/by-riot-id/monk/monke"
        assert request.headers["X-Riot-Token"] == API_KEY
        return httpx.Response(200, json={"puuid": "abc123", "gameName": "monk"})

    with make_client(handler) as client:
        assert client.get_puuid("monk", "monke") == "abc123"


def test_get_match_ids_passes_paging_params() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tft/match/v1/matches/by-puuid/abc123/ids"
        assert request.url.params["count"] == "20"
        assert request.url.params["start"] == "0"
        return httpx.Response(200, json=["NA1_1", "NA1_2"])

    with make_client(handler) as client:
        assert client.get_match_ids("abc123") == ["NA1_1", "NA1_2"]


def test_retries_on_429_respecting_retry_after() -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"metadata": {"match_id": "NA1_1"}}),
        ]
    )
    sleeps: list[float] = []

    with make_client(lambda request: next(responses), sleeps) as client:
        match = client.get_match("NA1_1")

    assert match["metadata"]["match_id"] == "NA1_1"
    assert sleeps == [2.0]


def test_gives_up_after_max_retries() -> None:
    sleeps: list[float] = []
    with make_client(lambda request: httpx.Response(429), sleeps) as client:
        with pytest.raises(RiotAPIError) as exc_info:
            client.get_match("NA1_1")

    assert exc_info.value.status_code == 429
    assert len(sleeps) == 3


def test_error_message_does_not_leak_api_key() -> None:
    with make_client(lambda request: httpx.Response(403, text="Forbidden")) as client:
        with pytest.raises(RiotAPIError) as exc_info:
            client.get_puuid("monk", "monke")

    assert exc_info.value.status_code == 403
    assert API_KEY not in str(exc_info.value)
