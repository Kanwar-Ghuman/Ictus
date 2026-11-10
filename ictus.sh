#!/usr/bin/env bash
# Fight night in one command: the fight feed, the trading bot and the dashboard.
# Ctrl+C stops all three.
#
#   ./ictus.sh              practice, no money
#   ./ictus.sh live 20      real money, the bot can never spend more than $20 on the event
#   ./ictus.sh demo         Kalshi's demo exchange
#   ./ictus.sh stop         stop whatever an earlier run left running
#
# The bot trades before and during fights. Add --pre-fight-only to stop it at
# the opening bell. Any other option is passed to the bot, e.g. --min-edge 0.02.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd -P)"
cd "$ROOT"
unset VIRTUAL_ENV

FEED_PORT=8765
BOT_PORT=8002
DASHBOARD_PORT=3000
LOGS="$ROOT/model/trading-state/logs"
ENV_FILE="$ROOT/model/.env"

say()  { printf '%s\n' "$*"; }
fail() { printf 'ictus: %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

# --- what is on a port, and is it ours -------------------------------------

listeners() { lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null || true; }

# A process belongs to Ictus when it was started from inside this folder.
is_ours() {
  local cwd
  cwd="$(lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)"
  [[ "$cwd" == "$ROOT" || "$cwd" == "$ROOT"/* ]]
}

# Stop our own leftovers on a port. Anything else is reported, never killed.
free_port() {
  local port="$1" label="$2" pid
  for pid in $(listeners "$port"); do
    if is_ours "$pid"; then
      kill "$pid" 2>/dev/null || true
    else
      fail "port $port ($label) is used by another program (pid $pid: $(ps -o comm= -p "$pid")). Close it and try again."
    fi
  done
  for _ in $(seq 1 20); do
    [[ -z "$(listeners "$port")" ]] && return 0
    sleep 0.25
  done
  for pid in $(listeners "$port"); do kill -9 "$pid" 2>/dev/null || true; done
}

free_ports() {
  free_port "$FEED_PORT" "fight feed"
  free_port "$BOT_PORT" "trading bot"
  free_port "$DASHBOARD_PORT" "dashboard"
}

# --- arguments --------------------------------------------------------------

MODE="${1:-paper}"
[[ $# -gt 0 ]] && shift
case "$MODE" in
  -h|--help|help) usage ;;
  stop) free_ports; say "Stopped."; exit 0 ;;
  paper|demo|live) ;;
  *) say "Unknown mode: $MODE"; usage 1 ;;
esac

CAP=""
if [[ "$MODE" == "live" ]]; then
  CAP="${1:-}"
  [[ $# -gt 0 ]] && shift
  [[ "$CAP" =~ ^[0-9]+(\.[0-9]{1,2})?$ ]] \
    || fail "live needs the most it may spend on the event, e.g. ./ictus.sh live 20"
fi

IN_FIGHT=1
EXTRA=()
for option in "$@"; do
  case "$option" in
    --pre-fight-only) IN_FIGHT=0 ;;
    --in-fight) IN_FIGHT=1 ;;  # the default; accepted so old commands keep working
    *) EXTRA+=("$option") ;;
  esac
done

# --- checks before anything starts -----------------------------------------

command -v uv >/dev/null  || fail "uv is not installed. See https://docs.astral.sh/uv/"
command -v npm >/dev/null || fail "npm is not installed. Install Node.js first."

env_value() { sed -n "s/^$1=//p" "$ENV_FILE" 2>/dev/null | head -n 1 | tr -d "\"'"; }

[[ -f "$ENV_FILE" ]] || cp "$ROOT/model/.env.example" "$ENV_FILE"
if [[ "$(env_value ICTUS_TRADING_TOKEN | wc -c)" -lt 33 ]]; then
  # A local secret between the dashboard and the bot. It is not a Kalshi key.
  token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  grep -v '^ICTUS_TRADING_TOKEN=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
  printf 'ICTUS_TRADING_TOKEN=%s\n' "$token" >> "$ENV_FILE.tmp"
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  say "Created a dashboard token in model/.env."
fi

if [[ "$MODE" != "paper" ]]; then
  key_path="$(env_value KALSHI_PRIVATE_KEY_PATH)"
  [[ -n "$(env_value KALSHI_API_KEY_ID)" && -f "$key_path" ]] \
    || fail "$MODE mode needs KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH in model/.env (see model/docs/kalshi_trading.md)."
fi

[[ -f "$ROOT/model/artifacts/gbm.joblib" ]] \
  || say "Note: no trained model in model/artifacts. New predictions need: cd model && uv run python -m octagon train"

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  say "Installing the dashboard (first run only)…"
  (cd frontend && npm install --silent)
fi

if [[ "$IN_FIGHT" == 1 && ! -f "$ROOT/model/artifacts/inplay.json" ]]; then
  say "Training the in-fight model (first run only)…"
  if ! (cd model && uv run python -m octagon train-inplay >/dev/null 2>&1); then
    say "Could not train it, so tonight is pre-fight only."
    IN_FIGHT=0
  fi
fi

FLAGS=(--mode "$MODE" --max-source-age-seconds 600)
[[ "$IN_FIGHT" == 1 ]] && FLAGS+=(--in-fight)
if [[ "$MODE" == "live" ]]; then
  read -r -p "REAL MONEY on Kalshi, up to \$$CAP on this event. Type yes to continue: " answer
  [[ "$answer" == "yes" ]] || { say "Cancelled."; exit 1; }
  FLAGS+=(--confirm-real-money --max-event-dollars "$CAP")
fi
FLAGS+=(${EXTRA[@]+"${EXTRA[@]}"})

# --- start ------------------------------------------------------------------

free_ports
mkdir -p "$LOGS"
export PYTHONUNBUFFERED=1  # so the log files fill as things happen
trap 'trap - INT TERM EXIT; kill 0 2>/dev/null; wait 2>/dev/null' INT TERM EXIT

(cd model && exec uv run --extra trading python -m octagon.live) > "$LOGS/feed.log" 2>&1 &
FEED_PID=$!
(cd model && exec uv run --extra trading python -m octagon.trading "${FLAGS[@]}") > "$LOGS/bot.log" 2>&1 &
BOT_PID=$!
(cd frontend && exec npm run dev) > "$LOGS/dashboard.log" 2>&1 &
DASHBOARD_PID=$!

# Wait until a service answers. If it dies first, show why.
wait_for() {
  local label="$1" port="$2" pid="$3" log="$4"
  for _ in $(seq 1 120); do
    curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$port/" && return 0
    if ! kill -0 "$pid" 2>/dev/null; then
      say ""
      say "The $label stopped while starting. Last lines of $log:"
      tail -n 15 "$log" | sed 's/^/    /'
      exit 1
    fi
    sleep 0.5
  done
  fail "the $label did not start within a minute. See $log"
}

say "Starting…"
wait_for "fight feed" "$FEED_PORT" "$FEED_PID" "$LOGS/feed.log"
wait_for "trading bot" "$BOT_PORT" "$BOT_PID" "$LOGS/bot.log"
wait_for "dashboard" "$DASHBOARD_PORT" "$DASHBOARD_PID" "$LOGS/dashboard.log"

case "$MODE" in
  live) headline="REAL MONEY, at most \$$CAP on this event" ;;
  demo) headline="Kalshi demo exchange" ;;
  *)    headline="practice, no money" ;;
esac
say ""
say "Ictus is running: $headline."
[[ "$IN_FIGHT" == 1 ]] && say "Trades before and during fights." || say "Trades before fights only."
say "Dashboard: http://localhost:$DASHBOARD_PORT   Enter an amount and press Start."
say "Ctrl+C here stops everything. Logs: model/trading-state/logs/"
[[ -z "${ICTUS_NO_BROWSER:-}" ]] && command -v open >/dev/null && open "http://localhost:$DASHBOARD_PORT"
wait
