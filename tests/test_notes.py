import pytest

from tftcoach.rag.notes import html_to_markdown, notes_url

PAGE = """
<html><body><nav>Menu</nav>
<div id="patch-notes-container">
  <h2>LARGE CHANGES</h2>
  <div class="designer"><img src="x.png"> Riot Designer</div>
  <h4>TRAITS</h4>
  <p>Juggernaut: too easy to hit.</p>
  <ul><li>Juggernaut<ul><li>Durability: 20/33/45% &rArr; 20/30/42%</li></ul></li></ul>
  <script>tracking()</script>
</div>
<footer>Related Articles</footer></body></html>
"""


def test_converts_headings_lists_and_skips_noise() -> None:
    md = html_to_markdown(PAGE, "18.4")

    assert md.startswith("# Teamfight Tactics patch 18.4\n\nSource: ")
    assert "## LARGE CHANGES" in md
    assert "### TRAITS" in md
    assert "- Juggernaut\n  - Durability: 20/33/45% ⇒ 20/30/42%" in md
    # Content after an <img> (a void tag) must not be swallowed.
    assert "Juggernaut: too easy to hit." in md
    assert "tracking" not in md and "Menu" not in md and "Related Articles" not in md


def test_missing_container_is_an_error() -> None:
    with pytest.raises(ValueError):
        html_to_markdown("<html><body>No notes</body></html>", "18.4")


def test_notes_url_uses_dashed_patch() -> None:
    assert notes_url("18.4").endswith("/teamfight-tactics-patch-18-4/")
