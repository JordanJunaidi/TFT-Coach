"""Check that every number in an answer came from tool output (CLAUDE.md rule).

A number in the answer counts as grounded if some number in the sources (tool results,
the question, the system prompt's facts) rounds to it at the answer's own precision, so
"4.8" is supported by 4.82 and "36%" by 36.4. Fractions also match as percentages
(0.36 -> "36%"). Citation ids like [18.4-20] are ignored.
"""

import re
from dataclasses import dataclass

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
CITATION = re.compile(r"\[\d+\.\d+-\d+\]")
# Game-rule numbers that need no source: star levels, "top 4", 8 players per lobby.
ALWAYS_ALLOWED = {0.0, 1.0, 2.0, 3.0, 4.0, 8.0}


@dataclass(frozen=True)
class GroundingReport:
    numbers_checked: int
    unsupported: list[str]

    @property
    def ok(self) -> bool:
        return not self.unsupported


def extract_numbers(text: str) -> list[str]:
    return [m.group().rstrip(",") for m in NUMBER.finditer(CITATION.sub(" ", text))]


def _value(token: str) -> float:
    return float(token.replace(",", ""))


def _decimals(token: str) -> int:
    return len(token.split(".")[1]) if "." in token else 0


def is_supported(token: str, sources: set[float]) -> bool:
    value, places = _value(token), _decimals(token)
    if value in ALWAYS_ALLOWED:
        return True
    return any(round(s, places) == value or round(s * 100, places) == value for s in sources)


def check_grounding(answer: str, source_texts: list[str]) -> GroundingReport:
    sources = {_value(t) for text in source_texts for t in extract_numbers(text)}
    tokens = extract_numbers(answer)
    unsupported = [t for t in tokens if not is_supported(t, sources)]
    return GroundingReport(
        numbers_checked=len(tokens), unsupported=list(dict.fromkeys(unsupported))
    )
