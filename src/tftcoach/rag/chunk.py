"""Split patch-notes Markdown into retrieval chunks.

Chunks follow the notes' own structure instead of a fixed size:

- Entity sections (Traits, Units, Items...) list each changed thing as a top-level bullet
  with nested details. Each such bullet becomes its own chunk, together with the
  designer's "Name: why we changed it" paragraph. "Was Juggernaut nerfed?" then
  retrieves just the Juggernaut change instead of every trait in the patch.
- Flat sections (bug fixes, most mid-patch updates) are kept whole, split on line
  boundaries only when long.

Every chunk carries its patch, section path, and mid-patch label, both as metadata and in
its text, so the embedding and the LLM both see where it came from.
"""

import hashlib
import re
from dataclasses import dataclass, field

MAX_CHUNK_CHARS = 1800

# Top-level sections with nothing useful for coaching.
SKIP_SECTIONS = re.compile(
    r"COSMETIC|MINIMUM SPECS|PERFORMANCE|VICTORIOUS|LOADOUT|PATCH HIGHLIGHTS", re.IGNORECASE
)
MONTHS = "JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER"
DATE_HEADING = re.compile(rf"^({MONTHS})\b", re.IGNORECASE)
# "Juggernaut: Juggernaut (6) is too easy to hit..." -> designer note about "Juggernaut".
NOTE_PREFIX = re.compile(r"^([^:]{1,60}):\s")


@dataclass
class Chunk:
    key: str
    patch: str
    section: str
    entity: str | None
    midpatch: str | None
    body: str

    @property
    def content(self) -> str:
        """Text that is embedded, retrieved, and shown to the LLM."""
        where = f"Patch {self.patch}"
        if self.midpatch:
            where += f" (mid-patch update, {self.midpatch.title()})"
        return f"{where}\nSection: {self.section}\n\n{self.body}"

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


@dataclass
class _Item:
    lines: list[str] = field(default_factory=list)

    @property
    def has_children(self) -> bool:
        return len(self.lines) > 1

    @property
    def name(self) -> str:
        return self.lines[0].removeprefix("- ").strip()


@dataclass
class _Block:
    section: str
    midpatch: str | None
    lines: list[str] = field(default_factory=list)


def _pretty(heading: str) -> str:
    return heading.title() if heading.isupper() else heading


def _base_name(name: str) -> str:
    """'Executioner (3/4)' -> 'executioner'; 'Riftbeast (7) Stats: ...' -> 'riftbeast'."""
    name = name.split(":")[0]
    return re.sub(r"\s*\(.*?\)", "", name).strip().lower()


def _blocks(markdown: str) -> list[_Block]:
    """Group lines under their (## section, ### subsection), tracking mid-patch updates."""
    blocks: list[_Block] = []
    h2 = "Intro"
    h3: str | None = None
    skipping = False
    in_midpatch = False
    midpatch: str | None = None
    current = _Block(section=h2, midpatch=None)

    def start(section: str) -> None:
        nonlocal current
        if current.lines:
            blocks.append(current)
        current = _Block(section=section, midpatch=midpatch)

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("# ") or line.startswith("Source: "):
            continue
        if line.startswith("## "):
            h2, h3 = line[3:].strip(), None
            skipping = bool(SKIP_SECTIONS.search(h2))
            in_midpatch = "MID-PATCH" in h2.upper()
            midpatch = None
            start(_pretty(h2))
            continue
        if skipping:
            continue
        if line.startswith("### "):
            h3 = line[4:].strip()
            if in_midpatch and DATE_HEADING.match(h3):
                midpatch = h3
            start(f"{_pretty(h2)} › {_pretty(h3)}")
            continue
        if line.strip():
            current.lines.append(line)
    if current.lines:
        blocks.append(current)
    return blocks


def _split_long(lines: list[str]) -> list[list[str]]:
    parts: list[list[str]] = [[]]
    size = 0
    for line in lines:
        if size + len(line) > MAX_CHUNK_CHARS and parts[-1]:
            parts.append([])
            size = 0
        parts[-1].append(line)
        size += len(line) + 1
    return parts


def _last_word(text: str) -> str:
    words = text.removeprefix("- ").strip().rstrip(":").split()
    return words[-1].lower() if words else ""


def _continues_previous(line: str, previous: _Item) -> bool:
    """True if a top-level bullet is really a sibling of the previous bullet's children.

    Matches when it ends with the same word as one of those children ("AD Form" after a
    child "AP Form").
    """
    children = [c for c in previous.lines[1:] if c.startswith("  - ")]
    last = _last_word(line)
    return bool(last) and any(_last_word(c.strip()) == last for c in children)


def _block_pieces(block: _Block) -> list[tuple[str | None, list[str]]]:
    """Return (entity, lines) pieces for one block."""
    paragraphs: list[str] = []
    items: list[_Item] = []
    indent = ""  # extra indent for children of a re-nested bullet
    for line in block.lines:
        if line.startswith("- ") and items and _continues_previous(line, items[-1]):
            # Riot occasionally un-nests a variant: "- Nidalee / - AP Form / ... - AD Form".
            indent = "  "
            items[-1].lines.append(indent + line)
        elif line.startswith("- "):
            indent = ""
            items.append(_Item([line]))
        elif line.startswith(" ") and line.lstrip().startswith("- ") and items:
            items[-1].lines.append(indent + line)
        else:
            paragraphs.append(line)

    if not any(item.has_children for item in items):
        return [(None, part) for part in _split_long(block.lines)]

    # Entity mode: attach "Name: ..." designer notes to the bullets they describe.
    notes: dict[int, list[str]] = {}
    general: list[str] = []
    for para in paragraphs:
        match = NOTE_PREFIX.match(para)
        prefix = match.group(1).lower() if match else ""
        targets = [
            i
            for i, item in enumerate(items)
            if item.has_children
            and prefix
            and re.search(rf"\b{re.escape(_base_name(item.name))}\b", prefix)
        ]
        for i in targets:
            notes.setdefault(i, []).append(para)
        if not targets:
            general.append(para)

    pieces: list[tuple[str | None, list[str]]] = []
    if general:
        pieces.extend((None, part) for part in _split_long(general))
    loose: list[str] = []
    for i, item in enumerate(items):
        if item.has_children:
            pieces.append((item.name.rstrip(":"), notes.get(i, []) + item.lines))
        else:
            loose.extend(item.lines)
    if loose:
        pieces.extend((None, part) for part in _split_long(loose))
    return pieces


def chunk_notes(markdown: str, patch: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for block in _blocks(markdown):
        for entity, lines in _block_pieces(block):
            chunks.append(
                Chunk(
                    key=f"{patch}-{len(chunks) + 1}",
                    patch=patch,
                    section=block.section,
                    entity=entity,
                    midpatch=block.midpatch,
                    body="\n".join(lines),
                )
            )
    return chunks
