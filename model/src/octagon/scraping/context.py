"""Day-before context: circumstances, regional records, news, YouTube buzz.

Cached next to the card. Adjustments at predict time are small and skipped
when the signal is missing.
"""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from octagon.db.parsing import normalize_name
from octagon.scraping.fighters import slug
from octagon.scraping.wikipedia import USER_AGENT, _page_html

WIKI_API = "https://en.wikipedia.org/w/api.php"
NEWS_RSS = "https://news.google.com/rss/search"

# Small, explainable pulls — never large enough to overrule a priced market
# stack when odds are present.
DEBUT_PRIOR_WEIGHT = 0.18       # how hard a pro-record prior can tug a debut
SHORT_NOTICE_DAMPEN = 0.35      # shrink confidence toward 0.5 for short-notice
SENTIMENT_WEIGHT = 0.04         # tiny lean from headline polarity
# YouTube crowd lean: only nudges when the skill model is near a coin flip.
# Belgrade lesson — hyped debutants (Čepo) are exactly where crowd noise
# agrees with a wrong market, so we never let this overrule a clear skill call.
YOUTUBE_WEIGHT = 0.06           # max |Δp| from a full ±1.0 YouTube lean
YOUTUBE_SKILL_BAND = 0.08       # |skill_p - 0.5| must be inside this
YOUTUBE_MIN_SIGNALS = 4         # ignore thin comment scrapes

POSITIVE = re.compile(
    r"\b(dominant|finisher|knockout|prospect|streak|favourite|favorite|"
    r"lock|destroys|overwhelming|unbeaten|dangerous|elite|champ|"
    r"finishing|stoppage)\b", re.I)
NEGATIVE = re.compile(
    r"\b(injury|injured|withdraw|short notice|layoff|rust|overmatched|"
    r"underdog|concern|missed weight|cut|replaced|risky|vulnerable|"
    r"questionable|loss|losing)\b", re.I)

STYLE_WORDS = {
    "striker": re.compile(
        r"\b(striker|kickbox|muay thai|boxing|knockout artist|"
        r"power puncher|striking)\b", re.I),
    "wrestler": re.compile(
        r"\b(wrestler|wrestling|takedown|collegiate|"
        r"freestyle|folkstyle)\b", re.I),
    "grappler": re.compile(
        r"\b(bjj|brazilian jiu|submission|grappler|"
        r"jiu-jitsu|jiujitsu|ground)\b", re.I),
    "pressure": re.compile(
        r"\b(pressure|forward|aggressive|pace|volume)\b", re.I),
}

# A capitalised run of 1-4 words. Case-sensitive on purpose: with re.I,
# [A-Z] also matches 'steps' / 'against' and the name swallows the trigger.
_NAME = r"[A-Z][\w.'\-]+(?:\s+[A-Z][\w.'\-]+){0,3}"

# Phrasings that mean "this fighter took the bout without a full camp".
# Wikipedia writes short notice several different ways, and the one that
# matters most is a bare day count ('three days before the event').
SHORT_NOTICE_CUE = re.compile(
    r"short notice"
    r"|(?:\w+|\d+)\s+(?:days?|weeks?)'?s?\s+notice"
    r"|less than (?:\w+|\d+)\s+(?:days?|weeks?)'?s?\s+notice"
    r"|(?:\w+|\d+)\s+(?:days?|weeks?)\s+(?:before|prior to)\s+the\s+(?:event|card|fight)"
    r"|late replacement|promotional newcomer",
    re.I)

NAME_RUN = re.compile(_NAME)

# Who the sentence is about. Direction matters and used to be wrong: in
# "Ochoa pulled out and was replaced by Henrique", the man who needs the
# short-notice flag is Henrique — the one arriving, not the one leaving.
#
# Rather than trying to skip the words between the trigger and the name, we
# take the whole side of the sentence and look for the nearest name that
# resolves to someone on the card. Wikipedia pads these clauses with
# arbitrary description ("replaced by promotional newcomer and fellow former
# LFA flyweight champion Eduardo Henrique"), which no fixed-width skip
# survives.
#
# Only "replaced by X" puts the arriving fighter after the trigger. Every
# other phrasing names him first — and the ones that look forwards name his
# OPPONENT ("steps in against Blachowicz") or the man he replaced ("as a
# replacement for Ochoa"), so they must be read backwards or not at all.
INCOMING_AFTER = re.compile(r"replaced by", re.I)
INCOMING_BEFORE = re.compile(
    r"(?:steps?|stepped|stepping)\s+in\b|"
    r"(?:was|is)\s+(?:brought|called|drafted)\s+in\b|"
    r"as a (?:late )?replacement\b|"
    r"accepted the (?:bout|fight)", re.I)
FACING_INSTEAD = re.compile(rf"facing\s+(?P<who>{_NAME})\s+instead", re.I)

OUTGOING = re.compile(
    rf"(?P<who>{_NAME})\s+(?:\w+\s+){{0,3}}?"
    r"(?:withdrew|withdraw[s]?|pulled out|was (?:forced )?(?:out|removed)|"
    r"(?i:is out\b))")

RECORD_RE = re.compile(
    r"(?P<w>\d+)\s*[-–]\s*(?P<l>\d+)(?:\s*[-–]\s*(?P<d>\d+))?")

# Wikipedia's plain-text extraction leaves reference markers inline.
CITATION = re.compile(r"\[\s*\d+\s*\]")


def context_path(card_path: Path) -> Path:
    """`cards/foo.yaml` -> `data/card_context/foo.json`."""
    return (card_path.resolve().parents[1] / "data" / "card_context"
            / f"{card_path.stem}.json")


def load_context(card_path: Path) -> dict | None:
    path = context_path(card_path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_context(card_path: Path, payload: dict) -> Path:
    path = context_path(card_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def event_background(page_title: str) -> str:
    """Plain text of the Background section, if the page has one."""
    soup = BeautifulSoup(_page_html(page_title), "lxml")
    header = soup.find(id="Background")
    if header is None:
        return ""
    chunks = []
    for sib in header.parent.find_next_siblings():
        if sib.name in ("h2", "h3") and sib.find(class_="mw-headline"):
            break
        if sib.name == "p":
            chunks.append(sib.get_text(" ", strip=True))
    return "\n".join(chunks)


def build_resolver(names: list[str], aliases: dict[str, str] | None = None):
    """A name matcher for prose that does not use the card's spellings.

    Wikipedia frequently uses a different name than the UFC does — the man
    ufc.com calls 'Eduardo Chapolin' is 'Eduardo Henrique' there, and a
    plain substring test matches neither way round. Three passes, most
    trustworthy first:

    1. explicit `aliases` from the card YAML (a human wrote it down),
    2. exact / substring match on the normalized name,
    3. a single shared token, but only when it points at exactly ONE
       fighter on the card. 'Eduardo' is unique here so it resolves;
       'Johnson' matches both Charles and Donte, so it is refused rather
       than guessed.
    """
    known = {normalize_name(n): n for n in names}
    alias_map = {normalize_name(k): normalize_name(v)
                 for k, v in (aliases or {}).items()}

    token_owners: dict[str, set[str]] = {}
    for key in known:
        for token in key.split():
            if len(token) >= 4:
                token_owners.setdefault(token, set()).add(key)

    def resolve(who: str) -> str | None:
        key = normalize_name(who)
        if not key:
            return None
        if key in alias_map and alias_map[key] in known:
            return alias_map[key]
        if key in known:
            return key
        # Both the substring and the shared-token pass must be unambiguous.
        # 'Johnson' is a substring of two men on the UFC 330 card, so it
        # resolves to neither: a wrong flag is worse than a missing one.
        partial = {nk for nk in known if nk in key or key in nk}
        if len(partial) == 1:
            return next(iter(partial))
        candidates = {owner for token in key.split()
                      for owner in token_owners.get(token, ())}
        if len(candidates) == 1:
            return next(iter(candidates))
        return None

    return resolve


def parse_circumstances(background: str, names: list[str],
                        aliases: dict[str, str] | None = None) -> dict[str, dict]:
    """Map normalized fighter name -> circumstance flags + notes.

    Worked sentence by sentence, because attribution is local: the fighter
    who arrives on short notice and the fighter who withdrew are named in
    the same clause, and only the arriving one is actually fighting.
    """
    resolve = build_resolver(names, aliases)
    out: dict[str, dict] = {normalize_name(n): {
        "short_notice": False,
        "late_replacement": False,
        "opponent_changed": False,
        "notes": [],
    } for n in names}

    def flag(key: str | None, kind: str, note: str) -> None:
        if key is None or key not in out:
            return
        bucket = out[key]
        bucket[kind] = True
        # These notes are shown verbatim on the site, so drop Wikipedia's
        # inline citation markers ("[ 11 ]") and the space before punctuation
        # its text extraction leaves behind.
        note = CITATION.sub("", note)
        note = re.sub(r"\s+([.,;])", r"\1", " ".join(note.split())).strip()
        note = re.sub(r"^(?:However|But),?\s+", "", note)[:240]
        if note and note not in bucket["notes"]:
            bucket["notes"].append(note)

    # Wikipedia's background is one paragraph per booking change, and a
    # sentence is the tightest span that still holds both names.
    for sentence in re.split(r"(?<=[.!?])\s+", background):
        if not sentence.strip():
            continue
        cue = SHORT_NOTICE_CUE.search(sentence)
        incoming: list[str] = []

        def add(key: str | None) -> None:
            if key is not None and key not in incoming:
                incoming.append(key)

        # Nearest resolvable name on the far side of the trigger: forwards
        # for "replaced by X", backwards for "X stepped in".
        for match in INCOMING_AFTER.finditer(sentence):
            for name in NAME_RUN.finditer(sentence[match.end():]):
                key = resolve(name.group(0))
                if key is not None:
                    add(key)
                    break
        for match in INCOMING_BEFORE.finditer(sentence):
            for name in reversed(list(NAME_RUN.finditer(sentence[:match.start()]))):
                key = resolve(name.group(0))
                if key is not None:
                    add(key)
                    break
        for match in FACING_INSTEAD.finditer(sentence):
            add(resolve(match.group("who")))

        for key in incoming:
            flag(key, "late_replacement", sentence)
            # A replacement is only 'short notice' when the prose says so.
            # An opponent swap announced a month out is a different animal.
            if cue:
                flag(key, "short_notice", sentence)

        for match in OUTGOING.finditer(sentence):
            key = resolve(match.group("who"))
            # The man who pulled out is usually not on the card at all; the
            # note belongs to whoever is still fighting in this sentence.
            if key is not None and key not in incoming:
                flag(key, "opponent_changed", sentence)
            for other in incoming:
                flag(other, "opponent_changed", sentence)
    return out


def _wiki_summary(name: str) -> dict:
    """Lead extract + description for one fighter article."""
    resp = requests.get(WIKI_API, params={
        "action": "query", "titles": name, "prop": "extracts|pageprops",
        "exintro": 1, "explaintext": 1, "redirects": 1,
        "format": "json", "formatversion": 2,
    }, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        search = requests.get(WIKI_API, params={
            "action": "query", "list": "search", "srlimit": 5,
            "srsearch": f"{name} mixed martial artist",
            "format": "json", "formatversion": 2,
        }, headers={"User-Agent": USER_AGENT}, timeout=30)
        search.raise_for_status()
        title = None
        for hit in search.json().get("query", {}).get("search", []):
            ht = normalize_name(hit["title"])
            nt = normalize_name(name)
            if ht == nt or ht.split()[-1:] == nt.split()[-1:]:
                title = hit["title"]
                break
        if not title:
            return {}
        return _wiki_summary(title)

    page = pages[0]
    extract = page.get("extract") or ""
    return {
        "wiki_title": page.get("title"),
        "description": page.get("pageprops", {}).get("wikibase-shortdesc"),
        "summary": extract[:1200],
        "styles": _styles_from_text(extract),
        "pro_record": _record_from_text(extract),
    }


def _styles_from_text(text: str) -> list[str]:
    return [label for label, pattern in STYLE_WORDS.items()
            if pattern.search(text)]


def _record_from_text(text: str) -> dict | None:
    """Best-effort W-L-D from a bio sentence like 'with a record of 16-2'."""
    for match in RECORD_RE.finditer(text):
        wins, losses = int(match.group("w")), int(match.group("l"))
        d = int(match.group("d") or 0)
        if wins + losses + d < 3 or wins > 80:
            continue
        window = text[max(0, match.start() - 40):match.end() + 20].lower()
        if any(tok in window for tok in ("record", "mma", "professional",
                                         "career", "wins")):
            return {"wins": wins, "losses": losses, "draws": d,
                    "win_pct": (wins + 0.5) / (wins + losses + 1.0)}
    return None


def parse_pro_record(record: str | None) -> dict | None:
    """'16-2-0' / '16-2' from ufc.com media cache -> structured prior."""
    if not record:
        return None
    match = RECORD_RE.search(record.replace(" ", ""))
    if not match:
        return None
    wins, losses = int(match.group("w")), int(match.group("l"))
    d = int(match.group("d") or 0)
    return {"wins": wins, "losses": losses, "draws": d,
            "win_pct": (wins + 0.5) / (wins + losses + 1.0),
            "source": "ufc.com"}


def news_headlines(query: str, limit: int = 8) -> list[dict]:
    """Recent headlines mentioning a fighter or bout."""
    url = (f"{NEWS_RSS}?q={quote_plus(query + ' UFC')}"
           f"&hl=en-US&gl=US&ceid=US:en")
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return []
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return []
    items = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title:
            items.append({"title": title, "link": link})
    return items


def sentiment_score(headlines: list[dict]) -> float:
    """Crude polarity in [-1, 1] from keyword hits in headlines."""
    if not headlines:
        return 0.0
    score = 0.0
    for item in headlines:
        text = item["title"]
        score += 0.15 * len(POSITIVE.findall(text))
        score -= 0.15 * len(NEGATIVE.findall(text))
    return max(-1.0, min(1.0, score / max(len(headlines), 1)))


def soft_adjust_p_f1(
    p: float,
    f1_n_fights: float,
    f2_n_fights: float,
    f1_record: dict | None,
    f2_record: dict | None,
    f1_flags: dict | None,
    f2_flags: dict | None,
    f1_sentiment: float = 0.0,
    f2_sentiment: float = 0.0,
    has_market_odds: bool = False,
    youtube_lean: float | None = None,
    youtube_n_signals: int = 0,
    skill_p: float | None = None,
) -> tuple[float, list[str]]:
    """Nudge a skill probability with day-before context. Returns (p, notes).

    `youtube_lean` is in [-1, 1] (positive → fighter1). It only moves `p`
    when the *skill* probability (not the market stack) is near a coin flip
    — otherwise the note still records agreement/disagreement for the report.
    """
    notes: list[str] = []
    adjusted = float(p)

    if not has_market_odds:
        if f1_n_fights == 0 and f1_record and f2_n_fights > 0:
            prior = f1_record["win_pct"]
            adjusted = ((1 - DEBUT_PRIOR_WEIGHT) * adjusted
                        + DEBUT_PRIOR_WEIGHT * prior)
            notes.append(
                f"debut prior for f1 from pro record "
                f"{f1_record['wins']}-{f1_record['losses']}"
                + (f"-{f1_record['draws']}" if f1_record.get("draws") else "")
                + f" (win%≈{prior:.0%})")
        elif f2_n_fights == 0 and f2_record and f1_n_fights > 0:
            prior = 1.0 - f2_record["win_pct"]
            adjusted = ((1 - DEBUT_PRIOR_WEIGHT) * adjusted
                        + DEBUT_PRIOR_WEIGHT * prior)
            notes.append(
                f"debut prior for f2 from pro record "
                f"{f2_record['wins']}-{f2_record['losses']}"
                + (f"-{f2_record['draws']}" if f2_record.get("draws") else "")
                + f" (win%≈{f2_record['win_pct']:.0%})")
        elif (f1_n_fights == 0 and f2_n_fights == 0
              and f1_record and f2_record):
            gap = f1_record["win_pct"] - f2_record["win_pct"]
            adjusted = ((1 - DEBUT_PRIOR_WEIGHT) * adjusted
                        + DEBUT_PRIOR_WEIGHT * (0.5 + 0.5 * gap))
            notes.append(
                f"both debuts: pro win% {f1_record['win_pct']:.0%} vs "
                f"{f2_record['win_pct']:.0%}")

        sentiment = f1_sentiment - f2_sentiment
        if abs(sentiment) > 0.05:
            adjusted += SENTIMENT_WEIGHT * sentiment
            notes.append(f"headline buzz lean {sentiment:+.2f}")

    for corner, flags in (("f1", f1_flags), ("f2", f2_flags)):
        if flags and (flags.get("short_notice")
                      or flags.get("late_replacement")):
            adjusted = ((1 - SHORT_NOTICE_DAMPEN) * adjusted
                        + SHORT_NOTICE_DAMPEN * 0.5)
            label = ("short notice" if flags.get("short_notice")
                     else "late replacement")
            notes.append(f"{corner} flagged {label} — confidence dampened")

    if (youtube_lean is not None
            and youtube_n_signals >= YOUTUBE_MIN_SIGNALS
            and abs(float(youtube_lean)) > 0.15):
        reference = float(skill_p if skill_p is not None else p)
        if abs(reference - 0.5) <= YOUTUBE_SKILL_BAND:
            delta = YOUTUBE_WEIGHT * float(youtube_lean)
            adjusted += delta
            notes.append(
                f"YouTube lean {youtube_lean:+.2f} (n={youtube_n_signals}) "
                f"nudged p by {delta:+.3f} — skill was near a coin flip")
        else:
            notes.append(
                f"YouTube lean {youtube_lean:+.2f} (n={youtube_n_signals}) "
                f"noted but not applied — skill already decisive "
                f"({reference:.2f})")

    return max(0.02, min(0.98, adjusted)), notes


def bout_signals(payload: dict, f1_name: str, f2_name: str) -> dict:
    """One bout's saved context, oriented to (f1, f2).

    Keys: both fighters' context dicts, and the YouTube lean toward f1 with
    how many comments it was read from.
    """
    k1, k2 = normalize_name(f1_name), normalize_name(f2_name)
    fighters = payload.get("fighters", {})
    bouts = {(b.get("f1_key"), b.get("f2_key")): b for b in payload.get("bouts", [])}
    bout = bouts.get((k1, k2)) or bouts.get((k2, k1)) or {}
    youtube = bout.get("youtube") or {}
    lean = youtube.get("lean_f1")
    if lean is not None:
        # The lean is stored toward the context's own first fighter.
        lean = -float(lean) if bout.get("f1_key") == k2 else float(lean)
    return {"f1": fighters.get(k1, {}), "f2": fighters.get(k2, {}),
            "youtube_lean": lean, "youtube_n_signals": int(youtube.get("n_signals") or 0)}


def adjust_bout(payload: dict, f1_name: str, f2_name: str, p: float, *,
                f1_n_fights: float, f2_n_fights: float, has_market_odds: bool,
                skill_p: float) -> tuple[float, list[str]]:
    """``soft_adjust_p_f1`` for one bout, reading its inputs from a saved context."""
    signals = bout_signals(payload, f1_name, f2_name)
    c1, c2 = signals["f1"], signals["f2"]
    return soft_adjust_p_f1(
        p, f1_n_fights, f2_n_fights,
        c1.get("pro_record"), c2.get("pro_record"),
        c1.get("circumstances"), c2.get("circumstances"),
        float(c1.get("sentiment") or 0.0), float(c2.get("sentiment") or 0.0),
        has_market_odds=has_market_odds,
        youtube_lean=signals["youtube_lean"],
        youtube_n_signals=signals["youtube_n_signals"],
        skill_p=skill_p,
    )


def fetch_card_context(
    card_path: Path,
    wiki_page: str | None = None,
    media_cache: dict | None = None,
    delay: float = 1.0,
    youtube_api_key: str | None = None,
    youtube_videos_per_bout: int = 4,
    youtube_comments_per_video: int = 25,
) -> dict:
    """Scrape + assemble the day-before context file for one card YAML."""
    import yaml

    with open(card_path, encoding="utf-8") as fh:
        card = yaml.safe_load(fh)

    event = card.get("event", card_path.stem)
    # An unquoted `date: 2026-08-08` in a hand-written card comes back from
    # PyYAML as a datetime.date, which json.dumps refuses at save time —
    # after the whole scrape (and its YouTube quota) has already been spent.
    # predict.py's load_card coerces the same field; do it here too.
    iso_date = str(card.get("date"))
    fights = card.get("fights", [])
    names = [n for f in fights for n in (f["fighter1"], f["fighter2"])]
    page = wiki_page or event
    # Optional `aliases: {"Wikipedia name": "card name"}` block, for fighters
    # the sources spell differently (see build_resolver).
    aliases = card.get("aliases") or {}

    try:
        background = event_background(page)
    except Exception as exc:  # noqa: BLE001 — context is best-effort
        background = f"(background unavailable: {exc})"

    circumstances = parse_circumstances(background, names, aliases)

    fighters: dict[str, dict] = {}
    for name in names:
        key = normalize_name(name)
        time.sleep(delay)
        try:
            wiki = _wiki_summary(name)
        except requests.RequestException:
            wiki = {}
        media = (media_cache or {}).get(key, {})
        pro = parse_pro_record(media.get("record")) or wiki.get("pro_record")
        headlines = news_headlines(name)
        fighters[key] = {
            "name": name,
            "pro_record": pro,
            "ufc_record": media.get("record"),
            "styles": wiki.get("styles") or [],
            "summary": wiki.get("summary"),
            "description": wiki.get("description") or media.get("description"),
            "circumstances": circumstances.get(key, {}),
            "headlines": headlines,
            "sentiment": sentiment_score(headlines),
        }

    youtube_by_pair: dict[tuple[str, str], dict] = {}
    if youtube_api_key:
        from octagon.scraping import youtube as yt

        for bout_yt in yt.fetch_card_youtube(
                youtube_api_key, fights, event,
                max_videos=youtube_videos_per_bout,
                max_comments=youtube_comments_per_video):
            key = (normalize_name(bout_yt["fighter1"]),
                   normalize_name(bout_yt["fighter2"]))
            youtube_by_pair[key] = bout_yt

    bout_context = []
    for fight in fights:
        f1, f2 = fight["fighter1"], fight["fighter2"]
        k1, k2 = normalize_name(f1), normalize_name(f2)
        pair_news = news_headlines(f"{f1} vs {f2}", limit=6)
        yt_buzz = youtube_by_pair.get((k1, k2))
        bout_context.append({
            "fighter1": f1,
            "fighter2": f2,
            "weight_class": fight.get("weight_class"),
            "headlines": pair_news,
            "sentiment": sentiment_score(pair_news),
            "f1_key": k1,
            "f2_key": k2,
            "youtube": None if yt_buzz is None else {
                "lean_f1": yt_buzz["lean_f1"],
                "n_signals": yt_buzz["n_signals"],
                "n_videos": yt_buzz["n_videos"],
                "n_comments": yt_buzz["n_comments"],
                "preferred": yt_buzz["preferred"],
                "title_picks": yt_buzz.get("title_picks") or [],
                "videos": [
                    {"title": v["title"], "channel": v["channel"],
                     "url": v["url"]}
                    for v in (yt_buzz.get("videos") or [])[:4]
                ],
            },
        })

    payload = {
        "event": event,
        "date": iso_date,
        "wiki_page": page,
        "fetched_at": date.today().isoformat(),
        "background": background[:4000],
        "fighters": fighters,
        "bouts": bout_context,
        "slug": slug(event).replace("-", "_"),
        "youtube_enabled": bool(youtube_api_key),
    }
    save_context(card_path, payload)
    return payload
