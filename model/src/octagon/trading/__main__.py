"""python -m octagon.trading --mode paper (never auto-starts orders)."""

import argparse
from decimal import Decimal, InvalidOperation
from pathlib import Path

from octagon.config import load_dotenv, project_root
from octagon.trading.risk import RiskPolicy
from octagon.trading.service import run


def unit_interval(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("Expected a number") from None
    if not value.is_finite() or not 0 <= value < 1:
        raise argparse.ArgumentTypeError("Must be at least 0 and less than 1")
    return value


def fraction(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("Expected a number") from None
    if not value.is_finite() or not 0 < value <= 1:
        raise argparse.ArgumentTypeError("Must be greater than 0 and at most 1")
    return value


def dollars(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("Expected a dollar amount") from None
    if not value.is_finite() or value <= 0 or value != value.quantize(Decimal("0.01")):
        raise argparse.ArgumentTypeError("Must be positive dollars with at most two decimals")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ictus budgeted Kalshi paper/demo/live trading")
    parser.add_argument("--mode", choices=("paper", "demo", "live"), default="paper")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--gateway-url", default="ws://127.0.0.1:8765/ws")
    parser.add_argument("--state-dir", type=Path, default=project_root() / "trading-state")
    parser.add_argument("--market-environment", choices=("production", "demo"), default=None,
                        help="Paper defaults to production public data; demo requires demo")
    parser.add_argument("--confirm-real-money", action="store_true",
                        help="Required with --mode live: orders spend real money on production Kalshi")
    parser.add_argument("--max-event-dollars", type=dollars, default=None,
                        help="Hard cap on any event budget the dashboard may set (required for live)")
    defaults = RiskPolicy()
    parser.add_argument("--min-edge", type=fraction, default=defaults.min_net_edge,
                        help="Minimum expected profit per $1 contract after fees (default 0.03)")
    parser.add_argument("--min-price", type=unit_interval, default=defaults.min_price,
                        help="Never pay less than this per contract; longshots lose (default 0.20)")
    parser.add_argument("--draw-rate", type=unit_interval, default=defaults.draw_settlement_rate,
                        help="Share of 50-cent draw/no-contest settlements (default 0.018, measured)")
    parser.add_argument("--venue-lag", action="store_true",
                        help="Also require the Kalshi ask to lag a same-time sportsbook price")
    parser.add_argument("--max-bout-fraction", type=fraction, default=defaults.max_bout_fraction,
                        help="Most of the event budget one fight may use across all its bets")
    parser.add_argument("--inplay-reserve", type=fraction, default=defaults.inplay_reserve,
                        help="With --in-fight, share of the budget kept for between-rounds bets")
    parser.add_argument("--min-ufc-fights", type=int, default=defaults.min_ufc_fights,
                        help="UFC fights each fighter needs for a pre-fight bet (0 allows debuts)")
    parser.add_argument("--max-source-age-seconds", type=float, default=defaults.max_source_age_seconds,
                        help="Oldest acceptable ESPN espn_updated_at; ESPN often changes it only every 1-2 min")
    parser.add_argument("--in-fight", action="store_true",
                        help="Also trade during the fight, from the live clock and stats (off by default)")
    parser.add_argument("--inplay-artifact", type=Path, default=project_root() / "artifacts" / "inplay.json",
                        help="Between-rounds model from `octagon train-inplay`")
    args = parser.parse_args(argv)
    load_dotenv()
    if not 1024 <= args.port <= 65535:
        parser.error("Port must be between 1024 and 65535")
    if args.mode == "live" and not args.confirm_real_money:
        parser.error("Live mode spends real money; pass --confirm-real-money to proceed")
    if args.mode == "live" and args.max_event_dollars is None:
        parser.error("Live mode requires --max-event-dollars")
    if not 0 < args.max_source_age_seconds <= 600:
        parser.error("--max-source-age-seconds must be greater than 0 and at most 600")
    environment = args.market_environment or ("demo" if args.mode == "demo" else "production")
    if args.min_ufc_fights < 0:
        parser.error("--min-ufc-fights must be 0 or more")
    policy = RiskPolicy(min_net_edge=args.min_edge,
                        min_price=args.min_price,
                        max_bout_fraction=args.max_bout_fraction,
                        inplay_reserve=args.inplay_reserve,
                        min_ufc_fights=args.min_ufc_fights,
                        max_source_age_seconds=args.max_source_age_seconds,
                        draw_settlement_rate=args.draw_rate,
                        venue_lag=args.venue_lag)
    try:
        run(args.mode, args.port, args.gateway_url, args.state_dir, environment,
            policy=policy, max_event_dollars=args.max_event_dollars,
            inplay_artifact=args.inplay_artifact if args.in_fight else None)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
