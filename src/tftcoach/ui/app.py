"""Streamlit chat UI for the TFT coach.

Run: uv run streamlit run src/tftcoach/ui/app.py
"""

import streamlit as st

from tftcoach.agent import session as coach_session
from tftcoach.agent.loop import AgentResult, tool_result_preview
from tftcoach.config import get_settings
from tftcoach.openai_compat import LLMAPIError

st.set_page_config(page_title="TFT Coach", page_icon="🎲")


@st.cache_resource(show_spinner=False)
def get_session(riot_id: str) -> coach_session.CoachSession:
    return coach_session.open_session(riot_id)


def render_details(result: AgentResult) -> None:
    """Warnings, sources, and tool calls under an answer."""
    if not result.grounding.ok:
        st.warning(
            "These numbers don't appear in the data the coach looked up, so treat them with "
            f"caution: {', '.join(result.grounding.unsupported)}"
        )
    if result.unknown_citations:
        st.warning(
            f"Cited patch notes that weren't retrieved: {', '.join(result.unknown_citations)}"
        )
    sources = result.cited_sources()
    if sources:
        with st.expander(f"Sources ({len(sources)})"):
            for key, text in sources.items():
                st.markdown(f"**[{key}]**")
                st.text(text)
    if result.tool_calls:
        with st.expander(f"Tool calls ({len(result.tool_calls)})"):
            for call in result.tool_calls:
                st.markdown(f"`{call.name}({call.arguments})`")
                st.code(tool_result_preview(call, limit=1500), language="json")


def main() -> None:
    settings = get_settings()
    with st.sidebar:
        st.header("TFT Coach")
        riot_id = st.text_input("Riot ID", value=settings.tft_riot_id or "", placeholder="Name#TAG")
        st.caption(f"Model: {settings.llm_model}")
        if st.button("Clear chat"):
            st.session_state.turns = []

    st.title("TFT Coach")
    st.caption("Answers come from your ingested matches and official patch notes.")
    if not riot_id:
        st.info("Enter your Riot ID in the sidebar to start.")
        return

    try:
        coach = get_session(riot_id)
    except Exception as exc:  # setup problems (unknown player, missing key) shown, not raised
        st.error(f"Couldn't start the coach: {exc}")
        return

    turns: list[tuple[str, AgentResult]] = st.session_state.setdefault("turns", [])
    for question, result in turns:
        st.chat_message("user").write(question)
        with st.chat_message("assistant"):
            st.markdown(result.answer)
            render_details(result)

    question = st.chat_input("Ask about your games or the patch")
    if not question:
        return
    st.chat_message("user").write(question)
    # Earlier turns go back as plain text; their tool calls aren't replayed.
    history = [
        message
        for q, r in turns
        for message in ({"role": "user", "content": q}, {"role": "assistant", "content": r.answer})
    ]
    with st.chat_message("assistant"):
        try:
            with st.spinner("Looking at your games and the patch notes..."):
                result = coach.ask(question, history)
        except LLMAPIError as exc:
            st.error(f"The language model request failed: {exc}")
            return
        st.markdown(result.answer)
        render_details(result)
    turns.append((question, result))


main()
