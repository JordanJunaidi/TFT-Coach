from pathlib import Path

from tftcoach.rag.chunk import MAX_CHUNK_CHARS, chunk_notes

NOTES = """# Teamfight Tactics patch 18.4

Source: https://example.com

Intro from the designers.

## MID-PATCH UPDATE

### OCTOBER 7TH
B-patch summary.

### 1 COST UNIT
- Camille Ability Damage: 150 ⇒ 160
- Varus Mana: 30/120 ⇒ 20/110

## LARGE CHANGES

### TRAITS
Our aim with traits this patch is balance.
Juggernaut: Too easy to hit.
- Juggernaut
  - Durability: 20/33/45% ⇒ 20/30/42%
- Executioner (3/4)
  - Bleed Damage: 30/40% ⇒ 25/35%

### UNITS: TIER 1
Xayah and Rakan: Birds of a feather get buffed together.
- Rakan
  - Shield: 270 ⇒ 290
- Xayah
  - Damage: 68 ⇒ 73
- Nidalee
  - AP Form
    - Spear: 170 ⇒ 185
- AD Form
  - Damage: 210 ⇒ 200

## COSMETICS CONVERTED IN PATCH 18.4
- Chibi Something
"""


def by_entity(chunks):
    return {c.entity: c for c in chunks if c.entity}


def test_entity_bullets_become_chunks_with_their_designer_note() -> None:
    chunks = by_entity(chunk_notes(NOTES, "18.4"))

    jugg = chunks["Juggernaut"]
    assert jugg.section == "Large Changes › Traits"
    assert jugg.body.startswith("Juggernaut: Too easy to hit.")
    assert "20/33/45% ⇒ 20/30/42%" in jugg.body
    assert "Executioner" not in jugg.body
    assert "Executioner (3/4)" in chunks


def test_shared_designer_note_attaches_to_each_named_entity() -> None:
    chunks = by_entity(chunk_notes(NOTES, "18.4"))
    assert chunks["Rakan"].body.startswith("Xayah and Rakan:")
    assert chunks["Xayah"].body.startswith("Xayah and Rakan:")


def test_un_nested_variant_merges_into_previous_entity() -> None:
    chunks = by_entity(chunk_notes(NOTES, "18.4"))
    assert "AD Form" not in chunks
    assert "  - AD Form\n    - Damage: 210 ⇒ 200" in chunks["Nidalee"].body


def test_section_intro_is_its_own_chunk() -> None:
    chunks = chunk_notes(NOTES, "18.4")
    intro = [c for c in chunks if c.section == "Large Changes › Traits" and c.entity is None]
    assert [c.body for c in intro] == ["Our aim with traits this patch is balance."]


def test_flat_lists_stay_together_and_carry_mid_patch_label() -> None:
    chunks = chunk_notes(NOTES, "18.4")
    [units] = [c for c in chunks if c.section == "Mid-Patch Update › 1 Cost Unit"]

    assert units.entity is None
    assert units.midpatch == "OCTOBER 7TH"
    assert "Camille" in units.body and "Varus" in units.body
    assert units.content.startswith("Patch 18.4 (mid-patch update, October 7Th)")


def test_main_notes_are_not_marked_mid_patch_and_cosmetics_are_skipped() -> None:
    chunks = chunk_notes(NOTES, "18.4")
    assert all(c.midpatch is None for c in chunks if c.section.startswith("Large Changes"))
    assert not any("Chibi" in c.body for c in chunks)


def test_keys_are_sequential_per_patch() -> None:
    chunks = chunk_notes(NOTES, "18.4")
    assert [c.key for c in chunks] == [f"18.4-{i}" for i in range(1, len(chunks) + 1)]


def test_long_flat_sections_are_split() -> None:
    lines = "\n".join(f"- Fixed bug number {i} with a fairly long description" for i in range(100))
    chunks = chunk_notes(f"## BUG FIXES\n{lines}\n", "18.4")
    assert len(chunks) > 1
    assert all(len(c.body) <= MAX_CHUNK_CHARS for c in chunks)


def test_real_notes_chunk_cleanly() -> None:
    text = (Path(__file__).parents[1] / "patch_notes" / "18.4.md").read_text(encoding="utf-8")
    chunks = by_entity(chunk_notes(text, "18.4"))
    assert "Juggernaut Durability: 20/33/45% ⇒ 20/30/42%" in chunks["Juggernaut"].body
