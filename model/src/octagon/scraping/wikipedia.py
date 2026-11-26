"""Upcoming UFC cards from the Wikipedia API."""

import re
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

from octagon.trading.names import same_pair

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
    """Bouts Wikipedia lists under 'Announced bouts' but not in the card table.

    That section mixes late bookings with reports. A fight still missing an
    opponent ('vs. TBD') can't be predicted and is left out. Whether a
    named report is actually on the card is decided later, against the
    official listing — the bullet alone is not a booking.
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


# ESPN's scoreboard is the card the broadcast is actually carrying. Wikipedia's
# 'Announced bouts' bullets are reports, and a report does not get a prediction
# unless this listing has the fight. A browser User-Agent is required; the
# default Python client is refused.
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
ESPN_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _bout(weight: str, f1: str, f2: str, section: str | None) -> dict:
    title = "(c)" in f1 or "(c)" in f2 or "Title" in weight
    return {
        "weight_class": re.sub(r"\s*Title.*$", "", weight).strip(),
        "fighter1": f1.replace("(c)", "").strip(),
        "fighter2": f2.replace("(c)", "").strip(),
        "title_fight": title,
        "section": section,
    }


def table_bouts(soup) -> list[dict]:
    """Rows of the fight card table, in order, with their broadcast section.

    The table is banded by segment — 'Main card (Paramount+)',
    'Preliminary card' — as header rows between the bouts. Carrying that
    through is what lets the site group a card the way UFC does.
    """
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
            bouts.append(_bout(cells[0], cells[1], cells[3], section))
    return bouts


def _on_card(bout: dict, others) -> bool:
    pair = (bout["fighter1"], bout["fighter2"])
    for other in others:
        if isinstance(other, dict):
            names = (other["fighter1"], other["fighter2"])
        else:
            names = (other[0], other[1])
        if same_pair(pair, names):
            return True
    return False


def merge_bouts(table: list[dict], announced: list[dict],
                booked: list[tuple[str, str]] | None) -> tuple[list[dict], list[dict]]:
    """(bouts on the card, reported bouts left off).

    `booked` is the official pairs for the date. None means that listing
    could not be read; an empty list means no card is posted yet. Either
    way there is nothing to contradict a report, so the report stays.
    Once a card is posted, a report is added only when the card has that
    fight. A posted card at least as full as the Wikipedia table also
    drops a table row the official card does not list.
    """
    extras = [bout for bout in announced if not _on_card(bout, table)]
    if not booked:
        return table + extras, []
    kept = [bout for bout in extras if _on_card(bout, booked)]
    left = [bout for bout in extras if not _on_card(bout, booked)]
    if len(booked) >= len(table) > 0:
        kept_table = []
        for bout in table:
            if _on_card(bout, booked):
                kept_table.append(bout)
            else:
                left.append(bout)
        return kept_table + kept, left
    return table + kept, left


def _event_day(stamp: str) -> date | None:
    try:
        return datetime.fromisoformat(stamp).date()
    except ValueError:
        return None


def pairs_from_scoreboard(payload: dict, iso_date: str) -> list[tuple[str, str]]:
    """Fighter pairs on the scoreboard whose event falls on `iso_date`.

    The board's timestamp is UTC, so a Saturday-night card can fall on the
    next calendar day. One day of slack covers that without taking an
    event from a different week.
    """
    try:
        target = date.fromisoformat(iso_date)
    except ValueError:
        return []
    pairs = []
    for event in payload.get("events") or []:
        when = _event_day(str(event.get("date") or ""))
        if when is None or abs((when - target).days) > 1:
            continue
        for comp in event.get("competitions") or []:
            names = []
            for row in comp.get("competitors") or []:
                athlete = row.get("athlete") or {}
                name = athlete.get("displayName") or athlete.get("fullName")
                if name:
                    names.append(str(name))
            if len(names) >= 2:
                pairs.append((names[0], names[1]))
    return pairs


def booked_fights(iso_date: str) -> list[tuple[str, str]] | None:
    """Official pairs for `iso_date`, or None when the listing can't be read."""
    try:
        day = date.fromisoformat(iso_date).strftime("%Y%m%d")
    except ValueError:
        return None
    try:
        resp = requests.get(
            ESPN_SCOREBOARD,
            params={"dates": day},
            headers={"User-Agent": ESPN_UA, "Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return None
    return pairs_from_scoreboard(payload, iso_date)


def card_from_soup(soup, booked: list[tuple[str, str]] | None = None
                   ) -> tuple[list[dict], list[dict]]:
    """(card, left off) from one event page and an official listing."""
    return merge_bouts(table_bouts(soup), announced_bouts(soup), booked)


def fight_card(page_title: str, iso_date: str | None = None
               ) -> tuple[list[dict], list[dict], bool]:
    """(bouts on the card, bouts left off, whether the official card was read).

    Each bout is {weight_class, fighter1, fighter2, title_fight, section}.
    """
    soup = BeautifulSoup(_page_html(page_title), "lxml")
    booked = booked_fights(iso_date) if iso_date else None
    bouts, left_off = card_from_soup(soup, booked)
    return bouts, left_off, booked is not None


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
