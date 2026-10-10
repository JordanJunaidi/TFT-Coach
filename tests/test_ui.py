"""Render the Streamlit app with a fake coach session (no browser, no API calls)."""

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from tftcoach.agent import session as coach_session
from tftcoach.agent.grounding import GroundingReport
from tftcoach.agent.loop import AgentResult, ToolCallRecord
from tftcoach.config import get_settings

APP = str(Path(__file__).parents[1] / "src" / "tftcoach" / "ui" / "app.py")

SEARCH_RESULT = '{"results": [{"id": "18.4-20", "text": "Juggernaut Durability: 20/33/45%"}]}'


class FakeSession:
    def __init__(self, result: AgentResult) -> None:
        self.result = result
        self.questions: list[tuple[str, list]] = []

    def ask(self, question: str, history=None) -> AgentResult:
        self.questions.append((question, history))
        return self.result


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch):
    def make(result: AgentResult) -> tuple[AppTest, FakeSession]:
        fake = FakeSession(result)
        monkeypatch.setenv("RIOT_API_KEY", "test")
        monkeypatch.setenv("TFT_RIOT_ID", "monk#monke")
        monkeypatch.setattr(coach_session, "open_session", lambda riot_id: fake)
        get_settings.cache_clear()
        st.cache_resource.clear()
        return AppTest.from_file(APP, default_timeout=10), fake

    yield make
    get_settings.cache_clear()


def test_answer_with_sources_and_no_warnings(app) -> None:
    result = AgentResult(
        answer="Juggernaut was nerfed [18.4-20].",
        tool_calls=[ToolCallRecord("search_patch_notes", '{"query": "Juggernaut"}', SEARCH_RESULT)],
        grounding=GroundingReport(numbers_checked=0, unsupported=[]),
        citations=["18.4-20"],
    )
    at, fake = app(result)
    at.run()
    at.chat_input[0].set_value("Was Juggernaut nerfed?").run()

    assert not at.exception
    assert fake.questions == [("Was Juggernaut nerfed?", [])]
    assert any("Juggernaut was nerfed" in m.value for m in at.markdown)
    assert [e.label for e in at.expander] == ["Sources (1)", "Tool calls (1)"]
    assert not at.warning


def test_unsupported_numbers_show_a_warning(app) -> None:
    result = AgentResult(
        answer="You win 27% of games.",
        grounding=GroundingReport(numbers_checked=1, unsupported=["27"]),
    )
    at, _ = app(result)
    at.run()
    at.chat_input[0].set_value("How often do I win?").run()

    assert "27" in at.warning[0].value


def test_second_question_sends_history(app) -> None:
    at, fake = app(AgentResult(answer="First answer."))
    at.run()
    at.chat_input[0].set_value("one").run()
    at.chat_input[0].set_value("two").run()

    assert fake.questions[1] == (
        "two",
        [{"role": "user", "content": "one"}, {"role": "assistant", "content": "First answer."}],
    )
