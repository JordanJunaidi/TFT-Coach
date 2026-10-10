"""Wire up settings, database, model, and tools for one player (used by the CLI and UI)."""

from dataclasses import dataclass

import psycopg

from tftcoach.agent.llm import APIChatModel, Message
from tftcoach.agent.loop import AgentResult, run_agent, system_prompt
from tftcoach.agent.tools import ToolContext
from tftcoach.analysis.queries import CURRENT_SET, puuid_for_riot_id, resolve_set
from tftcoach.config import get_settings
from tftcoach.db.core import connect
from tftcoach.openai_compat import OpenAICompatClient
from tftcoach.rag.embed import APIEmbedder
from tftcoach.rag.search import indexed_patches
from tftcoach.riot.client import parse_riot_id


def current_patch(conn: psycopg.Connection) -> str:
    row = conn.execute(
        "SELECT patch FROM patches WHERE start_date <= current_date "
        "ORDER BY start_date DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else "unknown"


@dataclass
class CoachSession:
    conn: psycopg.Connection
    client: OpenAICompatClient
    ctx: ToolContext
    model: APIChatModel
    system: str

    def ask(self, question: str, history: list[Message] | None = None) -> AgentResult:
        return run_agent(question, self.ctx, self.model, self.system, history)

    def close(self) -> None:
        self.client.close()
        self.conn.close()


def open_session(riot_id: str | None = None) -> CoachSession:
    settings = get_settings()
    riot_id = riot_id or settings.tft_riot_id
    if not riot_id:
        raise ValueError("No Riot ID given and TFT_RIOT_ID is not set in .env")
    if settings.llm_api_key is None:
        raise ValueError("LLM_API_KEY is not set in .env")

    conn = connect(settings.database_url)
    puuid = puuid_for_riot_id(conn, *parse_riot_id(riot_id))
    client = OpenAICompatClient(settings.llm_base_url, settings.llm_api_key.get_secret_value())
    embedder = APIEmbedder(client, settings.embedding_model, settings.embedding_dims)
    system = system_prompt(
        set_number=resolve_set(conn, puuid, CURRENT_SET),
        current_patch=current_patch(conn),
        note_patches=indexed_patches(conn),
    )
    conn.commit()  # end the setup read transaction; tool calls run in their own
    return CoachSession(
        conn=conn,
        client=client,
        ctx=ToolContext(conn=conn, puuid=puuid, embedder=embedder),
        model=APIChatModel(client, settings.llm_model),
        system=system,
    )
