"""Is everything ready for fight night? A read-only checklist.

    python -m octagon.trading.check              # practice
    python -m octagon.trading.check --live 70    # real money, $70 on the event

Nothing here places an order or changes a file. Each line is OK, a warning
(the bot runs, but worse than it could), or a problem (fix it first). The
command exits non-zero only on a problem.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from octagon.config import load_config, load_dotenv, project_root, resolve_path

OK, WARN, FAIL = "ok", "warning", "problem"
MARKS = {OK: "  OK      ", WARN: "  WARNING ", FAIL: "  PROBLEM "}
# The UFC runs most weekends, so fight data older than this is missing an event.
STALE_DATA_DAYS = 9
# A card counts as "this weekend's" when it is dated this close to today.
CARD_DAYS_AHEAD = 7


@dataclass(frozen=True)
class Line:
    level: str
    text: str
    fix: str = ""


def fight_data(db_path: Path, today: date) -> Line:
    """How recent the fights the model learned from are."""
    if not db_path.exists():
        return Line(FAIL, "No fight database.", "cd model && uv run python -m octagon refresh-data")
    with sqlite3.connect(db_path) as conn:
        latest = conn.execute("SELECT MAX(date) FROM fights").fetchone()[0]
    if not latest:
        return Line(FAIL, "The fight database is empty.", "cd model && uv run python -m octagon refresh-data")
    age = (today - date.fromisoformat(latest[:10])).days
    if age > STALE_DATA_DAYS:
        return Line(WARN, f"Fight data ends {latest[:10]}, {age} days ago. Recent fights are missing.",
                    "cd model && uv run python -m octagon refresh-data && uv run python -m octagon train")
    return Line(OK, f"Fight data is current (through {latest[:10]}).")


def model_files(artifacts: Path, features: Path) -> list[Line]:
    """The trained models exist and still match the fight data.

    New fights alone never invalidate the model: predictions refit on them.
    It has to be refit only when older records changed, which a data refresh
    sometimes brings. Predicting refuses to run until then.
    """
    lines = []
    model = artifacts / "gbm.joblib"
    refit = "cd model && uv run python -m octagon train --reuse-params"
    if not model.exists():
        lines.append(Line(FAIL, "No trained prediction model.", "cd model && uv run python -m octagon train"))
    elif not features.exists():
        lines.append(Line(FAIL, "No feature table.", "cd model && uv run python -m octagon refresh-data"))
    elif not _model_matches(model, features):
        lines.append(Line(FAIL, "The prediction model no longer matches the fight data, so new "
                                "predictions can't be built.", refit))
    else:
        lines.append(Line(OK, "Prediction model matches the current fight data."))
    if (artifacts / "inplay.json").exists():
        lines.append(Line(OK, "In-fight model is present."))
    else:
        lines.append(Line(WARN, "No in-fight model, so the bot can only bet before fights.",
                          "cd model && uv run python -m octagon train-inplay"))
    return lines


def _model_matches(model: Path, features: Path) -> bool:
    import joblib
    import pandas as pd

    from octagon.lineage import verify_artifact_snapshot

    frame = pd.read_parquet(features)
    try:
        verify_artifact_snapshot(frame[frame["label"].notna()], joblib.load(model))
    except SystemExit:
        return False
    return True


def upcoming_card(cards: list[dict], reports: Path, model: Path, today: date) -> Line:
    """This weekend's predictions exist and came from the current model."""
    soon = [c for c in cards
            if 0 <= (date.fromisoformat(str(c["date"])[:10]) - today).days <= CARD_DAYS_AHEAD]
    if not soon:
        return Line(OK, "No predictions saved for this weekend yet. The bot builds them when it starts.")
    card = min(soon, key=lambda c: c["date"])
    frozen = reports / f"card_predictions_{card['slug']}.parquet"
    if not frozen.exists():
        return Line(OK, f"{card['slug']}: card saved, predictions get built when the bot starts.")
    if model.exists() and frozen.stat().st_mtime < model.stat().st_mtime:
        return Line(WARN, f"{card['slug']}: predictions are older than the model.",
                    "./ictus.sh prepare")
    made = datetime.fromtimestamp(frozen.stat().st_mtime).date()
    days_out = (date.fromisoformat(str(card["date"])[:10]) - made).days
    if days_out > 2:
        return Line(WARN, f"{card['slug']}: predictions were made {days_out} days before the card. "
                          "Opponents can change until the weigh-ins.",
                    "Rebuild them the day before, after the weigh-ins: ./ictus.sh prepare")
    return Line(OK, f"{card['slug']}: predictions are current.")


def fight_feed() -> Line:
    try:
        from octagon.live.gateway import snapshot_once

        snapshot = snapshot_once()
    except Exception as exc:  # noqa: BLE001 — any failure here is the finding
        return Line(FAIL, f"Can't read ESPN's fight feed ({type(exc).__name__}).",
                    "Check the internet connection and try again.")
    bouts = snapshot.get("data") or []
    name = (snapshot.get("meta") or {}).get("event_name") or "an event"
    priced = sum(1 for b in bouts if (b.get("fighter_a") or {}).get("odds")
                 and (b.get("fighter_b") or {}).get("odds"))
    if not bouts:
        return Line(WARN, "ESPN's fight feed is up but lists no fights yet.")
    level = OK if priced else WARN
    return Line(level, f"ESPN feed: {name}, {len(bouts)} fights, sportsbook odds on {priced}.",
                "" if priced else "No odds yet means no pre-fight bets. They usually appear days ahead.")


def kalshi(cap: Decimal | None) -> list[Line]:
    """Markets are reachable. With a cap: the keys work and the account can cover it."""
    from octagon.trading.kalshi import KalshiClient, KalshiError

    lines = []
    client = KalshiClient.from_env("production", live_enabled=False)
    try:
        markets = client.list_open_markets("KXUFCFIGHT")
        lines.append(Line(OK if markets else WARN,
                          f"Kalshi lists {len(markets) // 2} UFC fights right now."))
        if cap is not None:
            if not (os.environ.get("KALSHI_API_KEY_ID") and os.environ.get("KALSHI_PRIVATE_KEY_PATH")):
                lines.append(Line(FAIL, "No Kalshi keys in model/.env, so real-money mode can't start.",
                                  "Add KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH."))
            else:
                cash = Decimal(str(client.get_balance().get("balance"))) / 100
                if cash < cap:
                    lines.append(Line(FAIL, f"Kalshi cash is ${cash:.2f}, less than the ${cap} limit.",
                                      "Deposit more or start with a lower limit."))
                else:
                    lines.append(Line(OK, f"Kalshi keys work and the account has ${cash:.2f} in cash."))
    except (KalshiError, RuntimeError, ValueError, ArithmeticError) as exc:
        lines.append(Line(FAIL, f"Kalshi check failed: {exc}", "Check the keys in model/.env."))
    finally:
        client.close()
    return lines


def run_checks(cap: Decimal | None, today: date | None = None) -> list[Line]:
    from octagon.api import findings

    today = today or date.today()
    cfg = load_config()
    artifacts = resolve_path("artifacts")
    features = resolve_path(cfg["data"]["processed_dir"]) / "features.parquet"
    lines = [fight_data(resolve_path(cfg["data"]["db_path"]), today)]
    lines += model_files(artifacts, features)
    lines.append(upcoming_card(findings.list_cards(), resolve_path("reports"),
                               artifacts / "gbm.joblib", today))
    lines.append(fight_feed())
    lines += kalshi(cap)
    if not (project_root().parent / "frontend" / "node_modules").exists():
        lines.append(Line(WARN, "The dashboard is not installed yet. The launcher installs it on first run."))
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only fight-night readiness check")
    parser.add_argument("--live", type=Decimal, default=None, metavar="DOLLARS",
                        help="also check the Kalshi keys and that the account covers this limit")
    args = parser.parse_args(argv)
    load_dotenv()
    lines = run_checks(args.live)
    for line in lines:
        print(MARKS[line.level] + line.text)
        if line.fix:
            print("            Fix: " + line.fix)
    problems = sum(line.level == FAIL for line in lines)
    warnings = sum(line.level == WARN for line in lines)
    print()
    if problems:
        print(f"Not ready: {problems} problem(s) to fix first.")
    elif warnings:
        print(f"Ready to run, with {warnings} warning(s) worth fixing before fight night.")
    else:
        print("Ready for fight night.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
