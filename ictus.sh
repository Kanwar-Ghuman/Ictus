#!/usr/bin/env bash
# Start the fight feed, the trading bot and the dashboard together.
# Ctrl+C stops all three.
#
#   ./ictus.sh paper              practice, no money
#   ./ictus.sh live 5             real money, the bot can never spend more than $5 per event
#   ./ictus.sh paper --in-fight   also bet between rounds
set -euo pipefail
cd "$(dirname "$0")"
unset VIRTUAL_ENV

MODE="${1:-paper}"
shift || true
CAP=""
if [[ "$MODE" == "live" ]]; then
  CAP="${1:-}"
  shift || true
  if ! [[ "$CAP" =~ ^[0-9]+(\.[0-9]{1,2})?$ ]]; then
    echo "Usage: ./ictus.sh live <max dollars per event>   e.g. ./ictus.sh live 5" >&2
    exit 1
  fi
elif [[ "$MODE" != "paper" && "$MODE" != "demo" ]]; then
  echo "Mode must be paper, demo or live." >&2
  exit 1
fi

FLAGS=(--mode "$MODE" --max-source-age-seconds 600
       # Sizing chosen on Oct 31: Kelly-limited, but no extra per-order/per-fight caps.
       --max-order-fraction 1 --max-bout-fraction 1 --kelly-fraction 1)
if [[ "$MODE" == "live" ]]; then
  read -r -p "REAL MONEY on Kalshi, up to \$$CAP per event. Type yes to continue: " answer
  [[ "$answer" == "yes" ]] || { echo "Cancelled."; exit 1; }
  FLAGS+=(--confirm-real-money --max-event-dollars "$CAP")
fi
FLAGS+=("$@")  # e.g. --in-fight

trap 'trap - INT TERM EXIT; kill 0 2>/dev/null; wait 2>/dev/null' INT TERM EXIT

(cd model && uv run --extra trading python -m octagon.live) &
sleep 2
(cd model && uv run --extra trading python -m octagon.trading "${FLAGS[@]}") &
(cd frontend && npm run dev >/dev/null) &

for _ in $(seq 1 60); do
  curl -s -o /dev/null http://127.0.0.1:3000 && break
  sleep 1
done
echo
echo "Dashboard: http://localhost:3000   (Ctrl+C here stops everything)"
[[ -z "${ICTUS_NO_BROWSER:-}" ]] && command -v open >/dev/null && open http://localhost:3000
wait
