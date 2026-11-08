"""Event-budget coordinator. In-play execution runs only when a model is attached.

Production (real-money) orders run only in ``live`` mode, which requires an
explicitly live-enabled production client and a hard per-event dollar cap.

Every decision requires a freshly observed ESPN bout, explicit market identity,
current exchange metadata and executable depth. A ledger reservation is durable
before an order can leave the process. Budget is spread across the card: each
fight still to be decided gets a slice of the money left, scaled by edge
strength. Missed or partly filled orders are retried (bounded) while the edge lasts.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from octagon.inplay.live import BREAK_STATUS, fight_progress, held_without_threat
from octagon.trading.kalshi import KalshiClient, KalshiOrderBook, KalshiTransportError
from octagon.trading.ledger import Ledger
from octagon.trading.risk import (
    RiskPolicy, bout_allowance, decimal, edge_of, money, size_candidate, taker_fee,
)
from octagon.trading.signal import lag_block_reason

READINESS_REASONS = [
    "No independently verified Kalshi trading edge: live orders can lose the whole budget.",
    "Pre-fight orders use the frozen card pick and abstain when the card has no vig-free line.",
    "In-fight orders reprice from the live clock. A fighter already held under 50 cents is not flipped.",
    "Historical sportsbook backtests do not establish profitable Kalshi execution.",
    "Paper fills are simulations; demo fills use Kalshi's separate test environment.",
]
IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
IDLE_DECISION_SECONDS = 2.0
# A contract bought under 50 cents is the side we keep.
HIGH_ODDS_PRICE = Decimal("0.50")


def normalized_name(name: str) -> str:
    # A hyphen is a space, so "Cortes-Acosta" and "Cortes Acosta" are one fighter.
    folded = unicodedata.normalize("NFKD", name).casefold().replace("-", " ")
    return " ".join("".join(
        c for c in folded
        if not unicodedata.combining(c) and (c.isalnum() or c.isspace())
    ).split())


def timestamp(value: Any) -> float:
    if not isinstance(value, str):
        raise ValueError("Missing source timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        raise ValueError("Invalid source timestamp") from None
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return parsed.timestamp()


def age_is_valid(value: Any, now: float, maximum: float) -> bool:
    try:
        age = now - timestamp(value)
    except ValueError:
        return False
    return -2 <= age <= maximum


def _probability(value, label: str) -> Decimal:
    try:
        probability = decimal(value)
    except (ValueError, ArithmeticError):
        raise ValueError(f"A finite {label} probability is required") from None
    if not 0 < probability < 1:
        raise ValueError(f"A finite {label} probability is required")
    return probability


def rest_quotes(payload: dict) -> dict[str, tuple[Decimal, Decimal]]:
    """Read a standalone current REST book without mixing it with WS deltas."""
    book = payload.get("orderbook_fp")
    if not isinstance(book, dict):
        raise ValueError("Kalshi fixed-point order book unavailable")
    best = {}
    for side in ("yes", "no"):
        levels = book.get(side + "_dollars")
        if not isinstance(levels, list) or not levels:
            raise ValueError("Two-sided market liquidity is required")
        parsed = []
        for row in levels:
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError("Malformed order book")
            price, count = map(decimal, row)
            if not 0 < price < 1 or count <= 0:
                raise ValueError("Invalid order-book level")
            parsed.append((price, count))
        if len({p for p, _ in parsed}) != len(parsed):
            raise ValueError("Duplicate order-book price")
        best[side] = max(parsed)
    if best["yes"][0] + best["no"][0] > 1:
        raise ValueError("Crossed order book")
    return {"yes": (1 - best["no"][0], best["no"][1]),
            "no": (1 - best["yes"][0], best["yes"][1])}


class TradingEngine:
    def __init__(self, ledger: Ledger, client: KalshiClient, *, mode: str = "paper",
                 policy: RiskPolicy | None = None, record=None,
                 max_budget: Decimal | None = None, inplay=None,
                 prefight_path: Path | None = None):
        if mode not in {"paper", "demo", "live"}:
            raise ValueError("Mode must be paper, demo or live")
        if mode == "demo" and client.environment != "demo":
            raise ValueError("Demo orders must use the demo exchange")
        if mode == "live":
            if client.environment != "production" or getattr(client, "live_enabled", False) is not True:
                raise ValueError("Live mode requires a live-enabled production client")
            if max_budget is None:
                raise ValueError("Live mode requires a hard maximum event budget")
        self.max_budget = money(max_budget) if max_budget is not None else None
        self.ledger, self.client, self.mode = ledger, client, mode
        # Order and fill records can lag an IOC acknowledgement by a moment.
        # Re-read briefly before pausing; never resubmit.
        self.reconcile_delays: tuple[float, ...] = (0.5, 1.0, 1.5)
        self.sleep = time.sleep
        # Between-rounds model (None = pre-fight only, the default).
        self.inplay = inplay
        self.prefight_path = prefight_path
        self.prefight: dict[str, dict] = self._load_prefight()
        self.prefight_checked: dict[str, float] = {}
        self.break_seen: dict[tuple[str, int], float] = {}
        # Monotonic time of the last order attempt per attempt family.
        self.last_attempt: dict[str, float] = {}
        self.policy = policy or RiskPolicy()
        self.record = record or (lambda kind, data: None)
        self.running = threading.Event()
        self.lock = threading.RLock()
        self.control_lock = threading.RLock()
        self.stop_generation = 0
        self.instance_id = str(uuid.uuid4())
        self.feed_lock = threading.RLock()
        self.book_lock = threading.RLock()
        self.book = KalshiOrderBook()
        self.feed: dict | None = None
        self.feed_received: float | None = None
        self.feed_connected = False
        self.market_connected = False
        self.market_received: float | None = None
        self.market_stream_required = False
        self.decisions: list[dict] = []
        self.message = "Paused. Configure a budget and explicitly confirm each winner market."
        self.session_id: str | None = None
        self.config: dict | None = None
        old = self.ledger.latest(mode)
        if old:
            self.session_id = old["id"]
            self.config = json.loads(old["config"])
            self.message = "Recovered journal. Paused after restart; reconcile before starting."

    def configure(self, request: dict, card: dict) -> dict:
        with self.lock:
            if self.running.is_set():
                raise ValueError("Stop the session before changing its budget or mappings")
            for field in ("card_slug", "espn_event_id"):
                if not IDENTIFIER.fullmatch(str(request.get(field, ""))):
                    raise ValueError(f"Invalid {field}")
            if request["card_slug"] != card.get("slug"):
                raise ValueError("Card identity mismatch")
            budget = money(request["budget_dollars"])
            if not 0 < budget <= 1_000_000:
                raise ValueError("Budget must be between $0.01 and $1,000,000")
            if self.max_budget is not None and budget > self.max_budget:
                raise ValueError(f"Budget exceeds this service's hard cap of ${self.max_budget}")
            mappings = request.get("mappings")
            if not isinstance(mappings, list) or not 1 <= len(mappings) <= 30:
                raise ValueError("Configure between 1 and 30 individual winner markets")
            by_pair = {(b["f1"], b["f2"]): b for b in card["bouts"]}
            mapped, seen_tickers, seen_bouts, seen_pairs = [], set(), set(), set()
            for mapping in mappings:
                if mapping.get("confirmed") is not True:
                    raise ValueError("Confirm each market's winner, event and settlement rules")
                f1, f2 = mapping.get("f1"), mapping.get("f2")
                bout = by_pair.get((f1, f2))
                if bout is None or not f1 or not f2 or f1 == f2:
                    raise ValueError("Mapped fighters must exactly match the selected model card")
                if mapping.get("yes_fighter") not in (f1, f2):
                    raise ValueError("YES fighter must be one of the two fighters")
                ticker, bout_id = mapping.get("ticker", ""), mapping.get("bout_id", "")
                if not IDENTIFIER.fullmatch(ticker) or not IDENTIFIER.fullmatch(bout_id):
                    raise ValueError("Invalid Kalshi ticker or ESPN bout ID")
                if ticker in seen_tickers or bout_id in seen_bouts or (f1, f2) in seen_pairs:
                    raise ValueError("Each fight and market can be mapped only once")
                seen_tickers.add(ticker)
                seen_bouts.add(bout_id)
                seen_pairs.add((f1, f2))
                p_skill = _probability(bout.get("p_skill"), "skill-model")
                p_market = bout.get("p_market")
                market_text = None
                if p_market is not None:
                    market_text = str(_probability(p_market, "market"))
                raw_pick = bout.get("p_f1_wins")
                order_p = p_skill if raw_pick is None else _probability(raw_pick, "initial-pick")
                layer = "initial"
                p_book = bout.get("p_book")
                book_text = None if p_book is None else str(_probability(p_book, "sportsbook"))
                market = self.client.get_market(ticker)
                self._validate_identity(market, mapping)
                mapped.append({key: mapping[key] for key in (
                    "ticker", "bout_id", "f1", "f2", "yes_fighter", "confirmed"
                )} | {"probability_f1": str(order_p),
                      "p_skill": str(p_skill),
                      "p_market": market_text,
                      "p_book": book_text,
                      "probability_layer": layer,
                      "f1_ufc_fights": bout.get("f1_ufc_fights"),
                      "scheduled_rounds": bout.get("scheduled_rounds"),
                      "f2_ufc_fights": bout.get("f2_ufc_fights"),
                      "market_identity": self._market_identity(market)})
            config = {
                "card_slug": request["card_slug"], "espn_event_id": request["espn_event_id"],
                "budget_dollars": str(budget), "card_date": str(card["date"]),
                "mappings": mapped,
            }
            # Never drop unresolved exposure by switching events.
            if self.session_id and any(o["reserved"] for o in self.ledger.orders(self.session_id)):
                raise ValueError("Resolve pending orders before reconfiguring")
            self.session_id = self.ledger.configure(config, self.mode)
            self.config = config
            self.decisions = []
            self.message = "Configured and paused. Budget is a spending ceiling, not a target."
            self.record("configuration", config)
            return self.status()

    @staticmethod
    def _market_identity(market: dict) -> str:
        fields = {key: market.get(key) for key in (
            "ticker", "event_ticker", "market_type", "yes_sub_title", "no_sub_title",
            "title", "subtitle", "rules_primary", "rules_secondary",
        )}
        return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _validate_identity(market: dict, mapping: dict):
        if market.get("ticker") != mapping["ticker"] or market.get("market_type") != "binary":
            raise ValueError("Expected the exact binary winner market")
        if market.get("mve_collection_ticker") or market.get("mve_selected_legs"):
            raise ValueError("Combo markets require joint probabilities and are unsupported")
        from octagon.trading.autoplan import fighter_in_rules, same_name

        if not same_name(str(market.get("yes_sub_title", "")), mapping["yes_fighter"]):
            raise ValueError("Market YES label must exactly identify the selected fighter")
        if not market.get("rules_primary") or not market.get("event_ticker"):
            raise ValueError("Market settlement rules and event identity are required")
        if any(not fighter_in_rules(mapping[key], market["rules_primary"]) for key in ("f1", "f2")):
            raise ValueError("Market rules must identify both exact fighters in this bout")

    def update_feed(self, message: dict):
        with self.feed_lock:
            self.feed = copy.deepcopy(message)
            self.feed_received = time.monotonic()
            self.feed_connected = True
            # Persist terminal observations even while paused and even if later
            # source packets regress to 'scheduled'.
            if self.config and self.session_id and isinstance(message, dict):
                if (message.get("meta") or {}).get("event_id") == self.config["espn_event_id"]:
                    for bout in message.get("data") or []:
                        if not isinstance(bout, dict) or bout.get("status") == "scheduled":
                            continue
                        if self.inplay is not None and bout.get("status") == "in_progress":
                            round_k = bout.get("round")
                            if bout.get("status_detail") == BREAK_STATUS and isinstance(round_k, int):
                                self.break_seen.setdefault((str(bout.get("bout_id")), round_k),
                                                           time.monotonic())
                            continue
                        self.ledger.block_bout(self.session_id, str(bout.get("bout_id")),
                                               "Bout observed started or unavailable")
        self.record("fight_feed", message)

    def disconnect_feed(self):
        with self.feed_lock:
            self.feed_connected = False
            self.feed_received = None

    def update_book(self, message: dict):
        with self.book_lock:
            changed = self.book.apply(message)
            if changed:
                self.market_received = time.monotonic()
            self.market_connected = True
        self.record("market_feed", message)

    def disconnect_book(self):
        with self.book_lock:
            self.book.disconnect()
            self.market_connected = False
            self.market_received = None

    def config_version(self) -> str | None:
        if not self.config or not self.session_id:
            return None
        return hashlib.sha256(json.dumps(
            {"session": self.session_id, "config": self.config, "instance": self.instance_id,
             "control_epoch": self.stop_generation},
            sort_keys=True
        ).encode()).hexdigest()

    def start(self, *, session_id: str | None = None, config_version: str | None = None) -> dict:
        with self.control_lock:
            generation = self.stop_generation
        with self.lock:
            if not self.config or not self.session_id:
                raise ValueError("Configure an event first")
            if session_id is not None and session_id != self.session_id:
                raise ValueError("Session changed; review and save the event configuration again")
            if config_version is not None and config_version != self.config_version():
                raise ValueError("Budget or mappings changed; review and save the configuration again")
            if any(o["reserved"] for o in self.ledger.orders(self.session_id)):
                raise ValueError("Unresolved order reservation: reconcile before starting")
            if self.mode != "paper":
                # Fail closed if the account already has positions or orders in
                # these markets; local budgets cannot account for manual activity.
                # Completed/attempted bouts can never be traded again, including
                # after settlement. Preflight account checks apply to remaining
                # bouts; settling an earlier winner must not prevent resuming.
                attempted = {o["ticker"] for o in self.ledger.orders(self.session_id)}
                tickers = {m["ticker"] for m in self.config["mappings"]} - attempted
                orders = self.client.list_orders(status="resting")
                positions = self.client.list_positions()
                if any(o.get("ticker") in tickers for o in orders):
                    raise ValueError("Cancel existing resting orders in these markets first")
                own_positions = {ticker: Decimal(0) for ticker in tickers}
                for own_order in self.ledger.orders(self.session_id):
                    if own_order["status"] in {"demo_filled", "filled"} and own_order["ticker"] in tickers:
                        own_positions[own_order["ticker"]] += decimal(own_order["filled_count"]) * (
                            1 if own_order["side"] == "yes" else -1
                        )
                observed_positions = {ticker: Decimal(0) for ticker in tickers}
                for position in positions:
                    if position.get("ticker") in tickers:
                        observed_positions[position["ticker"]] = decimal(position.get("position_fp"))
                if observed_positions != own_positions:
                    raise ValueError("Account holdings differ from the journal; reconcile account activity")
                self.client.get_balance()
            with self.control_lock:
                if generation != self.stop_generation:
                    raise ValueError("Start was canceled by Stop; review the session before resuming")
                self.running.set()
                self.message = (f"{self.mode.title()} session running. "
                                + ("In-fight reprices from the live clock and stats."
                                   if self.inplay is not None
                                   else "In-progress bouts remain blocked."))
            return self.status()

    def stop(self) -> dict:
        # Set before acquiring the tick lock so a slow read cannot delay the stop.
        with self.control_lock:
            self.stop_generation += 1
            self.running.clear()
            self.message = "Stopped. Pending IOC results remain reserved until reconciled."
        return self.status()

    def _feed_reason(self, mapping: dict, now: float) -> str | None:
        bout, reason = self._feed_bout(mapping, now)
        if reason:
            return reason
        started = (bout.get("status") != "scheduled" or bout.get("winner") or bout.get("method")
                   or (bout.get("fighter_a") or {}).get("winner")
                   or (bout.get("fighter_b") or {}).get("winner")
                   or (bout.get("round") or 0) > 0)
        if started:
            if self.inplay is not None and bout.get("status") == "in_progress":
                return "Bout in progress; waiting for a usable live clock and stats"
            self.ledger.block_bout(self.session_id, mapping["bout_id"],
                                   "No validated in-play model; bout started or finished")
            return "No validated in-play model; bout started or finished"
        return self._card_reason(mapping, now, need_history=True)

    def _card_reason(self, mapping: dict, now: float, *, need_history: bool) -> str | None:
        try:
            card_date = datetime.fromisoformat(self.config["card_date"]).date()
        except ValueError:
            return "Invalid model card date"
        if abs((datetime.fromtimestamp(now, timezone.utc).date() - card_date).days) > 1:
            return "Model card is not dated for the current event window"
        if need_history:
            for key in ("f1_ufc_fights", "f2_ufc_fights"):
                history = mapping.get(key)
                if (not isinstance(history, int) or isinstance(history, bool)
                        or history < self.policy.min_ufc_fights):
                    return "Insufficient fighter history for this trading policy"
        return None

    def _feed_bout(self, mapping: dict, now: float) -> tuple[dict | None, str | None]:
        """The exact, fresh, identity-checked ESPN bout, or why it is unusable."""
        if not self.config or not self.session_id:
            return None, "No configured event"
        blocked = self.ledger.blocked(self.session_id, mapping["bout_id"])
        if blocked:
            return None, blocked
        with self.feed_lock:
            message, received, connected = copy.deepcopy(self.feed), self.feed_received, self.feed_connected
        if not connected or received is None or time.monotonic() - received > self.policy.max_feed_age_seconds:
            return None, "Live fight feed disconnected or stale"
        if not isinstance(message, dict) or message.get("success") is not True:
            return None, "Live fight feed reports an error"
        meta = message.get("meta") or {}
        if meta.get("event_id") != self.config["espn_event_id"]:
            return None, "Live event does not match the budgeted ESPN event"
        if meta.get("event_status") not in {"scheduled", "in_progress"}:
            return None, "Event is finished or unavailable"
        if not age_is_valid(meta.get("captured_at"), now, self.policy.max_feed_age_seconds):
            return None, "Gateway timestamp stale or invalid"
        if not age_is_valid(meta.get("espn_updated_at"), now, self.policy.max_source_age_seconds):
            return None, "ESPN source timestamp missing, stale or invalid"
        bouts = [b for b in message.get("data", []) if b.get("bout_id") == mapping["bout_id"]]
        if len(bouts) != 1:
            return None, "Exact ESPN bout identity not found"
        bout = bouts[0]
        actual = {normalized_name(str((bout.get(c) or {}).get("name", "")))
                  for c in ("fighter_a", "fighter_b")}
        expected = {normalized_name(mapping["f1"]), normalized_name(mapping["f2"])}
        if actual != expected:
            return None, "ESPN fighter identities do not match the model card"
        return bout, None

    def _bout_status(self, bout_id: str) -> str | None:
        with self.feed_lock:
            data = (self.feed or {}).get("data") if isinstance(self.feed, dict) else None
        matches = [b for b in data or [] if isinstance(b, dict) and b.get("bout_id") == bout_id]
        return matches[0].get("status") if len(matches) == 1 else None

    def _inplay_inputs(self, mapping: dict, now: float) -> tuple[str, Decimal, str, int, str]:
        """(attempt key, P(f1), prior source, round, phase) from the latest live bout."""
        bout, reason = self._feed_bout(mapping, now)
        if reason:
            raise ValueError(reason)
        elapsed, stats_1, stats_2, phase = fight_progress(
            bout, mapping["f1"], mapping["f2"], normalized_name)
        self._live_stats = (stats_1, stats_2)
        scheduled = mapping.get("scheduled_rounds")
        if scheduled not in (3, 5):
            raise ValueError("Scheduled rounds unknown; in-fight trading needs 3 or 5")
        if elapsed >= scheduled:
            raise ValueError("Final round finished; awaiting the result")
        round_k = int(elapsed) if phase == "break" else int(bout["round"])
        if phase == "break":
            seen = self.break_seen.get((mapping["bout_id"], round_k))
            if seen is None or time.monotonic() - seen < self.policy.min_break_seconds:
                raise ValueError("Break just started; waiting for round totals to settle")
            if time.monotonic() - seen > self.policy.max_break_seconds:
                raise ValueError("Too late in the break; the next round may already be live")
            key = f'{mapping["bout_id"]}:r{round_k}'
        elif phase == "live":
            key = f'{mapping["bout_id"]}:l{round_k}'
        else:
            raise ValueError("Unknown fight phase")
        if mapping.get("probability_f1") is None:
            raise ValueError("No initial pick for the in-play model")
        p_prior, source = decimal(mapping["probability_f1"]), "initial pick"
        card_reason = self._card_reason(mapping, now, need_history=True)
        if card_reason:
            raise ValueError(card_reason)
        p_f1 = self.inplay.predict_progress(
            stats_1, stats_2, float(p_prior), elapsed, scheduled)
        # Never act on near-certainty, and keep sizing in exact 4 dp decimals.
        p_f1 = min(max(p_f1, 0.01), 0.99)
        return key, decimal(f"{p_f1:.4f}"), source, round_k, phase

    def _capture_prefight(self, mapping: dict, status: str | None):
        """Remember the last two-sided Kalshi mid while the bout is still scheduled."""
        if self.inplay is None or status != "scheduled":
            return
        ticker, now = mapping["ticker"], time.monotonic()
        last = self.prefight_checked.get(ticker)
        if last is not None and now - last < self.policy.prefight_capture_seconds:
            return
        self.prefight_checked[ticker] = now
        try:
            quotes = rest_quotes(self.client.get_orderbook(ticker))
        except (ValueError, RuntimeError):
            return
        yes_ask, yes_bid = quotes["yes"][0], 1 - quotes["no"][0]
        if not 0 < yes_bid <= yes_ask < 1 or yes_ask - yes_bid > self.policy.max_spread:
            return
        p_yes = (yes_ask + yes_bid) / 2
        p_f1 = p_yes if mapping["yes_fighter"] == mapping["f1"] else 1 - p_yes
        self.prefight[ticker] = {"p_f1": str(p_f1), "at": time.time()}
        self._save_prefight()
        self.record("prefight_price", {"ticker": ticker, "p_f1": str(p_f1),
                                       "yes_bid": str(yes_bid), "yes_ask": str(yes_ask)})

    def _load_prefight(self) -> dict[str, dict]:
        if self.prefight_path is None or not self.prefight_path.exists():
            return {}
        try:
            raw = json.loads(self.prefight_path.read_text())
            return {k: {"p_f1": str(decimal(v["p_f1"])), "at": float(v["at"])} for k, v in raw.items()}
        except (ValueError, KeyError, TypeError):
            return {}

    def _save_prefight(self):
        if self.prefight_path is None:
            return
        tmp = self.prefight_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.prefight))
        tmp.replace(self.prefight_path)

    def _market_context(self, mapping: dict) -> tuple[dict, Decimal]:
        market = self.client.get_market(mapping["ticker"])
        self._validate_identity(market, mapping)
        if self._market_identity(market) != mapping["market_identity"]:
            raise ValueError("Market rules or identity changed; reconfirm while paused")
        if market.get("status") != "active" or market.get("result"):
            raise ValueError("Market is not open for trading")
        if market.get("is_provisional"):
            raise ValueError("Provisional markets are unsupported")
        if decimal(market.get("notional_value_dollars", "1")) != 1:
            raise ValueError("Only $1 binary contracts are supported")
        now = time.time()
        if timestamp(market.get("open_time")) > now:
            raise ValueError("Market is not open yet")
        if timestamp(market.get("close_time")) - now <= self.policy.close_buffer_seconds:
            raise ValueError("Market is closed or too close to closing")
        occurrence = datetime.fromtimestamp(timestamp(market.get("occurrence_datetime")), timezone.utc).date()
        card_date = datetime.fromisoformat(self.config["card_date"]).date()
        if abs((occurrence - card_date).days) > 1:
            raise ValueError("Kalshi occurrence date does not match the model card")
        event = self.client.get_event(market["event_ticker"])
        # Single-fight winner series only. Method, round and combo markets
        # cannot reuse an unconditional winner probability.
        if event.get("series_ticker") != "KXUFCFIGHT":
            raise ValueError("Only verified KXUFCFIGHT winner-series markets are supported")
        series = self.client.get_series(event["series_ticker"])
        fee_type = event.get("fee_type_override") or series.get("fee_type")
        multiplier = event.get("fee_multiplier_override")
        if multiplier is None:
            multiplier = series.get("fee_multiplier")
        if fee_type not in {"quadratic", "quadratic_with_maker_fees"}:
            raise ValueError("Unsupported or missing exchange fee schedule")
        multiplier = decimal(multiplier)
        if not 0 < multiplier <= 10:
            raise ValueError("Unsupported fee multiplier")
        exchange = self.client.get_exchange_status()
        index = market.get("exchange_index", 0)
        if index == 0:
            active = exchange.get("trading_active")
        else:
            shards = exchange.get("exchange_index_statuses") or []
            active = next((s.get("trading_active") for s in shards
                           if s.get("exchange_index") == index), False)
        if active is not True:
            raise ValueError("Exchange trading is paused or status is unknown")
        self.record("market_context", {"market": market, "event": event, "series": series,
                                       "exchange": exchange})
        return market, multiplier

    def tick(self):
        if not self.running.is_set() or not self.lock.acquire(blocking=False):
            return
        try:
            if not self.config or not self.session_id:
                return
            orders = self.ledger.orders(self.session_id)
            if any(o["reserved"] for o in orders):
                if self._confirm_open_orders() or not self.running.is_set():
                    if self.running.is_set():
                        self.message = ("Confirming the last order with Kalshi. "
                                        "No new order until it clears.")
                    return
                orders = self.ledger.orders(self.session_id)
            decisions = []
            for mapping in self.config["mappings"]:
                if not self.running.is_set():
                    break
                decision = {"ticker": mapping["ticker"],
                            "bout": f'{mapping["f1"]} vs {mapping["f2"]}',
                            "action": "skip", "reason": ""}
                decisions.append(decision)
                status = self._bout_status(mapping["bout_id"])
                self._capture_prefight(mapping, status)
                in_fight = self.inplay is not None and status == "in_progress"
                try:
                    if in_fight:
                        family, p_f1, source, round_k, phase = self._inplay_inputs(
                            mapping, time.time())
                        decision.update(phase=(f"live round {round_k}" if phase == "live"
                                               else f"after round {round_k}"),
                                        prior=source, p_f1=float(p_f1))
                        family, attempt = self._next_attempt(
                            orders, family, kind=phase,
                            label=(f"during round {round_k}" if phase == "live"
                                   else f"in the break after round {round_k}"))
                    else:
                        reason = self._feed_reason(mapping, time.time())
                        if reason:
                            raise ValueError(reason)
                        if mapping.get("p_market") is None:
                            raise ValueError("No vig-free line; pre-fight orders abstain")
                        decision.update(phase="pre-fight", layer=mapping.get("probability_layer"))
                        family, attempt = self._next_attempt(
                            orders, mapping["bout_id"], kind="prefight", label="before the fight")
                        p_f1 = decimal(mapping["probability_f1"])
                        decision["p_f1"] = float(p_f1)
                        decision["event_id"] = self.config["espn_event_id"]
                    market, multiplier = self._market_context(mapping)
                    # Price and depth come from the REST book, even if the socket is down.
                    began = time.monotonic()
                    book_payload = self.client.get_orderbook(mapping["ticker"])
                    quotes = rest_quotes(book_payload)
                    self.record("quote", {"ticker": mapping["ticker"], "book": book_payload})
                    self.market_connected = True
                    self.market_received = time.monotonic()
                    if time.monotonic() - began > self.policy.max_book_age_seconds:
                        raise ValueError("Market quote retrieval was too slow")
                    spread = quotes["yes"][0] + quotes["no"][0] - 1
                    decision["yes_bid"] = str(1 - quotes["no"][0])
                    decision["yes_ask"] = str(quotes["yes"][0])
                    event = self.ledger.event(self.session_id)
                    p_yes = p_f1 if mapping["yes_fighter"] == mapping["f1"] else 1 - p_f1
                    book_f1 = decimal(mapping["p_book"]) if mapping.get("p_book") else None
                    if self.policy.venue_lag and not in_fight and book_f1 is None:
                        raise ValueError("Venue-lag rule is on and this bout has no sportsbook price")
                    room = self._budget_room(orders, mapping, in_fight, event)
                    locked = self._high_odds_side(orders, mapping["ticker"])
                    candidates, best, lag_reason, stick_reason, held_reason = [], None, None, None, None
                    for side, probability in (("yes", p_yes), ("no", 1 - p_yes)):
                        price, depth = quotes[side]
                        if locked and side != locked:
                            unit_cost, edge, _kelly = edge_of(
                                probability, price, multiplier, self.policy)
                            if best is None or edge > best[1]:
                                best = (side, edge, probability, unit_cost, Decimal(0))
                            stick_reason = (
                                f"Sticking with {self._side_name(mapping, locked)}; "
                                "that fighter is already held at high odds"
                            )
                            continue
                        if self.policy.venue_lag and not in_fight:
                            book_side = book_f1 if side == "yes" else 1 - book_f1
                            if mapping["yes_fighter"] != mapping["f1"]:
                                book_side = (1 - book_f1) if side == "yes" else book_f1
                            blocked = lag_block_reason(
                                probability, book_side, price, spread,
                                taker_fee(price, 1, multiplier),
                                min_lag=self.policy.min_venue_lag,
                                max_gap=self.policy.max_book_gap,
                            )
                            if blocked:
                                lag_reason = blocked
                                continue
                        unit_cost, edge, kelly = edge_of(probability, price, multiplier, self.policy)
                        allowance = bout_allowance(kelly=kelly, policy=self.policy,
                                                   unit_cost=unit_cost, **room)
                        if best is None or edge > best[1]:
                            best = (side, edge, probability, unit_cost, allowance)
                        candidate = size_candidate(
                            side=side, probability=probability, price=price, depth=depth,
                            spread=spread, allowance=allowance,
                            fee_multiplier=multiplier, policy=self.policy,
                        )
                        if candidate and in_fight and (reason := self._held_reason(mapping, side)):
                            held_reason = reason
                            continue
                        if candidate:
                            candidates.append(candidate)
                    if not candidates:
                        if stick_reason and (best is None or best[0] != locked):
                            raise ValueError(stick_reason)
                        if held_reason:
                            raise ValueError(held_reason)
                        if lag_reason and best is None:
                            raise ValueError(lag_reason)
                        raise ValueError(self._no_trade_reason(mapping, spread, *best))
                    candidate = max(candidates, key=lambda c: c.net_edge)
                    if self.mode != "paper":
                        balance = self.client.get_balance()
                        if decimal(balance.get("balance")) / 100 < candidate.reserved_cost:
                            raise ValueError("Insufficient account cash for price plus fee reservation")
                    if in_fight:
                        # Still the same break with the same inputs, after the quote.
                        if self._inplay_inputs(mapping, time.time())[0] != family:
                            raise ValueError("The break ended while quoting")
                    else:
                        reason = self._feed_reason(mapping, time.time())
                        if reason:
                            raise ValueError(reason)
                    if self.ledger.blocked(self.session_id, mapping["bout_id"]):
                        raise ValueError("Bout finished or became unavailable")
                    if (not self.running.is_set() or time.monotonic() - began > 5
                            or timestamp(market["close_time"]) - time.time()
                            <= self.policy.close_buffer_seconds):
                        raise ValueError("Stopped, quote expired, or market is closing")
                    client_id = self.ledger.reserve(self.session_id, attempt, mapping["ticker"], candidate)
                    self.last_attempt[family] = time.monotonic()
                    decision.update({"side": candidate.side,
                                     "probability": float(candidate.probability),
                                     "price_dollars": str(candidate.price),
                                     "contracts": candidate.count,
                                     "cost_dollars": str(candidate.estimated_cost),
                                     "fee_dollars": str(candidate.estimated_cost - candidate.price * candidate.count),
                                     "edge": float(candidate.net_edge),
                                     "event_id": self.config["espn_event_id"]})
                    # Stop can arrive between reservation and dispatch.
                    if not self.running.is_set():
                        self.ledger.finish(client_id, Decimal(0), Decimal(0), "canceled")
                        raise ValueError("Stopped before submission")
                    if self.mode == "paper":
                        self.ledger.finish(client_id, candidate.estimated_cost,
                                           Decimal(candidate.count), "paper_filled")
                        decision.update(action="paper", reason="Simulated fill; no exchange order sent")
                    else:
                        self._submit_demo(client_id, mapping, candidate)
                        decision.update(action=self.mode,
                                        reason=f"{self.mode.title()} order submitted; inspect its ledger status")
                    orders = self.ledger.orders(self.session_id)
                    if any(o["reserved"] for o in orders):
                        self.message = ("Confirming the last order with Kalshi. "
                                        "No new order until it clears.")
                        break
                except (ValueError, RuntimeError) as exc:
                    # The client exposes sanitized RuntimeErrors, never raw bodies.
                    decision["reason"] = str(exc)
            self.decisions = decisions
            self.record("decisions", decisions)
        except Exception:
            self.running.clear()
            self.message = "Internal trading error. Paused; inspect the journal and reconcile."
            raise
        finally:
            self.lock.release()

    @property
    def decision_interval(self) -> float:
        """How often the worker may look again. Live repricing checks every second."""
        if self.inplay is not None:
            return self.policy.live_retry_seconds
        return IDLE_DECISION_SECONDS

    def _next_attempt(self, orders: list[dict], base: str, *, kind: str,
                      label: str) -> tuple[str, str]:
        """(attempt family, unique ledger key) for the next try, or why not yet.

        Pre-fight keys: "<bout>", "<bout>:p2", ... Breaks: "<bout>:r<k>".
        Live rounds: "<bout>:l<k>". Every key shares the fight's budget caps.
        """
        if kind == "prefight":
            limit, wait, marker = (self.policy.max_prefight_attempts,
                                   self.policy.prefight_retry_seconds, base + ":p")
        elif kind == "break":
            limit, wait, marker = (self.policy.max_break_attempts,
                                   self.policy.break_retry_seconds, base + ":")
        elif kind == "live":
            limit, wait, marker = (self.policy.max_live_attempts,
                                   self.policy.live_retry_seconds, base + ":")
        else:
            raise ValueError("Unknown attempt kind")
        tries = sum(1 for o in orders if o["bout_id"] == base or o["bout_id"].startswith(marker))
        if tries >= limit:
            raise ValueError(f"Already tried {tries} times {label}")
        last = self.last_attempt.get(base)
        if last is not None and time.monotonic() - last < wait:
            raise ValueError(f"Waiting {wait - (time.monotonic() - last):.0f}s before trying "
                             f"again {label}")
        if tries == 0:
            return base, base
        return base, f"{marker}{tries + 1}"

    def _budget_room(self, orders: list[dict], mapping: dict, in_fight: bool,
                     event: dict) -> dict:
        """Inputs for risk.bout_allowance: this fight's share of what is left."""
        budget = decimal(event["budget_dollars"])
        remaining = decimal(event["remaining_dollars"])

        def used(order):
            return decimal(order["cost_dollars"]) + decimal(order["reserved_dollars"])

        def fight(order):
            return order["bout_id"].split(":")[0]

        def is_break(order):
            # ":l" is a live-round attempt. Both share the in-fight budget.
            return ":r" in order["bout_id"] or ":l" in order["bout_id"]

        open_bouts = set()
        for m in self.config["mappings"]:
            if self.ledger.blocked(self.session_id, m["bout_id"]):
                continue
            if in_fight or self._bout_status(m["bout_id"]) in (None, "scheduled"):
                open_bouts.add(m["bout_id"])
        open_bouts.add(mapping["bout_id"])
        phase = [o for o in orders if is_break(o) == in_fight]
        if in_fight or self.inplay is None:
            phase_available = remaining
        else:
            # Keep part of the budget for between-rounds trades.
            cap = budget * (1 - self.policy.inplay_reserve)
            phase_available = min(remaining, max(Decimal(0), cap - sum(map(used, phase), Decimal(0))))
        return {
            "budget": budget, "remaining": remaining, "phase_available": phase_available,
            "phase_pool": phase_available + sum(
                (used(o) for o in phase if fight(o) in open_bouts), Decimal(0)),
            "open_bouts": len(open_bouts),
            "phase_bout_spent": sum((used(o) for o in phase if fight(o) == mapping["bout_id"]),
                                    Decimal(0)),
            "bout_spent": sum((used(o) for o in orders if fight(o) == mapping["bout_id"]),
                              Decimal(0)),
        }

    def _held_reason(self, mapping: dict, side: str) -> str | None:
        """Refuse a fighter who is being controlled and has no finish path."""
        pair = getattr(self, "_live_stats", None)
        if not pair:
            return None
        first, second = pair
        mine_is_first = (side == "yes") == (mapping["yes_fighter"] == mapping["f1"])
        mine, theirs = (first, second) if mine_is_first else (second, first)
        if not held_without_threat(mine, theirs):
            return None
        return (f"Staying off {self._side_name(mapping, side)}; "
                "being controlled with no finishing threat")

    def _high_odds_side(self, orders: list[dict], ticker: str) -> str | None:
        """The fighter already held under 50 cents, if either side is."""
        held = {"yes": Decimal(0), "no": Decimal(0)}
        cheapest = {"yes": None, "no": None}
        for order in orders:
            if order.get("ticker") != ticker or order.get("side") not in held:
                continue
            if order.get("status") not in {"filled", "demo_filled", "paper_filled"}:
                continue
            filled = decimal(order.get("filled_count") or 0)
            price = decimal(order["price"])
            if filled <= 0 or price >= HIGH_ODDS_PRICE:
                continue
            side = order["side"]
            held[side] += filled
            if cheapest[side] is None or price < cheapest[side]:
                cheapest[side] = price
        sides = [side for side, count in held.items() if count > 0]
        if not sides:
            return None
        return max(sides, key=lambda side: (held[side], -cheapest[side]))

    @staticmethod
    def _side_name(mapping: dict, side: str) -> str:
        yes, f1, f2 = mapping["yes_fighter"], mapping["f1"], mapping["f2"]
        return yes if side == "yes" else (f2 if yes == f1 else f1)

    def _no_trade_reason(self, mapping: dict, spread: Decimal, side: str, edge: Decimal,
                         probability: Decimal, unit_cost: Decimal, allowance: Decimal) -> str:
        yes, f1, f2 = mapping["yes_fighter"], mapping["f1"], mapping["f2"]
        name = yes if side == "yes" else (f2 if yes == f1 else f1)
        view = (f"model {probability:.0%} on {name} vs {unit_cost * 100:.0f}¢ all-in, "
                f"edge {edge * 100:+.1f}¢")
        if edge < self.policy.min_net_edge:
            return f"No edge: {view} (needs {self.policy.min_net_edge * 100:.0f}¢)"
        if spread > self.policy.max_spread:
            return f"Spread {spread * 100:.0f}¢ too wide; {view}"
        if allowance < unit_cost:
            return f"This fight's budget share is used; {view}"
        return f"Not enough contracts offered; {view}"

    def _submit_demo(self, client_id: str, mapping: dict, candidate):
        acknowledged = False
        try:
            result = self.client.create_ioc_order(
                mapping["ticker"], candidate.side, candidate.price, candidate.count, client_id
            )
            acknowledged = True
            order_id = result.get("order_id")
            self.ledger.mark_unknown(client_id, order_id)
            for delay in (*self.reconcile_delays, None):
                if self._reconcile_one(next(o for o in self.ledger.orders(self.session_id)
                                            if o["id"] == client_id)):
                    break
                if delay is not None:
                    self.sleep(delay)
        except KalshiTransportError as exc:
            if not acknowledged and not exc.ambiguous and exc.status_code in {400, 401, 403, 404, 422, 429}:
                self.ledger.finish(client_id, Decimal(0), Decimal(0), "rejected")
                self.message = "Exchange rejected the order. No spend."
            else:
                self.ledger.mark_unknown(client_id)
                self.message = ("Confirming the last order with Kalshi. "
                                "No new order until it clears.")
        except ValueError:
            self.running.clear()
            self.message = "Order records disagree with Kalshi. Paused until that is reviewed."
            raise
        except Exception:
            self.ledger.mark_unknown(client_id)
            self.message = ("Confirming the last order with Kalshi. "
                            "No new order until it clears.")

    def _confirm_open_orders(self) -> bool:
        """Read reserved orders again. True when one is still reserved."""
        if not self.session_id:
            return False
        for order in self.ledger.orders(self.session_id):
            if not order["reserved"] or self.mode == "paper":
                continue
            try:
                self._reconcile_one(order)
            except KalshiTransportError:
                return True
            except (ValueError, RuntimeError):
                self.running.clear()
                self.message = "Order records disagree with Kalshi. Paused until that is reviewed."
                return True
            except Exception:
                return True
        return any(o["reserved"] for o in self.ledger.orders(self.session_id))

    def _reconcile_one(self, local: dict) -> bool:
        if local["exchange_order_id"]:
            order = self.client.get_order(local["exchange_order_id"])
        else:
            order = self.client.find_order_by_client_id(local["id"], ticker=local["ticker"])
        if order is None:
            return False
        if order.get("client_order_id") != local["id"] or order.get("ticker") != local["ticker"]:
            raise ValueError("Exchange order identity mismatch")
        self._validate_direction(order, local["side"])
        if order.get("status") not in {"executed", "canceled"}:
            return False
        filled = decimal(order.get("fill_count_fp"))
        remaining = decimal(order.get("remaining_count_fp"))
        if remaining != 0:
            return False
        if decimal(order.get("initial_count_fp")) != local["count"]:
            raise ValueError("Exchange order size mismatch")
        # Aggregate order cost semantics are ambiguous for sell-YES/buy-NO.
        # Reconstruct cash debit from individually identified, complete fills.
        fills = self.client.list_fills(order["order_id"])
        spent, quantity, seen = Decimal(0), Decimal(0), set()
        for fill in fills:
            fill_id = fill.get("fill_id")
            if not fill_id or fill_id in seen:
                raise ValueError("Duplicate or missing fill identity")
            seen.add(fill_id)
            if (fill.get("order_id") != order["order_id"]
                    or fill.get("ticker", fill.get("market_ticker")) != local["ticker"]):
                raise ValueError("Fill identity mismatch")
            self._validate_direction(fill, local["side"])
            count, yes_price, fee = (decimal(fill.get(key)) for key in
                                     ("count_fp", "yes_price_dollars", "fee_cost"))
            price = yes_price if local["side"] == "yes" else 1 - yes_price
            if count <= 0 or not 0 < price <= decimal(local["price"]) or fee < 0:
                raise ValueError("Fill price, quantity or fee violates the reserved order")
            spent += count * price + fee
            quantity += count
        if quantity != filled:
            return False  # REST fill records may lag the final order record.
        if (filled == 0 and spent != 0) or (filled > 0 and spent <= 0):
            raise ValueError("Exchange fill and charge disagree")
        self.ledger.finish(local["id"], spent, filled,
                           ("demo_filled" if self.mode == "demo" else "filled") if filled else "unfilled",
                           order.get("order_id"))
        return True

    @staticmethod
    def _validate_direction(record: dict, side: str):
        if record.get("outcome_side") != side or record.get("book_side") != (
            "bid" if side == "yes" else "ask"
        ):
            raise ValueError("Exchange order direction mismatch or unavailable")

    def reconcile(self) -> dict:
        with self.lock:
            if self.running.is_set():
                raise ValueError("Stop before reconciliation")
            if self.session_id:
                for order in self.ledger.orders(self.session_id):
                    if order["reserved"]:
                        if self.mode == "paper":
                            # A crash before recording a simulated fill has no
                            # exchange exposure, so safely cancel the paper attempt.
                            self.ledger.finish(order["id"], Decimal(0), Decimal(0), "canceled")
                        else:
                            self._reconcile_one(order)
            pending = self.session_id and any(o["reserved"] for o in self.ledger.orders(self.session_id))
            self.message = ("Still awaiting definitive exchange records; reservation retained."
                            if pending else "Reconciled. Session remains paused.")
            return self.status()

    def status(self) -> dict:
        # Feed state uses its own lock; it must keep updating during REST calls.
        with self.feed_lock:
            feed = copy.deepcopy(self.feed)
            fresh = (self.feed_connected and self.feed_received is not None
                     and time.monotonic() - self.feed_received <= self.policy.max_feed_age_seconds)
        visible_feed = None
        if isinstance(feed, dict) and feed.get("success") is True:
            meta = feed.get("meta") or {}
            visible_feed = {
                "event_id": meta.get("event_id"), "event_name": meta.get("event_name"),
                "status": meta.get("event_status"), "updated_at": meta.get("espn_updated_at"),
                "fights": [{"bout_id": b.get("bout_id"), "status": b.get("status"),
                            "fighter_a": (b.get("fighter_a") or {}).get("name", ""),
                            "fighter_b": (b.get("fighter_b") or {}).get("name", "")}
                           for b in feed.get("data") or [] if isinstance(b, dict)],
            }
            fresh = fresh and age_is_valid(meta.get("espn_updated_at"), time.time(),
                                          self.policy.max_source_age_seconds)
        else:
            fresh = False
        return {"mode": self.mode, "running": self.running.is_set(),
                "config_version": self.config_version(),
                "feed_connected": bool(fresh), "market_connected": (
                    self.market_connected and self.market_received is not None
                ),
                "event": self.ledger.event(self.session_id) if self.session_id else None,
                "readiness": {"live_enabled": self.mode == "live", "reasons": READINESS_REASONS},
                "in_fight_enabled": self.inplay is not None,
                "max_budget_dollars": str(self.max_budget) if self.max_budget is not None else None,
                "decisions": list(self.decisions),
                "orders": self.ledger.orders(self.session_id) if self.session_id else [],
                "feed": visible_feed, "message": self.message}
