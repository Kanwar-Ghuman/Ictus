"""Kalshi contract tests with generated throwaway keys and mocked transport only."""

import base64
from decimal import Decimal

import pytest
import requests

from octagon.trading.kalshi import (
    KalshiBookError,
    KalshiClient,
    KalshiError,
    KalshiOrderBook,
    KalshiProtocolError,
    KalshiTransportError,
)


class Response:
    def __init__(self, data, status=200):
        self.data = data
        self.status_code = status

    def json(self):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        pass


def client_with_responses(monkeypatch, *responses, **kwargs):
    session = Session(responses)
    client = KalshiClient(session=session, **kwargs)
    monkeypatch.setattr(client, "auth_headers", lambda method, path: {"test-auth": "mock"})
    return client, session


def test_public_market_read_needs_no_key_and_cannot_redirect():
    session = Session([Response({"market": {"ticker": "TEST"}})])
    client = KalshiClient(session=session)
    assert client.get_market("TEST") == {"ticker": "TEST"}
    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert url == "https://external-api.demo.kalshi.co/trade-api/v2/markets/TEST"
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"] == 10
    assert "KALSHI-ACCESS-KEY" not in kwargs["headers"]


def test_environment_is_explicit_and_restricted():
    assert "external-api-ws.demo.kalshi.co" in KalshiClient().websocket_url
    assert "external-api-ws.kalshi.com" in KalshiClient("production").websocket_url
    with pytest.raises(ValueError):
        KalshiClient("https://not-an-exchange.example")
    with pytest.raises(ValueError):
        KalshiClient(timeout=float("nan"))


def test_private_requests_require_both_key_fields():
    client = KalshiClient(session=Session([]))
    with pytest.raises(KalshiError, match="required"):
        client.get_balance()


def test_production_order_submission_requires_explicit_opt_in(monkeypatch):
    client, session = client_with_responses(monkeypatch, environment="production")
    with pytest.raises(KalshiError, match="disabled"):
        client.create_ioc_order("FIGHT", "yes", Decimal("0.5"), 1, "intent")
    assert session.calls == []


def test_production_opt_in_does_not_change_v2_request_contract(monkeypatch):
    client, session = client_with_responses(
        monkeypatch, Response({"order_id": "order", "client_order_id": "intent"}, 201),
        environment="production", live_enabled=True,
    )
    client.create_ioc_order("FIGHT", "no", Decimal("0.5"), 1, "intent")
    assert session.calls[0][1].startswith("https://external-api.kalshi.com/")


@pytest.mark.parametrize("algorithm", ["rsa", "ed25519"])
def test_signature_uses_full_path_without_query(tmp_path, algorithm):
    cryptography = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519, padding

    key = (
        cryptography.generate_private_key(public_exponent=65537, key_size=2048)
        if algorithm == "rsa" else ed25519.Ed25519PrivateKey.generate()
    )
    key_path = tmp_path / "ephemeral-test.pem"
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    client = KalshiClient(api_key_id="test-key-id", private_key_path=key_path)
    headers = client.auth_headers("get", "/trade-api/v2/portfolio/orders?limit=3", timestamp_ms=1234)
    signature = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
    message = b"1234GET/trade-api/v2/portfolio/orders"
    if algorithm == "rsa":
        key.public_key().verify(
            signature, message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256(),
        )
    else:
        key.public_key().verify(signature, message)
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1234"
    assert headers["KALSHI-ACCESS-KEY"] == "test-key-id"


@pytest.mark.parametrize("side,book_side,yes_price", [
    ("yes", "bid", "0.3700"), ("no", "ask", "0.6300"),
])
def test_ioc_order_uses_v2_contract_and_no_price_complement(monkeypatch, side, book_side, yes_price):
    client, session = client_with_responses(
        monkeypatch, Response({"order_id": "exchange-id", "client_order_id": "intent-id"}, 201)
    )
    client.create_ioc_order("FIGHT", side, Decimal("0.37"), 3, "intent-id")
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url.endswith("/portfolio/events/orders")
    body = kwargs["json"]
    assert body["side"] == book_side
    assert body["price"] == yes_price
    assert body["count"] == "3.00"
    assert body["time_in_force"] == "immediate_or_cancel"
    assert body["self_trade_prevention_type"] == "taker_at_cross"
    assert body["cancel_order_on_pause"] is True
    assert body["exchange_index"] == -1
    assert "buy_max_cost" not in body
    assert "expiration_time" not in body


@pytest.mark.parametrize("price,count", [
    (Decimal("NaN"), 1), (Decimal("1"), 1), (Decimal("0"), 1),
    (Decimal("0.12345"), 1), (Decimal("0.5"), 0), (Decimal("0.5"), True),
])
def test_invalid_orders_never_touch_transport(monkeypatch, price, count):
    client, session = client_with_responses(monkeypatch)
    with pytest.raises((ValueError, KalshiProtocolError)):
        client.create_ioc_order("FIGHT", "yes", price, count, "intent")
    assert session.calls == []


@pytest.mark.parametrize("response", [
    requests.Timeout("secret that must not be logged"),
    Response({"message": "secret"}, 503),
    Response({"message": "secret"}, 408),
    Response(ValueError("secret"), 201),
    Response({"order_id": "exchange-id", "client_order_id": "wrong"}, 201),
])
def test_uncertain_post_never_retries_and_retains_ambiguity(monkeypatch, response):
    client, session = client_with_responses(monkeypatch, response)
    with pytest.raises(KalshiTransportError) as caught:
        client.create_ioc_order("FIGHT", "yes", Decimal("0.5"), 1, "intent")
    assert caught.value.ambiguous is True
    assert "secret" not in str(caught.value)
    assert len(session.calls) == 1


def test_http_errors_never_surface_remote_messages(monkeypatch):
    client, _ = client_with_responses(monkeypatch, Response({"message": "PRIVATE KEY"}, 401))
    with pytest.raises(KalshiTransportError) as caught:
        client.get_balance()
    assert str(caught.value) == "Kalshi request failed (HTTP 401)"
    assert caught.value.status_code == 401
    assert caught.value.ambiguous is False


def test_reconciliation_searches_all_pages_without_status_filter(monkeypatch):
    wanted = {"client_order_id": "wanted", "order_id": "found", "status": "canceled"}
    client, session = client_with_responses(
        monkeypatch,
        Response({"orders": [{"client_order_id": "other"}], "cursor": "next-page"}),
        Response({"orders": [wanted], "cursor": ""}),
    )
    assert client.find_order_by_client_id("wanted", ticker="FIGHT") == wanted
    assert len(session.calls) == 2
    assert session.calls[1][2]["params"]["cursor"] == "next-page"
    assert all("status" not in call[2]["params"] for call in session.calls)
    assert all(call[2]["params"]["subaccount"] == 0 for call in session.calls)


def test_reconciliation_absence_is_none_and_duplicate_ids_fail(monkeypatch):
    client, _ = client_with_responses(monkeypatch, Response({"orders": [], "cursor": ""}))
    assert client.find_order_by_client_id("pending") is None
    client, _ = client_with_responses(monkeypatch, Response({
        "orders": [{"client_order_id": "duplicate"}, {"client_order_id": "duplicate"}], "cursor": "",
    }))
    with pytest.raises(KalshiProtocolError, match="Multiple"):
        client.find_order_by_client_id("duplicate")


def test_repeated_pagination_cursor_fails_instead_of_partial_reconciliation(monkeypatch):
    client, session = client_with_responses(
        monkeypatch,
        Response({"orders": [], "cursor": "repeat"}),
        Response({"orders": [], "cursor": "repeat"}),
    )
    with pytest.raises(KalshiProtocolError, match="cursor"):
        client.list_orders()
    assert len(session.calls) == 2


def test_fill_reconciliation_reads_all_pages_without_losing_fractional_values(monkeypatch):
    first = {
        "fill_id": "fill-one", "order_id": "order", "ticker": "FIGHT",
        "outcome_side": "no", "book_side": "ask", "count_fp": "0.25",
        "yes_price_dollars": "0.6300", "no_price_dollars": "0.3700", "fee_cost": "0.004080",
    }
    second = {**first, "fill_id": "fill-two", "count_fp": "0.75", "fee_cost": "0.012240"}
    client, session = client_with_responses(
        monkeypatch,
        Response({"fills": [first], "cursor": "page-two"}),
        Response({"fills": [second], "cursor": ""}),
        subaccount=4,
    )
    assert client.list_fills("order") == [first, second]
    assert len(session.calls) == 2
    assert all(call[1].endswith("/portfolio/fills") for call in session.calls)
    assert session.calls[0][2]["params"] == {"order_id": "order", "limit": 1000, "subaccount": 4}
    assert session.calls[1][2]["params"]["cursor"] == "page-two"


def test_fill_reconciliation_does_not_return_partial_data_on_bad_later_page(monkeypatch):
    client, _ = client_with_responses(
        monkeypatch,
        Response({"fills": [{"fill_id": "first"}], "cursor": "page-two"}),
        Response({"fills": None, "cursor": ""}),
    )
    with pytest.raises(KalshiProtocolError, match="paginated"):
        client.list_fills("order")


def test_cancel_routes_by_ticker_and_selected_subaccount(monkeypatch):
    client, session = client_with_responses(monkeypatch, Response({"reduced_by": "1.00"}), subaccount=2)
    client.cancel_order("order-id", ticker="FIGHT")
    method, url, kwargs = session.calls[0]
    assert method == "DELETE"
    assert url.endswith("/portfolio/events/orders/order-id")
    assert kwargs["params"] == {"market_ticker": "FIGHT", "exchange_index": -1, "subaccount": 2}


def snapshot(ticker="A", seq=1, sid=7):
    return {"type": "orderbook_snapshot", "sid": sid, "seq": seq, "msg": {
        "market_ticker": ticker,
        "yes_dollars_fp": [["0.4000", "10.00"], ["0.3900", "20.00"]],
        "no_dollars_fp": [["0.5500", "5.00"], ["0.5400", "7.00"]],
    }}


def delta(ticker="A", seq=2, sid=7, amount="-2.00"):
    return {"type": "orderbook_delta", "sid": sid, "seq": seq, "msg": {
        "market_ticker": ticker, "side": "no", "price_dollars": "0.5500", "delta_fp": amount,
    }}


def test_book_exposes_complemented_executable_asks_and_exact_quantities():
    book = KalshiOrderBook()
    assert book.apply(snapshot(), received_at=10) == "A"
    assert book.quote("A", "yes") == (Decimal("0.45"), Decimal("5"))
    assert book.quote("A", "no") == (Decimal("0.60"), Decimal("10"))
    assert book.apply(delta(), received_at=11) == "A"
    assert book.quote("A", "yes") == (Decimal("0.45"), Decimal("3"))
    book.apply(delta(seq=3, amount="-3.00"))
    assert book.quote("A", "yes") == (Decimal("0.46"), Decimal("7"))


def test_sequence_belongs_to_subscription_across_markets():
    book = KalshiOrderBook()
    book.apply(snapshot("A", seq=50))
    book.apply(snapshot("B", seq=51))
    book.apply(delta("A", seq=52))
    assert book.is_ready("A") and book.is_ready("B")
    assert book.quote("A", "yes")[1] == Decimal("3")


@pytest.mark.parametrize("bad_message", [
    delta(seq=3), delta(seq=1), delta(sid=8), delta(amount="-6"),
    delta(amount="NaN"), {"type": "error", "msg": {"code": 1}},
    {"type": "orderbook_delta", "sid": 7, "seq": 2, "msg": {}},
])
def test_gaps_duplicates_wrong_subscription_or_bad_data_invalidate_every_book(bad_message):
    book = KalshiOrderBook()
    book.apply(snapshot("A", sid=7))
    book.apply(snapshot("B", sid=8))
    with pytest.raises(KalshiBookError):
        book.apply(bad_message)
    assert book.quote("A", "yes") is None
    assert book.quote("B", "yes") is None


def test_delta_before_snapshot_and_disconnect_require_fresh_snapshot():
    book = KalshiOrderBook()
    with pytest.raises(KalshiBookError):
        book.apply(delta())
    book.apply(snapshot(), received_at=123)
    assert book.last_update("A") == 123
    book.disconnect()
    assert book.last_update("A") is None
    assert book.is_ready("A") is False
    with pytest.raises(KalshiBookError):
        book.apply(delta(seq=3))
    book.apply(snapshot(seq=100))
    assert book.is_ready("A")


def test_replacement_snapshot_removes_prior_levels_and_empty_side_is_not_executable():
    book = KalshiOrderBook()
    book.apply(snapshot())
    replacement = snapshot(seq=2)
    replacement["msg"]["no_dollars_fp"] = []
    book.apply(replacement)
    assert book.is_ready("A")
    assert book.quote("A", "yes") is None
    assert book.quote("A", "no") is not None


def test_legacy_cent_fields_are_not_silently_treated_as_dollars():
    book = KalshiOrderBook()
    malformed = snapshot()
    malformed["msg"].pop("yes_dollars_fp")
    malformed["msg"]["yes"] = [[40, 10]]
    with pytest.raises(KalshiBookError):
        book.apply(malformed)


def test_subscription_requests_realtime_fixed_point_books():
    message = KalshiClient.subscription_message(["A", "B", "A"])
    assert message["params"] == {
        "channels": ["orderbook_delta"], "market_tickers": ["A", "B"], "update_interval_ms": 0,
        "use_yes_price": False,
    }
