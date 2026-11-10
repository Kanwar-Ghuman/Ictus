"""Matching one fighter across ESPN, Kalshi, Wikipedia and the model card.

The sources disagree on accents, hyphens, middle names, transliteration,
name order, and nicknames ("Bia" for "Beatriz").

Two levels:

* ``same_name`` is strict. The surname matches and the given names differ only
  in ways a spelling can.
* ``orient`` matches a whole fight. It accepts a nickname on one side as long
  as the other fighter matches strictly, because two different people with one
  surname do not face the same opponent on the same night.
"""

from __future__ import annotations

import unicodedata


def normalized_name(name: str) -> str:
    """Lower-case, accent-free, punctuation-free, single-spaced."""
    # A hyphen is a space, so "Cortes-Acosta" and "Cortes Acosta" are one fighter.
    folded = unicodedata.normalize("NFKD", name).casefold().replace("-", " ")
    return " ".join("".join(
        c for c in folded
        if not unicodedata.combining(c) and (c.isalnum() or c.isspace())
    ).split())


def _skeleton(name: str) -> str:
    return "".join(c for c in name if c not in "aeiouy ")


def same_name(a: str, b: str) -> bool:
    x, y = normalized_name(a), normalized_name(b)
    if not x or not y:
        return False
    if x == y or x.replace(" ", "") == y.replace(" ", ""):
        return True
    xt, yt = x.split(), y.split()
    if sorted(xt) == sorted(yt):
        return True  # "Zhang Mingyang" and "Mingyang Zhang"
    if not xt or not yt or xt[-1] != yt[-1]:
        return False
    shorter, longer = (xt, yt) if len(xt) <= len(yt) else (yt, xt)
    if len(shorter) >= 2 and set(shorter) <= set(longer):
        return True
    sx, sy = _skeleton(x), _skeleton(y)
    return len(sx) >= 4 and sx == sy


def loose_name(a: str, b: str) -> bool:
    """Plausibly one fighter: the same surname, or a shared distinctive name.

    Never enough on its own. ``orient`` and ``identifies`` use it only with a
    second fighter to anchor the match.
    """
    if same_name(a, b):
        return True
    x, y = normalized_name(a).split(), normalized_name(b).split()
    if not x or not y:
        return False
    if len(x[-1]) >= 3 and x[-1] == y[-1]:
        return True
    return any(len(token) >= 4 and token in y for token in x)


def orient(f1: str, f2: str, a: str, b: str) -> bool | None:
    """Is the fight (f1, f2) the fight (a, b)?

    True when f1 is a and f2 is b, False when they are the other way round,
    None when it is a different fight or the answer is unclear.
    """
    strict = _orientation(same_name, same_name, f1, f2, a, b)
    if strict is not None:
        return strict
    # One fighter must still match strictly; the other may be a nickname.
    one_strict = [_orientation(first, second, f1, f2, a, b)
                  for first, second in ((same_name, loose_name), (loose_name, same_name))]
    answers = {answer for answer in one_strict if answer is not None}
    return answers.pop() if len(answers) == 1 else None


def _orientation(match_1, match_2, f1: str, f2: str, a: str, b: str) -> bool | None:
    straight = match_1(f1, a) and match_2(f2, b)
    swapped = match_1(f1, b) and match_2(f2, a)
    return straight if straight != swapped else None


def same_pair(pair: tuple[str, str], other: tuple[str, str]) -> bool:
    return orient(pair[0], pair[1], other[0], other[1]) is not None


def identifies(label: str, fighter: str, opponent: str) -> bool:
    """Does a market label name ``fighter`` and not the opponent?"""
    if same_name(label, fighter):
        return not same_name(label, opponent)
    return loose_name(label, fighter) and not loose_name(label, opponent)


def fighter_in_rules(fighter: str, rules: str) -> bool:
    """Does a market's settlement text name this fighter in full?"""
    folded = normalized_name(fighter)
    text = normalized_name(rules)
    if not folded or not text:
        return False
    if f" {folded} " in f" {text} ":
        return True
    tokens = folded.split()
    words = text.split()
    if len(tokens) < 2 or tokens[-1] not in words:
        return False
    if all(token in words for token in tokens):
        return True
    skeleton = _skeleton(folded)
    return len(skeleton) >= 4 and skeleton in _skeleton(text)


def rules_name_fight(rules: str, f1: str, f2: str) -> bool:
    """Does a market's settlement text describe this fight?

    Both fighters named in full, or one in full and the other by a surname the
    first does not share. That lets "Bia Mesquita" stand for Beatriz Mesquita
    without accepting a market for a different opponent.
    """
    full = [fighter_in_rules(name, rules) for name in (f1, f2)]
    if all(full):
        return True
    if not any(full):
        return False
    surnames = [normalized_name(name).split()[-1:] for name in (f1, f2)]
    if not all(surnames) or surnames[0] == surnames[1]:
        return False
    missing = surnames[full.index(False)][0]
    return len(missing) >= 3 and missing in normalized_name(rules).split()
