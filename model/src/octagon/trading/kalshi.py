"""Kalshi event-contract transport and a fail-closed streaming order book.

Prices and quantities use Decimal. Order writes use the V2 event endpoint and
are never retried here: a timeout may hide an accepted order. Callers must keep
the client_order_id and reserve its budget until reconciliation is conclusive.
Contracts verified against docs.kalshi.com on 2026-10-31.
"""

from __future__ import annotations

import base64
import math
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


ENDPOINTS = {
    "demo": (
        "https://external-api.demo.kalshi.co/trade-api/v2",
        "wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2",
    ),
    "production": (
        "https://external-api.kalshi.com/trade-api/v2",
        "wss://external-api-ws.kalshi.com/trade-api/ws/v2",
    ),
}
ONE = Decimal("1")


class KalshiError(RuntimeError):
    """Sanitized error suitable for an operator log; never includes credentials."""


class KalshiTransportError(KalshiError):
    """A request failed. Ambiguous writes must remain reserved and reconciled."""

    def __init__(self, message: str, *, status_code: int | None = None, ambiguous: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.ambiguous = ambiguous


class KalshiProtocolError(KalshiError):
    """The exchange response cannot be safely interpreted."""


class KalshiBookError(KalshiProtocolError):
    """Discard the book and reconnect/resubscribe before making decisions."""


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise KalshiProtocolError("Expected a fixed-point decimal value")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError):
        raise KalshiProtocolError("Invalid fixed-point decimal value") from None
    if not result.is_finite():
        raise KalshiProtocolError("Non-finite decimal value")
    return result


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("A nonempty identifier of at most 256 characters is required")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("Identifiers cannot contain control characters")
    return value


def _object(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    result = payload.get(key)
    if not isinstance(result, dict):
        raise KalshiProtocolError("Missing response object")
    return result


class KalshiClient:
    """Synchronous REST client. Public reads work without configured credentials.

    Private reads and writes require both an API key ID and a PEM private-key
    path. ``from_env`` reads KALSHI_API_KEY_ID / KALSHI_PRIVATE_KEY_PATH; private
    key contents stay on the backend. Production must be selected explicitly.
    Strategy authorization and durable budget accounting belong to the caller.
    """

    def __init__(
        self,
        environment: str = "demo",
        *,
        api_key_id: str | None = None,
        private_key_path: str | Path | None = None,
        session: requests.Session | None = None,
        timeout: float = 10.0,
        subaccount: int = 0,
        live_enabled: bool = False,
    ):
        if environment not in ENDPOINTS:
            raise ValueError("Kalshi environment must be demo or production")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("A positive finite request timeout is required")
        if isinstance(subaccount, bool) or not isinstance(subaccount, int) or subaccount < 0:
            raise ValueError("Invalid subaccount")
        if not isinstance(live_enabled, bool):
            raise ValueError("live_enabled must be a boolean")
        self.environment = environment
        self.base_url, self.websocket_url = ENDPOINTS[environment]
        self.timeout = timeout
        self.subaccount = subaccount
        self.live_enabled = live_enabled
        self._api_key_id = _identifier(api_key_id) if api_key_id is not None else None
        self._private_key_path = Path(private_key_path) if private_key_path else None
        self._private_key: Any = None
        self._session = session if session is not None else requests.Session()

    @classmethod
    def from_env(cls, environment: str = "demo", **kwargs: Any) -> KalshiClient:
        return cls(
            environment,
            api_key_id=os.environ.get("KALSHI_API_KEY_ID") or None,
            private_key_path=os.environ.get("KALSHI_PRIVATE_KEY_PATH") or None,
            **kwargs,
        )

    def auth_headers(self, method: str, path: str, *, timestamp_ms: int | None = None) -> dict:
        """Sign timestamp + uppercase method + full path, excluding its query."""
        if not self._api_key_id or not self._private_key_path:
            raise KalshiError("Kalshi API key ID and private-key path are required")
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa
        except ImportError:
            raise KalshiError("Install the trading dependencies to use Kalshi authentication") from None
        if self._private_key is None:
            try:
                self._private_key = serialization.load_pem_private_key(
                    self._private_key_path.read_bytes(), password=None
                )
            except (OSError, ValueError, TypeError):
                raise KalshiError("Unable to load the Kalshi private key") from None
        timestamp = str(timestamp_ms if timestamp_ms is not None else time.time_ns() // 1_000_000)
        message = f"{timestamp}{method.upper()}{path.split('?')[0]}".encode("utf-8")
        if isinstance(self._private_key, rsa.RSAPrivateKey):
            signature = self._private_key.sign(
                message,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
                hashes.SHA256(),
            )
        elif isinstance(self._private_key, ed25519.Ed25519PrivateKey):
            signature = self._private_key.sign(message)
        else:
            raise KalshiError("Kalshi requires an RSA or Ed25519 private key")
        return {
            "KALSHI-ACCESS-KEY": self._api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("ascii"),
        }

    def websocket_headers(self) -> dict[str, str]:
        return self.auth_headers("GET", "/trade-api/ws/v2")

    @staticmethod
    def subscription_message(tickers: Sequence[str], request_id: int = 1) -> dict:
        if isinstance(tickers, str) or not tickers:
            raise ValueError("At least one market ticker is required")
        return {
            "id": request_id,
            "cmd": "subscribe",
            "params": {
                "channels": ["orderbook_delta"],
                "market_tickers": list(dict.fromkeys(_identifier(ticker) for ticker in tickers)),
                "update_interval_ms": 0,
                "use_yes_price": False,
            },
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = False,
        params: dict | None = None,
        body: dict | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if authenticated:
            headers.update(self.auth_headers(method, "/trade-api/v2" + path))
        if body is not None:
            headers["Content-Type"] = "application/json"
        is_write = method != "GET"
        try:
            response = self._session.request(
                method,
                self.base_url + path,
                headers=headers,
                params=params,
                json=body,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException:
            raise KalshiTransportError(
                "Kalshi request did not complete; reconcile any pending order",
                ambiguous=is_write,
            ) from None
        if not 200 <= response.status_code < 300:
            raise KalshiTransportError(
                f"Kalshi request failed (HTTP {response.status_code})",
                status_code=response.status_code,
                ambiguous=is_write and response.status_code not in {400, 401, 403, 404, 422, 429},
            )
        try:
            data = response.json()
        except ValueError:
            raise KalshiTransportError("Kalshi returned invalid JSON", ambiguous=is_write) from None
        if not isinstance(data, dict):
            raise KalshiTransportError("Kalshi returned an invalid response", ambiguous=is_write)
        return data

    def get_market(self, ticker: str) -> dict:
        return _object(self._request("GET", f"/markets/{quote(_identifier(ticker), safe='')}"), "market")

    def get_event(self, event_ticker: str) -> dict:
        path = f"/events/{quote(_identifier(event_ticker), safe='')}"
        return _object(self._request("GET", path, params={"exclude_markets": "true"}), "event")

    def get_series(self, series_ticker: str) -> dict:
        path = f"/series/{quote(_identifier(series_ticker), safe='')}"
        return _object(self._request("GET", path), "series")

    def get_orderbook(self, ticker: str) -> dict:
        """Return the raw response, including orderbook_fp, without seeding WS state."""
        return self._request("GET", f"/markets/{quote(_identifier(ticker), safe='')}/orderbook")

    def get_exchange_status(self) -> dict:
        return self._request("GET", "/exchange/status")

    def get_balance(self) -> dict:
        """Raw balance fields are exchange amounts in cents, not dollars."""
        return self._request(
            "GET", "/portfolio/balance", authenticated=True, params={"subaccount": self.subaccount}
        )

    def get_user_data_timestamp(self) -> dict:
        return self._request("GET", "/exchange/user_data_timestamp")

    def _paginate(self, path: str, key: str, params: dict, *, authenticated: bool = True) -> list[dict]:
        results: list[dict] = []
        seen: set[str] = set()
        query = dict(params)
        for _ in range(10_000):
            data = self._request("GET", path, authenticated=authenticated, params=query)
            rows = data.get(key)
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise KalshiProtocolError("Invalid paginated Kalshi response")
            results.extend(rows)
            cursor = data.get("cursor")
            if cursor == "":
                return results
            if not isinstance(cursor, str) or cursor in seen:
                raise KalshiProtocolError("Invalid or repeated Kalshi pagination cursor")
            seen.add(cursor)
            query = {**query, "cursor": cursor}
        raise KalshiProtocolError("Kalshi pagination limit exceeded")

    def list_open_markets(self, series_ticker: str) -> list[dict]:
        """Public read of every open market in a series (to propose mappings)."""
        params = {"series_ticker": _identifier(series_ticker), "status": "open", "limit": 1000}
        return self._paginate("/markets", "markets", params, authenticated=False)

    def list_orders(self, *, ticker: str | None = None, status: str | None = None) -> list[dict]:
        """Get every current page. No status filter is safest for reconciliation."""
        params: dict[str, Any] = {"limit": 1000, "subaccount": self.subaccount}
        if ticker is not None:
            params["ticker"] = _identifier(ticker)
        if status is not None:
            if status not in {"resting", "canceled", "executed"}:
                raise ValueError("Invalid order status")
            params["status"] = status
        return self._paginate("/portfolio/orders", "orders", params)

    def list_positions(self, *, ticker: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"limit": 1000, "subaccount": self.subaccount}
        if ticker is not None:
            params["ticker"] = _identifier(ticker)
        return self._paginate("/portfolio/positions", "market_positions", params)

    def list_fills(self, order_id: str) -> list[dict]:
        """Return every fill page for one order without losing decimal precision.

        Canonical fields include fill_id, order_id, ticker, outcome_side,
        book_side, count_fp, yes_price_dollars, no_price_dollars, and fee_cost.
        The caller must deduplicate fill_id and compare the total filled count
        with the final order before releasing any reservation; reads can lag.
        """
        return self._paginate(
            "/portfolio/fills", "fills",
            {"order_id": _identifier(order_id), "limit": 1000, "subaccount": self.subaccount},
        )

    def get_order(self, order_id: str) -> dict:
        path = f"/portfolio/orders/{quote(_identifier(order_id), safe='')}"
        return _object(self._request("GET", path, authenticated=True), "order")

    def find_order_by_client_id(self, client_order_id: str, *, ticker: str | None = None) -> dict | None:
        """None means not observed yet; it never proves a timed-out write failed.

        REST portfolio data is eventually consistent. The caller must retain its
        reservation and halt new exposure until the order is positively resolved.
        """
        _identifier(client_order_id)
        matches = [
            order for order in self.list_orders(ticker=ticker)
            if order.get("client_order_id") == client_order_id
        ]
        if len(matches) > 1:
            raise KalshiProtocolError("Multiple orders share a client order ID")
        return matches[0] if matches else None

    def create_ioc_order(
        self,
        ticker: str,
        side: str,
        price: Decimal,
        count: int,
        client_order_id: str,
    ) -> dict:
        """Buy YES/NO at a bounded cost-axis price using the V2 YES-axis book.

        IOC may partially fill. A NO purchase costing q uses ask at YES price
        1-q. The caller must reserve count*price plus fees BEFORE this method,
        and reconcile actual fills afterwards. No server buy_max_cost is used.
        """
        if self.environment == "production" and not self.live_enabled:
            raise KalshiError("Production order submission is disabled for this client")
        if side not in {"yes", "no"}:
            raise ValueError("Order side must be yes or no")
        price = _decimal(price)
        if not 0 < price < 1 or price != price.quantize(Decimal("0.0001")):
            raise ValueError("Order price must be between zero and one with at most four decimals")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("Order count must be a positive whole number")
        yes_price = price if side == "yes" else ONE - price
        body = {
            "ticker": _identifier(ticker),
            "client_order_id": _identifier(client_order_id),
            "side": "bid" if side == "yes" else "ask",
            "count": f"{count}.00",
            "price": format(yes_price, ".4f"),
            "time_in_force": "immediate_or_cancel",
            "self_trade_prevention_type": "taker_at_cross",
            "post_only": False,
            "cancel_order_on_pause": True,
            "subaccount": self.subaccount,
            "exchange_index": -1,
        }
        data = self._request("POST", "/portfolio/events/orders", authenticated=True, body=body)
        if not isinstance(data.get("order_id"), str) or not data["order_id"]:
            raise KalshiTransportError("Kalshi order acknowledgement is incomplete", ambiguous=True)
        if data.get("client_order_id") != client_order_id:
            raise KalshiTransportError("Kalshi order acknowledgement ID mismatch", ambiguous=True)
        return data

    def cancel_order(self, order_id: str, *, ticker: str) -> dict:
        """Cancel only this order; callers still need final fill reconciliation."""
        path = f"/portfolio/events/orders/{quote(_identifier(order_id), safe='')}"
        return self._request(
            "DELETE", path, authenticated=True,
            params={
                "market_ticker": _identifier(ticker),
                "exchange_index": -1,
                "subaccount": self.subaccount,
            },
        )

    def close(self) -> None:
        self._session.close()


@dataclass
class _Book:
    sid: int
    bids: dict[str, dict[Decimal, Decimal]] = field(default_factory=dict)
    received_at: float = 0.0


class KalshiOrderBook:
    """One real-time WebSocket connection's order books.

    ``seq`` belongs to the subscription, NOT a market. On gaps, malformed data,
    server errors, or disconnect, every book is invalidated. Reconnect and wait
    for fresh snapshots; never combine an unsequenced REST book with WS deltas.
    Snapshots use yes_dollars_fp/no_dollars_fp and deltas price_dollars/delta_fp.
    Subscriptions explicitly pin use_yes_price=False so NO levels retain NO-leg
    pricing. No implicit cents/dollars or price-axis fallback is permitted.
    """

    def __init__(self):
        self._books: dict[str, _Book] = {}
        self._sequences: dict[int, int] = {}

    def disconnect(self) -> None:
        self._books.clear()
        self._sequences.clear()

    def apply(self, message: Mapping[str, Any], *, received_at: float | None = None) -> str | None:
        """Apply one WS message and return the changed ticker, otherwise None."""
        try:
            return self._apply(message, time.monotonic() if received_at is None else received_at)
        except (KalshiProtocolError, ValueError, TypeError, KeyError, InvalidOperation):
            self.disconnect()
            raise KalshiBookError("Kalshi book is invalid; reconnect and obtain fresh snapshots") from None

    def _apply(self, message: Mapping[str, Any], received_at: float) -> str | None:
        if not isinstance(message, Mapping) or not math.isfinite(received_at):
            raise KalshiBookError("Invalid message")
        kind = message.get("type")
        if kind in {"error", "unsubscribed"}:
            raise KalshiBookError("Subscription unavailable")
        if kind not in {"orderbook_snapshot", "orderbook_delta"}:
            return None
        sid, seq = message.get("sid"), message.get("seq")
        if type(sid) is not int or type(seq) is not int or sid < 0 or seq < 0:
            raise KalshiBookError("Invalid sequence")
        previous = self._sequences.get(sid)
        if previous is not None and seq != previous + 1:
            raise KalshiBookError("Sequence gap or duplicate")
        data = message.get("msg")
        if not isinstance(data, Mapping):
            raise KalshiBookError("Invalid payload")
        ticker = _identifier(data.get("market_ticker"))
        if kind == "orderbook_snapshot":
            bids = {
                "yes": self._levels(data.get("yes_dollars_fp")),
                "no": self._levels(data.get("no_dollars_fp")),
            }
            self._books[ticker] = _Book(sid, bids, received_at)
        else:
            book = self._books.get(ticker)
            if book is None or book.sid != sid:
                raise KalshiBookError("Delta without snapshot")
            side = data.get("side")
            if side not in {"yes", "no"}:
                raise KalshiBookError("Invalid side")
            price = _decimal(data.get("price_dollars"))
            delta = _decimal(data.get("delta_fp"))
            if not 0 < price < 1:
                raise KalshiBookError("Invalid price")
            quantity = book.bids[side].get(price, Decimal(0)) + delta
            if quantity < 0:
                raise KalshiBookError("Negative book quantity")
            if quantity == 0:
                book.bids[side].pop(price, None)
            else:
                book.bids[side][price] = quantity
            book.received_at = received_at
        book = self._books[ticker]
        if book.bids["yes"] and book.bids["no"]:
            if max(book.bids["yes"]) + max(book.bids["no"]) > ONE:
                raise KalshiBookError("Crossed book")
        self._sequences[sid] = seq
        return ticker

    @staticmethod
    def _levels(rows: Any) -> dict[Decimal, Decimal]:
        if not isinstance(rows, list):
            raise KalshiBookError("Missing book levels")
        result: dict[Decimal, Decimal] = {}
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) != 2:
                raise KalshiBookError("Invalid book level")
            price, count = (_decimal(value) for value in row)
            if not 0 < price < 1 or count <= 0 or price in result:
                raise KalshiBookError("Invalid book price or quantity")
            result[price] = count
        return result

    def is_ready(self, ticker: str) -> bool:
        return ticker in self._books

    def last_update(self, ticker: str) -> float | None:
        book = self._books.get(ticker)
        return book.received_at if book else None

    def last_updated(self, ticker: str) -> float | None:
        """Monotonic receive time of this market's most recent book message."""
        return self.last_update(ticker)

    def levels(self, ticker: str, side: str) -> list[tuple[Decimal, Decimal]]:
        """Executable buy asks on YES/NO cost axis, cheapest first."""
        if side not in {"yes", "no"}:
            raise ValueError("Quote side must be yes or no")
        book = self._books.get(ticker)
        if book is None:
            return []
        opposite = "no" if side == "yes" else "yes"
        return sorted((ONE - price, count) for price, count in book.bids[opposite].items())

    def quote(self, ticker: str, side: str) -> tuple[Decimal, Decimal] | None:
        levels = self.levels(ticker, side)
        return levels[0] if levels else None
