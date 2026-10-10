"""Download official TFT patch notes and convert them to Markdown.

The Markdown keeps the page's structure, which the chunker relies on:
`##` for top-level sections, `###` for subsections, and nested `- ` lists for changes.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import httpx

NOTES_URL = (
    "https://teamfighttactics.leagueoflegends.com/en-us/news/game-updates/"
    "teamfight-tactics-patch-{slug}/"
)
NOTES_DIR = Path("patch_notes")

# Content we never want as text. Void tags (img, br, ...) are handled separately because
# they have no end tag; counting them here would skip the rest of the page.
SKIP_TAGS = {"script", "style", "noscript", "svg", "video", "iframe", "button", "figure"}
VOID_TAGS = {"br", "hr", "img", "input", "meta", "link", "source", "wbr", "area", "col"}
BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "blockquote", "tr"}
CONTAINER_ID = "patch-notes-container"


def notes_url(patch: str) -> str:
    return NOTES_URL.format(slug=patch.replace(".", "-"))


class _NotesParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0  # element depth inside the notes container; 0 = outside
        self.skip_depth = 0
        self.list_depth = 0
        self.lines: list[str] = []
        self.buf: list[str] = []
        self.prefix = ""

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if text:
            self.lines.append(self.prefix + text)
        self.buf = []
        self.prefix = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.depth == 0:
            if dict(attrs).get("id") == CONTAINER_ID:
                self.depth = 1
            return
        if tag in VOID_TAGS:
            if tag == "br" and not self.skip_depth:
                self._flush()
            return
        self.depth += 1
        if tag in SKIP_TAGS or self.skip_depth:
            self.skip_depth += 1
            return
        if tag in BLOCK_TAGS:
            self._flush()
        if tag in ("ul", "ol"):
            self._flush()
            self.list_depth += 1
        elif tag == "li":
            self.prefix = "  " * max(self.list_depth - 1, 0) + "- "
        elif tag == "h2":
            self.lines.append("")
            self.prefix = "## "
        elif tag in ("h3", "h4"):
            self.lines.append("")
            self.prefix = "### "

    def handle_endtag(self, tag: str) -> None:
        if self.depth == 0 or tag in VOID_TAGS:
            return
        if self.skip_depth:
            self.skip_depth -= 1
        else:
            if tag in BLOCK_TAGS:
                self._flush()
            if tag in ("ul", "ol"):
                self.list_depth = max(self.list_depth - 1, 0)
        self.depth -= 1
        if self.depth == 0:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self.depth and not self.skip_depth:
            self.buf.append(data)


def html_to_markdown(html: str, patch: str) -> str:
    parser = _NotesParser()
    parser.feed(html)
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(parser.lines)).strip()
    if not body:
        raise ValueError(f"No patch-notes content found for {patch} (page layout changed?)")
    return f"# Teamfight Tactics patch {patch}\n\nSource: {notes_url(patch)}\n\n{body}\n"


def fetch_notes(patch: str, out_dir: Path = NOTES_DIR) -> Path:
    response = httpx.get(
        notes_url(patch),
        headers={"User-Agent": "tftcoach/0.1"},
        timeout=30.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{patch}.md"
    path.write_text(html_to_markdown(response.text, patch), encoding="utf-8")
    return path
