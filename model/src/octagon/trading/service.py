"""Authenticated local controls and background collectors for paper/demo/live use."""

from __future__ import annotations

import asyncio
import copy
import hmac
import json
import os
import threading
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from octagon.api import findings
from octagon.trading.autoplan import MarketCache, build_plan, quickstart_mappings
from octagon.trading.engine import IDENTIFIER, TradingEngine
from octagon.trading.kalshi import KalshiError


class MappingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bout_id: str = Field(min_length=1, max_length=160)
    ticker: str = Field(min_length=1, max_length=160)
    yes_fighter: str = Field(min_length=1, max_length=160)
    f1: str = Field(min_length=1, max_length=160)
    f2: str = Field(min_length=1, max_length=160)
    confirmed: StrictBool = False


class ConfigureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_slug: str = Field(pattern=r"^[A-Za-z0-9_-]{1,160}$")
    espn_event_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,160}$")
    budget_dollars: str = Field(min_length=1, max_length=16)
    mappings: list[MappingRequest] = Field(min_length=1, max_length=30)


class QuickstartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    budget_dollars: str = Field(min_length=1, max_length=16)


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=160)
    config_version: str = Field(pattern=r"^[a-f0-9]{64}$")


def local_gateway(url: str) -> str:
    parsed = urlparse(url)
    if (parsed.scheme != "ws" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path != "/ws"):
        raise ValueError("Fight gateway must be a loopback ws:// address ending in /ws")
    return url


class Recorder:
    """Bounded local JSONL journal for later chronological replay (no credentials)."""
    def __init__(self, directory: Path, max_bytes: int = 25_000_000):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "observations.jsonl"
        self.max_bytes = max_bytes
        self.lock = threading.Lock()

    def __call__(self, kind: str, data):
        row = {"received_at": datetime.now(timezone.utc).isoformat(), "kind": kind, "data": data}
        encoded = json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n"
        with self.lock:
            if self.path.exists() and self.path.stat().st_size + len(encoded.encode()) > self.max_bytes:
                for number in range(3, 0, -1):
                    old = self.path.with_suffix(f".jsonl.{number}")
                    if old.exists():
                        if number == 3:
                            old.unlink()
                        else:
                            old.replace(self.path.with_suffix(f".jsonl.{number + 1}"))
                self.path.replace(self.path.with_suffix(".jsonl.1"))
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded)


@contextmanager
def process_lease(directory: Path):
    """A single process owns a journal; a crash releases the OS lock."""
    import fcntl

    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "service.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another trading service already owns this state directory") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


async def collect_fights(engine: TradingEngine, gateway_url: str):
    from websockets.asyncio.client import connect

    delay = 1
    while True:
        try:
            async with connect(gateway_url, open_timeout=5, ping_interval=10, ping_timeout=10,
                               max_size=2_000_000, proxy=None) as websocket:
                delay = 1
                while True:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=10)
                    message = json.loads(raw)
                    if not isinstance(message, dict):
                        raise ValueError("Invalid fight feed")
                    await asyncio.to_thread(engine.update_feed, message)
        except asyncio.CancelledError:
            raise
        except Exception:
            engine.disconnect_feed()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
        finally:
            engine.disconnect_feed()


async def collect_markets(engine: TradingEngine):
    import ssl

    import certifi
    from websockets.asyncio.client import connect

    # python.org macOS builds ship without system CA roots; use certifi's,
    # matching what requests already does for the REST client.
    tls = ssl.create_default_context(cafile=certifi.where())
    delay = 1
    while True:
        config = engine.config
        tickers = tuple(m["ticker"] for m in config["mappings"]) if config else ()
        if not tickers:
            await asyncio.sleep(1)
            continue
        try:
            headers = await asyncio.to_thread(engine.client.websocket_headers)
            async with connect(engine.client.websocket_url, additional_headers=headers,
                               open_timeout=10, ping_interval=10, ping_timeout=10,
                               max_size=2_000_000, proxy=None, ssl=tls) as websocket:
                engine.disconnect_book()
                await websocket.send(json.dumps(engine.client.subscription_message(tickers)))
                delay = 1
                while True:
                    configured = tuple(m["ticker"] for m in (engine.config or {}).get("mappings", []))
                    if configured != tickers:
                        break
                    try:
                        raw = await asyncio.wait_for(websocket.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        continue
                    await asyncio.to_thread(engine.update_book, json.loads(raw))
        except asyncio.CancelledError:
            raise
        except Exception:
            engine.disconnect_book()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
        finally:
            engine.disconnect_book()


async def decide(engine: TradingEngine):
    while True:
        try:
            await asyncio.to_thread(engine.tick)
        except asyncio.CancelledError:
            engine.running.clear()
            raise
        except Exception:
            engine.running.clear()
            engine.message = "Trading worker stopped after an error; inspect the journal before restarting."
        await asyncio.sleep(2)


def create_app(engine: TradingEngine, token: str, *, background: bool = False,
               gateway_url: str = "ws://127.0.0.1:8765/ws", market_stream: bool = False,
               preparer=None) -> FastAPI:
    if len(token) < 32 or token.strip() != token:
        raise ValueError("ICTUS_TRADING_TOKEN must be a random secret of at least 32 characters")
    gateway_url = local_gateway(gateway_url)
    origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    engine.market_stream_required = market_stream

    @asynccontextmanager
    async def lifespan(app):
        tasks = []
        if background:
            tasks = [asyncio.create_task(collect_fights(engine, gateway_url)),
                     asyncio.create_task(decide(engine))]
            if market_stream:
                tasks.append(asyncio.create_task(collect_markets(engine)))
        try:
            yield
        finally:
            engine.running.clear()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            engine.disconnect_feed()
            engine.disconnect_book()

    app = FastAPI(title="Ictus paper/demo trading", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"], allow_credentials=False)

    def authorize(request: Request):
        origin = request.headers.get("origin")
        if origin is not None and origin not in origins:
            raise HTTPException(403, "Trading controls are available from the local dashboard only")
        supplied = request.headers.get("authorization", "")
        if len(supplied) > 4096 or not hmac.compare_digest(
            supplied.encode("utf-8"), ("Bearer " + token).encode("utf-8")
        ):
            raise HTTPException(401, "Enter the local ICTUS_TRADING_TOKEN")

    auth = [Depends(authorize)]

    @app.exception_handler(ValueError)
    async def invalid_request(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(KalshiError)
    async def exchange_error(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.get("/api/trading/status", dependencies=auth)
    def status():
        return engine.status()

    @app.get("/api/trading/cards", dependencies=auth)
    def cards():
        return findings.list_cards()

    @app.get("/api/trading/cards/{slug}", dependencies=auth)
    def card(slug: str):
        if not IDENTIFIER.fullmatch(slug):
            raise HTTPException(400, "Invalid card slug")
        result = findings.card_detail(slug)
        if result is None:
            raise HTTPException(404, "Frozen model card not found")
        return result

    @app.get("/api/trading/market/{ticker}", dependencies=auth)
    def market(ticker: str):
        if not IDENTIFIER.fullmatch(ticker):
            raise HTTPException(400, "Invalid ticker")
        return engine.client.get_market(ticker)

    @app.post("/api/trading/configure", dependencies=auth)
    def configure(body: ConfigureRequest):
        return engine.configure(body.model_dump(), card(body.card_slug))

    @app.post("/api/trading/start", dependencies=auth)
    def start(body: StartRequest):
        return engine.start(session_id=body.session_id, config_version=body.config_version)

    @app.post("/api/trading/stop", dependencies=auth)
    def stop():
        return engine.stop()

    @app.post("/api/trading/reconcile", dependencies=auth)
    def reconcile():
        return engine.reconcile()

    markets = MarketCache(engine.client)

    def current_plan() -> dict:
        with engine.feed_lock:
            feed = copy.deepcopy(engine.feed)
        try:
            open_markets = markets.get()
        except (KalshiError, RuntimeError, ValueError):
            open_markets = None
        plan = build_plan(feed, findings.list_cards(), findings.card_detail, open_markets or [],
                          in_fight=engine.inplay is not None)
        if open_markets is None and not plan["problem"]:
            plan["problem"] = "Can't reach Kalshi to find tonight's markets."
        return plan

    @app.get("/api/trading/plan", dependencies=auth)
    def plan():
        return current_plan()

    @app.post("/api/trading/quickstart", dependencies=auth)
    def quickstart(body: QuickstartRequest):
        """Amount in, session running: auto-mapped fights, confirmed by this one action."""
        if engine.running.is_set():
            raise ValueError("Already running. Stop first to change the amount.")
        proposal = current_plan()
        if not proposal["card"]:
            raise ValueError(proposal["problem"] or "No predictions for this event yet.")
        same_event = bool(engine.config and engine.session_id
                          and engine.config["espn_event_id"] == proposal["event"]["espn_event_id"])
        orders = engine.ledger.orders(engine.session_id) if same_event else []
        attempted = {o["bout_id"].split(":")[0] for o in orders}
        mappings = quickstart_mappings(proposal, engine.config if same_event else None, attempted)
        if not mappings:
            raise ValueError(proposal["problem"] or "No fights can be traded right now.")
        if any(o["reserved"] for o in orders):
            engine.reconcile()
        status = engine.configure({"card_slug": proposal["card"]["slug"],
                                   "espn_event_id": proposal["event"]["espn_event_id"],
                                   "budget_dollars": body.budget_dollars, "mappings": mappings},
                                  card(proposal["card"]["slug"]))
        return engine.start(session_id=status["event"]["session_id"],
                            config_version=status["config_version"])

    @app.get("/api/trading/prepare", dependencies=auth)
    def prepare_status():
        return preparer.status() if preparer else {"state": "unavailable", "message": ""}

    @app.post("/api/trading/prepare", dependencies=auth)
    def prepare():
        if preparer is None:
            raise ValueError("Generating predictions is unavailable in this service")
        with engine.feed_lock:
            feed = copy.deepcopy(engine.feed) or {}
        name = (feed.get("meta") or {}).get("event_name")
        if not name:
            raise ValueError("Waiting for the live fight feed")
        pairs = [((b.get("fighter_a") or {}).get("name", ""), (b.get("fighter_b") or {}).get("name", ""))
                 for b in feed.get("data") or [] if isinstance(b, dict)]
        return preparer.start(name, pairs)

    return app


def run(mode: str, port: int, gateway_url: str, state_dir: Path, market_environment: str,
        *, policy=None, max_event_dollars=None, inplay_artifact: Path | None = None):
    import uvicorn

    from octagon.trading.kalshi import KalshiClient
    from octagon.trading.ledger import Ledger

    token = os.environ.get("ICTUS_TRADING_TOKEN", "")
    if len(token) < 32:
        raise ValueError("Set ICTUS_TRADING_TOKEN to a random secret of at least 32 characters in model/.env")
    if mode == "demo" and market_environment != "demo":
        raise ValueError("Demo mode requires the demo market environment")
    if mode == "live" and market_environment != "production":
        raise ValueError("Live mode requires the production market environment")
    if mode == "live" and max_event_dollars is None:
        raise ValueError("Live mode requires --max-event-dollars")
    inplay = None
    if inplay_artifact is not None:
        from octagon.inplay.model import InplayModel

        if not inplay_artifact.exists():
            raise ValueError(f"No between-rounds model at {inplay_artifact}; run `octagon train-inplay`")
        inplay = InplayModel.load(inplay_artifact)
    with process_lease(state_dir):
        client = KalshiClient.from_env(market_environment, live_enabled=mode == "live")
        try:
            stream = bool(os.environ.get("KALSHI_API_KEY_ID") and os.environ.get("KALSHI_PRIVATE_KEY_PATH"))
            if mode != "paper" and not stream:
                raise ValueError(f"{mode.title()} mode requires Kalshi API credentials in model/.env")
            engine = TradingEngine(Ledger(state_dir / "ledger.sqlite3"), client, mode=mode,
                                   record=Recorder(state_dir), policy=policy,
                                   max_budget=max_event_dollars, inplay=inplay,
                                   prefight_path=state_dir / "prefight_prices.json")
            from octagon.config import project_root
            from octagon.trading.prepare import CardPreparer

            app = create_app(engine, token, background=True, gateway_url=gateway_url, market_stream=stream,
                             preparer=CardPreparer(project_root(), state_dir / "prepare"))
            print(f"Ictus {mode} controls: http://127.0.0.1:{port}; dashboard: http://localhost:3000/trading")
            if mode == "live":
                print(f"LIVE MODE: REAL-MONEY orders on production Kalshi, hard cap ${engine.max_budget} per event.")
            if inplay is not None:
                print("IN-FIGHT: between-rounds trades enabled. No trading edge has been demonstrated.")
            else:
                print("Production orders disabled.")
            print("Service starts paused. Never expose this port publicly.")
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
        finally:
            client.close()
