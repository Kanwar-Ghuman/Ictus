"""python -m octagon.trading --mode paper (never auto-starts orders)."""

import argparse
from decimal import Decimal, InvalidOperation
from pathlib import Path

from octagon.config import load_dotenv, project_root
from octagon.trading.risk import RiskPolicy
from octagon.trading.service import run


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
    parser.add_argument("--max-order-fraction", type=fraction, default=defaults.max_order_fraction,
                        help="Largest single order as a fraction of the event budget")
    parser.add_argument("--max-bout-fraction", type=fraction, default=defaults.max_bout_fraction,
                        help="Largest spend on one bout as a fraction of the event budget")
    parser.add_argument("--kelly-fraction", type=fraction, default=defaults.kelly_fraction,
                        help="Fraction of the Kelly stake to use (at most 1, never over-Kelly)")
    parser.add_argument("--max-source-age-seconds", type=float, default=defaults.max_source_age_seconds,
                        help="Oldest acceptable ESPN espn_updated_at; ESPN often changes it only every 1-2 min")
    parser.add_argument("--in-fight", action="store_true",
                        help="Also trade between rounds with the between-rounds model (off by default)")
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
    policy = RiskPolicy(max_order_fraction=args.max_order_fraction,
                        max_bout_fraction=args.max_bout_fraction,
                        kelly_fraction=args.kelly_fraction,
                        max_source_age_seconds=args.max_source_age_seconds)
    try:
        run(args.mode, args.port, args.gateway_url, args.state_dir, environment,
            policy=policy, max_event_dollars=args.max_event_dollars,
            inplay_artifact=args.inplay_artifact if args.in_fight else None)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
