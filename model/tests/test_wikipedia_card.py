"""Card scraping: names must come out exactly as the fighter is called."""

from bs4 import BeautifulSoup

from octagon.scraping.wikipedia import _clean


def cell(html):
    return BeautifulSoup(f"<table><tr><td>{html}</td></tr></table>", "html.parser").td


def test_footnote_markers_never_reach_a_fighter_name():
    assert _clean(cell('Alateng Heili <sup class="reference">[<a>17</a>]</sup>')) == "Alateng Heili"
    assert _clean(cell('Josh Hokit<sup>[a]</sup>')) == "Josh Hokit"
    assert _clean(cell("  Ciryl   Gane ")) == "Ciryl Gane"
