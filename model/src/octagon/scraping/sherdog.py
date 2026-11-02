"""Sherdog fight histories. Cached JSON, polite delay."""

import json
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from octagon.db.parsing import normalize_name
from octagon.scraping.fighters import FOLD, _same_person


def _ascii_fold(name: str) -> str:
    """Strip accents while keeping case/word order, for search queries.

    Sherdog's fightfinder endpoint can't handle accented input ('Jan
    Błachowicz' -> 0 hits; 'Jan Blachowicz' -> 1) — the same gap
    scraping/fighters.py's slug() works around for ufc.com URLs.
    """
    folded = unicodedata.normalize("NFKD", name.translate(FOLD))
    return "".join(c for c in folded if not unicodedata.combining(c))

SHERDOG_BASE = "https://www.sherdog.com"
# The fightfinder autocomplete endpoint used by the site's own search box —
# returns clean JSON, no HTML scraping needed to locate a fighter. robots.txt
# is `User-agent: * / Allow: /` with no AI-crawler carve-out, unlike
# Tapology, so this project scrapes Sherdog but not Tapology (see
# scraping/fighters.py's header for the ufc.com/ufcstats.com precedent this
# follows: honour what a site's own robots.txt says).
SHERDOG_SEARCH = f"{SHERDOG_BASE}/search/fightfinder/"

USER_AGENT = "octagon-oracle/0.1 (educational UFC prediction project)"
CRAWL_DELAY = 0.5

# Fighters Sherdog files under their formal name while the UFC bills them by
# a diminutive. _same_person deliberately will not bridge these — it requires
# one name's tokens to be a subset of the other's, and 'vlasto' is not
# 'vlastislav' — because loosening that to a prefix rule would silently pair
# up same-surname relatives. Each entry below is verified by hand against
# Sherdog's own event listing for the bout in question, keyed by
# normalize_name so accents and word order don't matter.
SHERDOG_ALIASES = {
    # Same Minev/Livingston opponents as UFC's Tommy Gantt profile:
    # https://www.sherdog.com/fighter/Thomas-Gantt-428202
    "gantt tommy": "Thomas Gantt",
    # Sherdog's UFC Fight Night 283 card lists this man, 14-3, opposite
    # Gilbert Urbina: https://www.sherdog.com/fighter/Vlastislav-Cepo-330615
    "cepo vlasto": "Vlastislav Cepo",
    # UFC Fight Night 286 (Shanghai). ufcstats concatenates the Mongolian
    # given name; Sherdog splits it. Event page:
    # https://www.sherdog.com/events/UFC-Fight-Night-286-Nurmagomedov-vs-Song-113007
    "aoriqileng": "Qileng Aori",
    "sumudaerji": "Su Mudaerji",
    "de hector santiago sousa": "Hector Santiago",
    # UFC bills him as Muhammad Naimov; Sherdog uses his legal first name and
    # the UFC Fight Night 287 event page links this profile opposite Losene
    # Keita: https://www.sherdog.com/fighter/Muhammadjon-Naimov-228381
    "muhammad naimov": "Muhammadjon Naimov",
    # UFC / Tapology bill him as Reginaldo Junior; Sherdog files the legal
    # middle name. DWCS 2026 Week 5 event page:
    # https://www.sherdog.com/events/Dana-Whites-Contender-Series-Contender-Series-2026-Week-5-112631
    "junior reginaldo": "Reginaldo Geraldo Jr",
}


def _blank(name: str) -> dict:
    """A cached miss — same shape as a hit, for consistent consumers."""
    return {
        "name": name,
        "key": normalize_name(name),
        "sherdog_fighter_id": None,
        "sherdog_url": None,
        "regional_fights": [],
        "fetched": datetime.now().isoformat(),
    }


def _hit_names(hit: dict) -> list[str]:
    """Every name a search hit could legitimately be billed under.

    Sherdog files a fighter by legal name and carries the ring name in a
    separate `nickname` field, but promotions often bill the nickname as if
    it were a surname — 'Jose Luiz', nickname 'Montanha', appears on the UFC
    card as 'Jose Montanha'. Offering the nickname combinations to
    _same_person lets that match without weakening the guard itself: each
    candidate still has to match on the full token set, so a shared first
    name or a coincidental nickname alone can never pass.
    """
    first = (hit.get("firstname") or "").strip()
    last = (hit.get("lastname") or "").strip()
    nick = (hit.get("nickname") or "").strip()
    names = [f"{first} {last}".strip()]
    if nick:
        names += [f"{first} {nick} {last}".strip(), f"{first} {nick}".strip()]
    return [n for n in names if n]


def _search_sherdog(fighter_name: str, session: requests.Session) -> Optional[str]:
    """Search Sherdog's fightfinder JSON API and return the fighter page URL.

    The site's own search box calls this endpoint for autocomplete — it
    returns structured JSON (id, firstname, lastname, url), no HTML to
    scrape and no slug-guessing. Only an exact name match (after folding) is
    accepted, same discipline as ufc.com/Wikipedia in fighters.py, except for
    the hand-verified SHERDOG_ALIASES.
    """
    expected = SHERDOG_ALIASES.get(normalize_name(fighter_name), fighter_name)
    try:
        resp = session.get(SHERDOG_SEARCH, params={"q": _ascii_fold(expected)},
                           timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None

    for hit in data.get("collection", []):
        if hit.get("source") != "Fighter":
            continue
        if any(_same_person(candidate, expected)
               for candidate in _hit_names(hit)):
            href = hit.get("url", "")
            return f"{SHERDOG_BASE}{href}" if href.startswith("/") else href

    return None


def event_fighter_urls(event_url: str,
                       session: Optional[requests.Session] = None) -> dict[str, str]:
    """Map every fighter on a Sherdog event page to their fighter page.

    Name search is not safe on its own for common names: 'Daniel Rodriguez'
    returns a dozen fighters and 'Michael Oliveira' eight, and the first one
    whose name matches can easily be a different man who lost a single bout
    in 2003. An event page has no such ambiguity — it links the actual
    entrants — so when the caller knows the Sherdog page for the card, these
    URLs take precedence over anything the search endpoint suggests.

    Returns {normalize_name(fighter): absolute URL}; empty if the page can't
    be read, so a bad URL degrades to plain search rather than failing.
    """
    session = session or _session()
    try:
        resp = session.get(event_url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        return {}

    soup = BeautifulSoup(resp.text, "lxml")
    urls: dict[str, str] = {}
    for link in soup.select('a[href^="/fighter/"]'):
        name = " ".join(link.get_text(" ").split())
        if not name:
            continue
        urls.setdefault(normalize_name(name),
                        f"{SHERDOG_BASE}{link['href']}")
    return urls


def _parse_fight_history(fighter_url: str, session: requests.Session) -> list[dict]:
    """Parse the fight history table from a Sherdog fighter page.

    Table structure (class="new_table fighter"): Result | Fighter | Event |
    Method/Referee | R | Time. Result and method live in nested spans/bold
    tags, and the event cell packs the event name and date into two lines
    (an <a> then a `.sub_line` span) — see this module's tests for a fixture.
    """
    try:
        resp = session.get(fighter_url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    return _parse_fight_table(soup)


def _parse_fight_table(soup: "BeautifulSoup") -> list[dict]:
    table = soup.find("table", class_="fighter")
    if table is None:
        return []

    fights = []
    for row in table.find_all("tr")[1:]:  # skip header row
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        result_span = cells[0].find("span", class_="final_result")
        result_text = (result_span.get_text(strip=True) if result_span
                       else cells[0].get_text(strip=True)).lower()
        result_map = {"win": "win", "loss": "loss", "draw": "draw", "nc": "nc"}
        result = result_map.get(result_text)
        if not result:
            continue

        opponent_link = cells[1].find("a")
        opponent = opponent_link.get_text(strip=True) if opponent_link else \
            cells[1].get_text(strip=True)

        event_link = cells[2].find("a")
        event_text = event_link.get_text(strip=True) if event_link else ""
        date_span = cells[2].find("span", class_="sub_line")
        date_text = date_span.get_text(strip=True) if date_span else ""
        date_iso = _parse_date(date_text)
        if not date_iso:
            continue

        method_bold = cells[3].find("b")
        method_text = method_bold.get_text(strip=True) if method_bold else \
            cells[3].get_text(strip=True)
        method_norm = _normalize_method(method_text)

        is_amateur = 1 if "amateur" in event_text.lower() else 0

        fights.append({
            "opponent": opponent,
            "date": date_iso,
            "result": result,
            "method": method_norm,
            "org": event_text or "Unknown",
            "is_amateur": is_amateur,
            "source": "sherdog",
        })

    return fights


def _parse_date(date_str: str) -> Optional[str]:
    """Parse a date string to ISO format YYYY-MM-DD.

    Sherdog's own format is 'Mar / 28 / 2026' (slash-separated with spaces);
    a couple of more conventional fallbacks are kept in case of layout
    changes, cheaper than a second network round trip to find out.
    """
    if not date_str:
        return None

    cleaned = date_str.strip()
    for fmt in ["%b / %d / %Y", "%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%d/%m/%Y"]:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def _normalize_method(method_str: str) -> str:
    """Normalize fight method to standard codes."""
    method_lower = method_str.lower().strip()

    if "ko" in method_lower or "tko" in method_lower or "knockout" in method_lower:
        return "KO/TKO"
    if "sub" in method_lower or "submission" in method_lower:
        return "SUB"
    if "dec" in method_lower or "decision" in method_lower:
        return "DEC"
    if "draw" in method_lower:
        return "DEC"
    if "nc" in method_lower or "no contest" in method_lower:
        return "NC"

    return method_str[:15] if method_str else "DEC"


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch(names: list[str], delay: float = 0.5,
          known_urls: Optional[dict[str, str]] = None) -> dict[str, dict]:
    """Fetch Sherdog records for these fighters. All network access is here.

    `known_urls` (normalize_name -> fighter URL, e.g. from
    event_fighter_urls) short-circuits the ambiguous name search.
    """
    unique = sorted({n.strip() for n in names if n and n.strip()})
    known_urls = known_urls or {}

    session = _session()

    records = {}
    for i, name in enumerate(unique):
        if i:
            time.sleep(delay)

        record = _blank(name)

        alias = SHERDOG_ALIASES.get(normalize_name(name), name)
        fighter_url = (known_urls.get(normalize_name(name))
                       or known_urls.get(normalize_name(alias))
                       or _search_sherdog(name, session))
        if fighter_url:
            record["sherdog_url"] = fighter_url
            # URL shape is /fighter/First-Last-<id>; id is the trailing digits.
            match = re.search(r"-(\d+)/?$", fighter_url)
            if match:
                record["sherdog_fighter_id"] = match.group(1)

            time.sleep(delay)
            fights = _parse_fight_history(fighter_url, session)
            record["regional_fights"] = fights

        records[name] = record

    return records


def _disagrees(record: dict, known_urls: dict[str, str], name: str) -> bool:
    """Does an authoritative URL contradict what we have cached for a fighter?"""
    alias = SHERDOG_ALIASES.get(normalize_name(name), name)
    expected = (known_urls.get(normalize_name(name))
                or known_urls.get(normalize_name(alias)))
    return bool(expected) and record.get("sherdog_url") != expected


def load_cache(path: Path) -> dict[str, dict]:
    """Load the JSON cache."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return {}


def save_cache(path: Path, cache: dict[str, dict]) -> None:
    """Save the JSON cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache, indent=1, ensure_ascii=False, sort_keys=True),
        encoding="utf-8"
    )


def refresh(
    names: list[str],
    path: Path,
    delay: float = 0.5,
    force: bool = False,
    on_progress=None,
    known_urls: Optional[dict[str, str]] = None,
) -> dict[str, dict]:
    """Top up the cache for these fighters and return their records.

    Keyed by normalized name so spelling variations don't trigger re-scrapes.
    A cached record that `known_urls` disagrees with is re-fetched even
    without `force`: it was scraped off a name search, and being cached is no
    evidence it was ever the right man.
    """
    cache = load_cache(path)
    known_urls = known_urls or {}
    wanted = {normalize_name(n): n for n in names if n and n.strip()}
    missing = [name for key, name in wanted.items()
               if force or key not in cache or _disagrees(cache[key], known_urls, name)]

    for name, record in fetch(missing, delay, known_urls).items():
        cache[normalize_name(name)] = record
        save_cache(path, cache)  # Checkpoint after each fighter
        if on_progress:
            on_progress(record)

    return {name: cache.get(key, _blank(name)) for key, name in wanted.items()}


def lookup(names: list[str], path: Path) -> dict[str, dict]:
    """Read-only view of the cache — no network, for predict time."""
    cache = load_cache(path)
    return {
        name: cache.get(normalize_name(name), _blank(name))
        for name in names if name
    }
