"""Upcoming UFC cards from the Wikipedia API."""

import re
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "octagon-oracle/0.1 (educational UFC prediction project)"


def _page_html(title: str) -> str:
    resp = requests.get(API, params={
        "action": "parse", "page": title, "prop": "text",
        "format": "json", "formatversion": 2,
    }, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.json()["parse"]["text"]


# A footnote marker such as [17] or [a]. Joining a cell's text with spaces
# turns it into "[ 17 ]", which would otherwise end up inside a fighter's name.
CITATION = re.compile(r"\[\s*[0-9a-z]{1,3}\s*\]")


def _clean(cell) -> str:
    return " ".join(CITATION.sub("", cell.get_text(" ", strip=True)).split())


def next_event(today: date | None = None) -> tuple[str, str, str]:
    """(wiki page title, event name, ISO date) of the nearest future event."""
    today = today or date.today()
    soup = BeautifulSoup(_page_html("List of UFC events"), "lxml")
    header = soup.find(id="Scheduled_events")
    table = header.find_next("table")
    best = None
    for row in table.select("tr"):
        cells = row.select("td")
        if len(cells) < 2:
            continue
        try:
            when = datetime.strptime(_clean(cells[1]), "%b %d, %Y").date()
        except ValueError:
            continue
        link = cells[0].find("a")
        if when >= today and link and (best is None or when < best[2]):
            best = (link["title"], _clean(cells[0]), when)
    if best is None:
        raise SystemExit("No scheduled UFC event found on Wikipedia.")
    return best[0], best[1], best[2].isoformat()


SECTION_PATTERN = re.compile(r"^(early preliminary|preliminary|main) card", re.I)

# 'Heavyweight bout: Jovan Leka vs. Alexander Poppeck' — the shape of the
# bullets under an event page's 'Announced bouts' heading.
ANNOUNCED_PATTERN = re.compile(
    r"^(?P<weight>.+?)\s+bout:\s*(?P<f1>.+?)\s+vs\.?\s+(?P<f2>.+)$", re.I)


def announced_bouts(soup) -> list[dict]:
    """Bouts announced but not yet placed in the card table.

    Weeks out, Wikipedia keeps late additions in a bulleted 'Announced
    bouts' section below the table; skipping them silently drops real
    fights from the card. Bouts still missing an opponent ('vs. TBD')
    can't be predicted and are left out.
    """
    header = soup.find(id="Announced_bouts")
    if header is None:
        return []
    listing = header.find_next("ul")
    if listing is None:
        return []
    bouts = []
    for item in listing.find_all("li", recursive=False):
        text = _clean(item)
        match = ANNOUNCED_PATTERN.match(text)
        if not match:
            continue
        weight, f1, f2 = (match.group("weight"), match.group("f1"),
                          match.group("f2"))
        if any("tbd" in name.lower().split() or name.strip().upper() == "TBD"
               for name in (f1, f2)):
            continue
        bouts.append({
            "weight_class": re.sub(r"\s*Title.*$", "", weight).strip(),
            "fighter1": f1.replace("(c)", "").strip(),
            "fighter2": f2.replace("(c)", "").strip(),
            "title_fight": "Title" in weight,
            "section": "Announced",
        })
    return bouts


def fight_card(page_title: str) -> list[dict]:
    """Announced bouts: [{weight_class, fighter1, fighter2, title_fight, section}].

    The bout table is banded by broadcast segment — 'Main card (Paramount+)',
    'Preliminary card (ESPN+)' — as header rows between the bouts. Carrying
    that through is what lets the site group a card the way UFC does instead
    of showing thirteen equal-weight rows.
    """
    soup = BeautifulSoup(_page_html(page_title), "lxml")
    bouts = []
    section = None
    for row in soup.select("table tr"):
        headers = row.select("th")
        cells = [_clean(c) for c in row.select("td")]
        if not cells and len(headers) == 1:
            match = SECTION_PATTERN.match(_clean(headers[0]))
            if match:
                # Drop the broadcaster: 'Main card (Paramount+)' -> 'Main card'.
                section = re.sub(r"\s*\(.*\)\s*$", "", _clean(headers[0]))
            continue
        if len(cells) >= 4 and cells[2] == "vs.":
            weight, f1, f2 = cells[0], cells[1], cells[3]
            title = "(c)" in f1 or "(c)" in f2 or "Title" in weight
            bouts.append({
                "weight_class": re.sub(r"\s*Title.*$", "", weight).strip(),
                "fighter1": f1.replace("(c)", "").strip(),
                "fighter2": f2.replace("(c)", "").strip(),
                "title_fight": title,
                "section": section,
            })
    return bouts + announced_bouts(soup)


def card_yaml(event_name: str, iso_date: str, bouts: list[dict]) -> dict:
    """The dict that predict's card loader consumes (see cards/*.yaml)."""
    fights = []
    for i, b in enumerate(bouts):
        fights.append({
            "fighter1": b["fighter1"],
            "fighter2": b["fighter2"],
            "weight_class": b["weight_class"],
            "title_fight": b["title_fight"],
            # Main event and title fights are five rounds.
            "rounds": 5 if (i == 0 or b["title_fight"]) else 3,
            "section": b.get("section"),  # 'Main card' / 'Preliminary card'
            "odds": None,  # add [f1_decimal, f2_decimal] by hand if desired
        })
    return {"date": iso_date, "event": event_name, "fights": fights}
