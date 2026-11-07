"""Closing-line value and settlement P&L from a trading journal.

Paper fills are not returns. The interval resamples whole events, because
fights on one card are not independent bets. A fill with no later mid is
omitted from closing-line value. A fill with no settlement is omitted from P&L.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import numpy as np

from octagon.trading.risk import ZERO, taker_fee

FILLED = {"paper", "demo", "live"}


@dataclass(frozen=True)
class Fill:
    event_id: str
    ticker: str
    side: str
    fill_price: Decimal
    contracts: Decimal
    fee: Decimal
    close_mid: Decimal | None
    settlement: str | None
    action: str


def closing_line_cents(fill: Fill) -> Decimal | None:
    """Cents the side's later mid sits above the price we paid. Higher is better."""
    if fill.close_mid is None:
        return None
    return (fill.close_mid - fill.fill_price) * 100


def settlement_pnl(fill: Fill) -> Decimal | None:
    """Dollars after the fee. Draws pay 50 cents a contract."""
    if fill.settlement not in {"yes", "no", "draw"}:
        return None
    if fill.settlement == "draw":
        payout = Decimal("0.5") * fill.contracts
    elif fill.settlement == fill.side:
        payout = fill.contracts
    else:
        payout = ZERO
    return payout - fill.fill_price * fill.contracts - fill.fee


def summarize(fills: list[Fill], *, seed: int = 42, n_bootstrap: int = 2000) -> dict:
    """Mean closing-line value, settlement ROI, and an event-block interval on ROI."""
    clv = [closing_line_cents(f) for f in fills]
    clv = [c for c in clv if c is not None]
    pnl = [(f.event_id, settlement_pnl(f), f.fill_price * f.contracts + f.fee) for f in fills]
    pnl = [(e, p, c) for e, p, c in pnl if p is not None]
    by_event: dict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)
    for event, profit, cost in pnl:
        by_event[event].append((profit, cost))
    events = list(by_event)
    roi = None
    interval = None
    if events:
        total_profit = sum((p for rows in by_event.values() for p, _ in rows), ZERO)
        total_cost = sum((c for rows in by_event.values() for _, c in rows), ZERO)
        roi = total_profit / total_cost if total_cost else None
        if n_bootstrap > 0 and total_cost:
            rng = np.random.default_rng(seed)
            samples = []
            for _ in range(n_bootstrap):
                picked = rng.integers(0, len(events), len(events))
                profit = sum((p for i in picked for p, _ in by_event[events[i]]), ZERO)
                cost = sum((c for i in picked for _, c in by_event[events[i]]), ZERO)
                if cost:
                    samples.append(float(profit / cost))
            if samples:
                lo, hi = np.percentile(samples, [2.5, 97.5])
                interval = (float(lo), float(hi))
    mean_clv = sum(clv, ZERO) / len(clv) if clv else None
    return {
        "n_fills": len(fills),
        "n_with_close": len(clv),
        "mean_clv_cents": mean_clv,
        "n_settled": len(pnl),
        "n_events": len(events),
        "roi": roi,
        "roi_ci95": interval,
    }


def _dec(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        out = Decimal(str(value))
    except Exception:
        return None
    return out if out.is_finite() else None


def fills_from_journal(rows: list[dict], settlements: dict[str, str] | None = None) -> list[Fill]:
    """Fills from observation records, using the last pre-fight mid as the close.

    ``settlements`` maps a ticker to ``yes``, ``no``, or ``draw``.
    """
    settlements = settlements or {}
    event_id = ""
    yes_is_f1: dict[str, bool] = {}
    last_mid: dict[str, Decimal] = {}
    fills: list[Fill] = []
    for row in rows:
        kind, data = row.get("kind"), row.get("data")
        if kind == "configuration" and isinstance(data, dict):
            event_id = str(data.get("espn_event_id") or event_id)
            for mapping in data.get("mappings") or []:
                if not isinstance(mapping, dict) or not mapping.get("ticker"):
                    continue
                yes_is_f1[mapping["ticker"]] = mapping.get("yes_fighter") == mapping.get("f1")
        elif kind == "prefight_price" and isinstance(data, dict):
            mid = _dec(data.get("p_f1"))
            ticker = data.get("ticker")
            if ticker and mid is not None and 0 < mid < 1:
                last_mid[ticker] = mid
        elif kind == "decisions" and isinstance(data, list):
            for decision in data:
                if not isinstance(decision, dict) or decision.get("action") not in FILLED:
                    continue
                ticker = decision.get("ticker")
                side = decision.get("side")
                price = _dec(decision.get("price_dollars"))
                count = _dec(decision.get("contracts"))
                if not ticker or side not in {"yes", "no"} or price is None or count is None:
                    continue
                fee = _dec(decision.get("fee_dollars"))
                if fee is None:
                    fee = taker_fee(price, int(count), Decimal(1))
                f1_mid = last_mid.get(ticker)
                close = None
                if f1_mid is not None:
                    yes_mid = f1_mid if yes_is_f1.get(ticker, True) else 1 - f1_mid
                    close = yes_mid if side == "yes" else 1 - yes_mid
                fills.append(Fill(
                    event_id=str(decision.get("event_id") or event_id),
                    ticker=ticker, side=side, fill_price=price, contracts=count, fee=fee,
                    close_mid=close, settlement=settlements.get(ticker),
                    action=decision["action"],
                ))
    return fills


def load_journal(path: Path, settlements_path: Path | None = None) -> dict:
    rows = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    settlements = {}
    if settlements_path is not None:
        raw = json.loads(settlements_path.read_text())
        settlements = {str(k): str(v) for k, v in raw.items()}
    fills = fills_from_journal(rows, settlements)
    report = summarize(fills)
    report["mean_clv_cents"] = _plain(report["mean_clv_cents"])
    report["roi"] = _plain(report["roi"])
    return report


def _plain(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Closing-line value and settlement P&L")
    parser.add_argument("journal", type=Path, help="observations.jsonl from a trading state dir")
    parser.add_argument("--settlements", type=Path, default=None,
                        help="JSON object of ticker to yes, no, or draw")
    args = parser.parse_args(argv)
    print(json.dumps(load_journal(args.journal, args.settlements), indent=2))


if __name__ == "__main__":
    main()
