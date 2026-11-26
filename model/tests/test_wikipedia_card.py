"""Card scraping: names must come out exactly as the fighter is called,
and a report that is not on the official card must not become a fight.
"""

import requests
from bs4 import BeautifulSoup

from octagon.scraping import wikipedia
from octagon.scraping.wikipedia import _clean, card_from_soup, pairs_from_scoreboard

PAGE = """
<table>
<tr><th>Main card (Paramount+)</th></tr>
<tr>
  <td>Middleweight</td><td>Israel Adesanya</td><td>vs.</td>
  <td>Sharabutdin Magomedov</td>
</tr>
<tr>
  <td>Welterweight</td><td>Ian Machado Garry</td><td>vs.</td>
  <td>Yaroslav Amosov</td>
</tr>
</table>
<h2 id="Announced_bouts">Announced bouts</h2>
<ul>
  <li>Middleweight bout: Anvarbek Daniyalbekov vs. Robert Bryczek<sup>[11]</sup></li>
  <li>Lightweight bout: Mateusz Rębecki vs. Elves Brener</li>
  <li>Heavyweight bout: Jovan Leka vs. TBD</li>
</ul>
"""

# The broadcast listing uses the short names. It has the two table fights
# and the lightweight booking, and not the middleweight report.
OFFICIAL = [
    ("Israel Adesanya", "Shara Magomedov"),
    ("Yaroslav Amosov", "Ian Machado Garry"),
    ("Elves Brener", "Mateusz Rebecki"),
]


def page():
    return BeautifulSoup(PAGE, "html.parser")


def names(bouts):
    return [(b["fighter1"], b["fighter2"]) for b in bouts]


def cell(html):
    return BeautifulSoup(f"<table><tr><td>{html}</td></tr></table>", "html.parser").td


def test_footnote_markers_never_reach_a_fighter_name():
    assert _clean(cell('Alateng Heili <sup class="reference">[<a>17</a>]</sup>')) == "Alateng Heili"
    assert _clean(cell('Josh Hokit<sup>[a]</sup>')) == "Josh Hokit"
    assert _clean(cell("  Ciryl   Gane ")) == "Ciryl Gane"


def test_a_report_that_is_not_on_the_official_card_is_left_off():
    card, left = card_from_soup(page(), OFFICIAL)
    assert ("Anvarbek Daniyalbekov", "Robert Bryczek") not in names(card)
    assert ("Anvarbek Daniyalbekov", "Robert Bryczek") in names(left)
    assert ("Mateusz Rębecki", "Elves Brener") in names(card)
    assert ("Jovan Leka", "TBD") not in names(card) + names(left)
    # Shortened broadcast names still keep the Wikipedia spelling.
    assert ("Israel Adesanya", "Sharabutdin Magomedov") in names(card)
    assert card[0]["section"] == "Main card"


def test_a_reported_bout_stays_when_no_official_card_is_posted():
    for booked in (None, []):
        card, left = card_from_soup(page(), booked)
        assert ("Anvarbek Daniyalbekov", "Robert Bryczek") in names(card)
        assert left == []


def test_a_table_row_stays_while_the_official_card_is_still_short():
    """A partial listing must not delete fights Wikipedia has already tabulated."""
    booked = [("Israel Adesanya", "Shara Magomedov")]
    card, left = card_from_soup(page(), booked)
    assert ("Ian Machado Garry", "Yaroslav Amosov") in names(card)
    assert ("Anvarbek Daniyalbekov", "Robert Bryczek") in names(left)


def test_a_full_official_card_drops_a_table_row_it_does_not_list():
    html = PAGE.replace(
        "</table>",
        "<tr><td>Middleweight</td><td>Anvarbek Daniyalbekov</td>"
        "<td>vs.</td><td>Robert Bryczek</td></tr></table>",
    )
    booked = [
        ("Israel Adesanya", "Shara Magomedov"),
        ("Yaroslav Amosov", "Ian Machado Garry"),
        ("Elves Brener", "Mateusz Rebecki"),
    ]
    card, left = card_from_soup(BeautifulSoup(html, "html.parser"), booked)
    assert ("Anvarbek Daniyalbekov", "Robert Bryczek") not in names(card)
    assert ("Anvarbek Daniyalbekov", "Robert Bryczek") in names(left)


def test_scoreboard_pairs_follow_the_event_date():
    payload = {"events": [
        {"date": "2026-12-05T15:00Z", "competitions": [
            {"competitors": [
                {"athlete": {"displayName": "Israel Adesanya"}},
                {"athlete": {"displayName": "Shara Magomedov"}},
            ]},
            {"competitors": [{"athlete": {"displayName": "Only One"}}]},
        ]},
        {"date": "2026-12-12T15:00Z", "competitions": [
            {"competitors": [
                {"athlete": {"displayName": "Anvarbek Daniyalbekov"}},
                {"athlete": {"displayName": "Robert Bryczek"}},
            ]},
        ]},
    ]}
    assert pairs_from_scoreboard(payload, "2026-12-05") == [
        ("Israel Adesanya", "Shara Magomedov"),
    ]
    # Saturday night in the US is already Sunday on the board's UTC clock.
    assert pairs_from_scoreboard(payload, "2026-12-04") == [
        ("Israel Adesanya", "Shara Magomedov"),
    ]
    assert pairs_from_scoreboard(payload, "not-a-date") == []


def test_an_unreadable_official_card_is_not_treated_as_empty(monkeypatch):
    def down(*args, **kwargs):
        raise requests.RequestException("scoreboard down")

    monkeypatch.setattr(wikipedia.requests, "get", down)
    assert wikipedia.booked_fights("2026-12-05") is None
