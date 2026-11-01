"""Local WebSocket gateway that fans out the live fight array.

Binds loopback by default. Clients subscribe to /ws; /live is the same
snapshot over HTTP for a quick curl check.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, Protocol

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from octagon.live.schema import EventSnapshot, envelope, error_envelope

VIEWER = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Octagon live</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; font-family: ui-sans-serif, system-ui, sans-serif;
         background: #0b0b0c; color: #f3f3f3; }
  header { padding: 20px 24px 8px; }
  header p { margin: 4px 0 0; color: #9a9aa2; font-size: 13px; }
  .live { margin: 16px 24px; padding: 20px; border: 1px solid #2a2a30;
          border-radius: 12px; background: #141417; }
  .live.idle { opacity: .7; }
  .badge { display: inline-block; background: #c81e1e; color: white;
           font-size: 11px; font-weight: 700; letter-spacing: .08em;
           padding: 3px 8px; border-radius: 999px; }
  .clock { font-variant-numeric: tabular-nums; font-size: 28px;
           font-weight: 700; margin: 8px 0 16px; }
  .row { display: grid; grid-template-columns: 1fr auto 1fr; gap: 16px;
         align-items: start; }
  .name { font-size: 22px; font-weight: 650; }
  .sub { color: #9a9aa2; font-size: 13px; margin-top: 4px; }
  .stat { font-variant-numeric: tabular-nums; font-size: 15px; margin-top: 8px; }
  .vs { align-self: center; color: #6d6d75; font-weight: 700; }
  .list { margin: 8px 24px 32px; }
  .bout { display: grid; grid-template-columns: 90px 1fr auto 1fr;
          gap: 12px; padding: 10px 0; border-top: 1px solid #23232a;
          font-size: 14px; }
  .status { color: #9a9aa2; }
  .status.in_progress { color: #ff4d4d; font-weight: 700; }
  .status.final { color: #8bd48b; }
  .right { text-align: right; }
</style>
<header>
  <h1 id="event">Octagon live</h1>
  <p id="meta">connecting…</p>
</header>
<section id="live" class="live idle">waiting for a live bout</section>
<section class="list" id="card"></section>
<script>
const liveEl = document.getElementById('live');
const cardEl = document.getElementById('card');
const eventEl = document.getElementById('event');
const metaEl = document.getElementById('meta');
function stats(f) {
  const s = f.stats || {};
  if (s.sigStrikes) {
    return 'sig ' + s.sigStrikes + ' · td ' + (s.takedowns || '0') +
           ' · ctrl ' + (s.timeInControl || '0:00');
  }
  return f.odds || '';
}
function render(body) {
  if (!body.success) { metaEl.textContent = body.error || 'error'; return; }
  const m = body.meta || {};
  eventEl.textContent = m.event_name || 'Octagon live';
  metaEl.textContent = (m.venue || '') + ' · seq ' + m.seq + ' · ' + (m.captured_at || '');
  const fights = body.data || [];
  const live = fights.find(b => b.status === 'in_progress');
  if (!live) {
    liveEl.className = 'live idle';
    liveEl.textContent = 'no bout in progress';
  } else {
    liveEl.className = 'live';
    const clock = live.clock ? ('R' + live.round + '  ' + live.clock) : ('R' + live.round);
    liveEl.innerHTML =
      '<span class="badge">LIVE</span>' +
      '<div class="clock">' + clock + ' · ' + (live.weight_class || '') + '</div>' +
      '<div class="row">' +
        '<div><div class="name">' + live.fighter_a.name + '</div>' +
        '<div class="sub">' + (live.fighter_a.record || '') + ' · ' +
          (live.fighter_a.odds || '') + '</div>' +
        '<div class="stat">' + stats(live.fighter_a) + '</div></div>' +
        '<div class="vs">VS</div>' +
        '<div class="right"><div class="name">' + live.fighter_b.name + '</div>' +
        '<div class="sub">' + (live.fighter_b.record || '') + ' · ' +
          (live.fighter_b.odds || '') + '</div>' +
        '<div class="stat">' + stats(live.fighter_b) + '</div></div>' +
      '</div>';
  }
  cardEl.innerHTML = fights.map(b => {
    const result = b.winner ? (b.winner + (b.method ? ' · ' + b.method : '')) : '';
    return '<div class="bout"><div class="status ' + b.status + '">' + b.status +
      '</div><div>' + b.fighter_a.name + '</div><div>' + (b.clock ? ('R' + b.round + ' ' + b.clock) : '') +
      '</div><div class="right">' + (result || b.fighter_b.name) + '</div></div>';
  }).join('');
}
const sock = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://')
  + location.host + '/ws');
sock.onmessage = (event) => render(JSON.parse(event.data));
sock.onclose = () => { metaEl.textContent = 'disconnected'; };
</script>
</html>
"""


class Collector(Protocol):
    source: str

    def snapshot(self) -> EventSnapshot: ...


class Hub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.latest: dict[str, Any] | None = None
        self.seq = 0

    async def register(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.clients.add(websocket)
        if self.latest is not None:
            await websocket.send_json(self.latest)

    def drop(self, websocket: WebSocket) -> None:
        self.clients.discard(websocket)

    async def publish(self, message: dict[str, Any]) -> None:
        self.latest = message
        stale: list[WebSocket] = []
        for client in self.clients:
            try:
                await client.send_json(message)
            except Exception:
                stale.append(client)
        for client in stale:
            self.clients.discard(client)


def create_app(collector: Collector, interval: float = 1.0) -> FastAPI:
    hub = Hub()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if interval > 0:
            task = asyncio.create_task(_poll(collector, hub, interval))
            app.state.poll_task = task
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            closer = getattr(collector, "close", None)
            if closer is not None:
                closer()

    app = FastAPI(title="Octagon live gateway", version="0.1.0", lifespan=lifespan)
    app.state.hub = hub
    app.state.collector = collector

    @app.get("/", response_class=HTMLResponse)
    def viewer() -> str:
        return VIEWER

    @app.get("/live")
    def live() -> JSONResponse:
        if hub.latest is None:
            message = _collect(collector, hub)
            return JSONResponse(message)
        return JSONResponse(hub.latest)

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        if hub.latest is None:
            hub.latest = _collect(collector, hub)
        await hub.register(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            hub.drop(websocket)

    return app


def _collect(collector: Collector, hub: Hub) -> dict[str, Any]:
    hub.seq += 1
    try:
        snapshot = collector.snapshot()
    except Exception as exc:
        return error_envelope(str(exc), hub.seq, getattr(collector, "source", "unknown"))
    return envelope(
        snapshot, source=getattr(collector, "source", "unknown"), seq=hub.seq
    )


async def _poll(collector: Collector, hub: Hub, interval: float) -> None:
    try:
        while True:
            message = await asyncio.to_thread(_collect, collector, hub)
            # Publish successful polls too: an unchanged card is a heartbeat,
            # and event-only changes must reach consumers. The envelope keeps
            # source time separate so a heartbeat cannot refresh stale data.
            await hub.publish(message)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        raise


def build_collector(
    mode: str,
    event_id: str | None,
    headed: bool = False,
) -> Collector:
    if mode == "browser":
        from octagon.live.browser import BrowserCollector
        from octagon.live.http import HttpCollector
        if not event_id:
            event_id = HttpCollector()._discover()
        return BrowserCollector(event_id=event_id, headed=headed)
    if mode not in {"http", "auto"}:
        raise ValueError(f"Unknown live mode '{mode}'")
    from octagon.live.http import HttpCollector
    return HttpCollector(event_id=event_id)


def run(
    host: str = "127.0.0.1",
    port: int = 8765,
    interval: float = 1.0,
    mode: str = "http",
    event_id: str | None = None,
    headed: bool = False,
) -> None:
    import uvicorn

    collector = build_collector(mode, event_id, headed=headed)
    app = create_app(collector, interval=interval)
    print(f"Live gateway  http://{host}:{port}/")
    print(f"WebSocket     ws://{host}:{port}/ws")
    print(f"JSON snapshot http://{host}:{port}/live")
    print(f"mode={mode} interval={interval}s event_id={event_id or 'auto'}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def snapshot_once(mode: str = "http", event_id: str | None = None) -> dict[str, Any]:
    collector = build_collector(mode, event_id)
    snapshot = collector.snapshot()
    return envelope(snapshot, source=collector.source, seq=1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Local UFC live WebSocket gateway")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--interval", type=float, default=1.0,
                        help="seconds between ESPN polls (1s is near-live)")
    parser.add_argument("--mode", choices=("http", "browser", "auto"), default="http")
    parser.add_argument("--event-id", default=None, help="ESPN event id (auto-detect tonight)")
    parser.add_argument("--headed", action="store_true", help="show Chromium in browser mode")
    parser.add_argument("--once", action="store_true",
                        help="print one JSON snapshot and exit")
    args = parser.parse_args(argv)
    if args.once:
        print(json.dumps(snapshot_once(args.mode, args.event_id), indent=2,
                         ensure_ascii=False))
        return
    run(
        host=args.host,
        port=args.port,
        interval=args.interval,
        mode=args.mode,
        event_id=args.event_id,
        headed=args.headed,
    )
