"""Thin client for the Riot account and TFT match endpoints."""

import time
from collections.abc import Callable
from typing import Any

import httpx

DEFAULT_TIMEOUT = 10.0
MAX_RETRIES = 3
DEFAULT_RETRY_AFTER = 1.0


class RiotAPIError(Exception):
    """Raised when the Riot API returns a non-success response."""

    def __init__(self, status_code: int, url: str, body: str) -> None:
        super().__init__(f"Riot API returned {status_code} for {url}: {body[:200]}")
        self.status_code = status_code


def parse_riot_id(riot_id: str) -> tuple[str, str]:
    """Split "Name#TAG" into (game_name, tag_line).

    Splits on the last '#' since game names may contain spaces and other characters.
    """
    game_name, sep, tag_line = riot_id.rpartition("#")
    if not sep or not game_name or not tag_line:
        raise ValueError(f"Riot ID must look like 'Name#TAG', got {riot_id!r}")
    return game_name, tag_line


class RiotClient:
    """Wraps a single httpx.Client with auth, regional routing, and 429 backoff."""

    def __init__(
        self,
        api_key: str,
        region: str = "americas",
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = httpx.Client(
            base_url=f"https://{region}.api.riotgames.com",
            headers={"X-Riot-Token": api_key},
            timeout=DEFAULT_TIMEOUT,
            transport=transport,
        )
        self._sleep = sleep

    def __enter__(self) -> "RiotClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        for attempt in range(MAX_RETRIES + 1):
            response = self._http.get(path, params=params)
            if response.status_code == 429 and attempt < MAX_RETRIES:
                retry_after = response.headers.get("Retry-After")
                self._sleep(float(retry_after) if retry_after else DEFAULT_RETRY_AFTER)
                continue
            if response.is_error:
                # Use the path rather than the full request so headers (the API key) never
                # end up in an exception message.
                raise RiotAPIError(response.status_code, path, response.text)
            return response.json()
        raise AssertionError("unreachable")

    def get_puuid(self, game_name: str, tag_line: str) -> str:
        account = self._get(f"/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}")
        return account["puuid"]

    def get_match_ids(self, puuid: str, count: int = 20, start: int = 0) -> list[str]:
        return self._get(
            f"/tft/match/v1/matches/by-puuid/{puuid}/ids",
            params={"start": start, "count": count},
        )

    def get_match(self, match_id: str) -> dict[str, Any]:
        return self._get(f"/tft/match/v1/matches/{match_id}")
