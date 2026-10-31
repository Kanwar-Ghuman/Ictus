"""CLI: python -m octagon <command>."""

import argparse
from pathlib import Path

from octagon.config import load_config, resolve_path


def cmd_init_db(args: argparse.Namespace, cfg: dict) -> None:
    from octagon.db.schema import connect, init_db

    db_path = resolve_path(cfg["data"]["db_path"])
    init_db(connect(db_path))
    print(f"Initialized schema in {db_path}")


GRECO_FILES = ["ufc_event_details.csv", "ufc_fight_results.csv", "ufc_fight_stats.csv",
               "ufc_fighter_details.csv", "ufc_fighter_tott.csv", "ufc_fight_details.csv"]
GRECO_RAW_URL = "https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main/"


def cmd_refresh_data(args: argparse.Namespace, cfg: dict) -> None:
    """Re-download Greco CSVs, rebuild the DB and features, re-run the audit."""
    import requests

    greco_dir = resolve_path(cfg["data"]["greco_dir"])
    greco_dir.mkdir(parents=True, exist_ok=True)
    for name in GRECO_FILES:
        resp = requests.get(GRECO_RAW_URL + name, timeout=120)
        resp.raise_for_status()
        (greco_dir / name).write_bytes(resp.content)
        print(f"  downloaded {name} ({len(resp.content) // 1024} KB)")

    cmd_build_db(args, cfg)
    cmd_build_features(args, cfg)
    print("\nRe-running the leakage audit on the fresh build:")
    cmd_audit(args, cfg)
    print("\nIf the audit passed, re-run `octagon train` so the artifact "
          "(params/calibration/blend) reflects the new data.")


def cmd_build_db(args: argparse.Namespace, cfg: dict) -> None:
    """Rebuild canonical tables and restore the cached regional histories."""
    from octagon.db.build import build_db

    db_path = resolve_path(cfg["data"]["db_path"])
    counts = build_db(
        db_path,
        greco_dir=resolve_path(cfg["data"]["greco_dir"]),
        bootstrap_dir=resolve_path(cfg["data"]["bootstrap_dir"]),
    )
    from octagon.db.schema import connect
    from octagon.db.supplemental import load_supplemental

    with connect(db_path) as conn:
        counts["supplemental_fights"] = load_supplemental(
            conn, resolve_path(cfg["data"].get("supplemental_path", "supplements/fights.yaml")))
    print(f"Rebuilt {db_path} from raw sources:")
    for table, n in counts.items():
        print(f"  {table:>18}: {n}")

    # Rebuilding drops every table, including regional_fights. Restoring the
    # point-in-time Sherdog cache here prevents a perfectly valid-looking
    # `build-db; build-features` run from silently training without debut data.
    sherdog_cache = resolve_path(cfg["data"]["sherdog_cache"])
    if sherdog_cache.exists():
        print("\nReloading cached regional records:")
        cmd_load_regional(args, cfg)


def cmd_build_features(args: argparse.Namespace, cfg: dict) -> None:
    from octagon.db.schema import connect
    from octagon.features.build import build_features, elo_kwargs

    conn = connect(resolve_path(cfg["data"]["db_path"]))
    df = build_features(conn, seed=cfg["seed"], **elo_kwargs(cfg))
    out = resolve_path(cfg["data"]["processed_dir"]) / "features.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)

    with_odds = df["f1_odds"].notna().sum()
    print(f"Wrote {out}: {len(df)} fights x {len(df.columns)} columns")
    print(f"  label balance: {df['label'].mean():.3f} (should sit near 0.5 after corner swaps)")
    print(f"  swapped: {df['swapped'].mean():.3f}")
    print(f"  fights with odds: {with_odds}")
    print(f"  date range: {df['date'].min()} -> {df['date'].max()}")


def cmd_train(args: argparse.Namespace, cfg: dict) -> None:
    """Tune the GBM with walk-forward CV, calibrate, and write the artifact.

    Default `--through` is splits.train_end. A later date fits on all fights
    up to that date (production card) and is not a holdout result.
    """
    import joblib
    import pandas as pd

    from octagon.eval import metrics
    from octagon.eval.report import semiannual_windows
    from octagon.models import calibration, ensemble, finish_round, gbm, logistic

    df = pd.read_parquet(resolve_path(cfg["data"]["processed_dir"]) / "features.parquet")
    train_end = cfg["splits"]["train_end"]
    through = args.through or train_end
    if through > str(df["date"].max()):
        through = str(df["date"].max())
    seed = cfg["seed"]
    include_raw = cfg["model"]["include_raw"]
    n_seeds = cfg["model"]["n_seeds"]
    windows = semiannual_windows("2016-12-31", through)

    if through > train_end:
        print(f"PRODUCTION FIT: Optuna + calibration walk-forward through {through} "
              f"({len(windows)} folds). This is not the frozen research split "
              f"(train_end={train_end}). Do not quote these params as a holdout result.")

    reused = None
    if getattr(args, "reuse_params", False):
        previous = resolve_path("artifacts/gbm.joblib")
        if not previous.exists():
            raise SystemExit("--reuse-params needs an existing artifacts/gbm.joblib")
        reused = joblib.load(previous)
        params, cv_loss = dict(reused["params"]), float(reused.get("cv_log_loss", float("nan")))
        print(f"Reusing GBM hyperparameters from the previous artifact "
              f"(tuned {reused.get('n_trials', '?')} trials, CV log loss {cv_loss:.4f}): "
              f"{params}")
    else:
        print(f"Tuning LightGBM: {args.trials} Optuna trials x {len(windows)} "
              f"walk-forward folds (2017 -> {through}) ...")
        params, cv_loss = gbm.tune(df, windows, n_trials=args.trials, seed=seed,
                                   include_raw=include_raw)
        print(f"  best walk-forward CV log loss: {cv_loss:.4f}")
        print(f"  params: {params}")

    oos = gbm.walk_forward_predict(df, windows, params, seed=seed,
                                   include_raw=include_raw, n_seeds=n_seeds)
    mask = oos.notna()
    y_oos = df.loc[mask, "label"].to_numpy(dtype=float)
    p_oos = oos[mask].to_numpy()
    iso = calibration.fit_isotonic(y_oos, p_oos)
    p_cal = calibration.apply(iso, p_oos)
    print(f"  train-era OOS ({mask.sum()} fights): "
          f"log loss {metrics.log_loss(y_oos, p_oos):.4f} -> "
          f"{metrics.log_loss(y_oos, p_cal):.4f} calibrated, "
          f"ECE {metrics.ece(y_oos, p_oos):.4f} -> {metrics.ece(y_oos, p_cal):.4f}")

    lr_C, lr_half_life, lr_loss = logistic.tune(df, windows)
    print(f"  logistic: C={lr_C:g}, recency half-life="
          f"{lr_half_life if lr_half_life else 'none'} "
          f"(train-era OOS log loss {lr_loss:.4f})")

    lr_oos = logistic.walk_forward_predict(
        df, windows, C=lr_C, half_life_years=lr_half_life)[mask].to_numpy()
    weight_lr = ensemble.tune_weight(y_oos, lr_oos, p_cal)
    p_blend = ensemble.blend(lr_oos, p_cal, weight_lr)
    print(f"  blend weight (LR share): {weight_lr:.2f}; train-era OOS log loss "
          f"{metrics.log_loss(y_oos, p_blend):.4f}")

    from octagon.models import baselines, market

    priced = mask & df["f1_odds"].notna() & df["f2_odds"].notna()
    p_mkt = baselines.market(df[priced])
    idx = mask[mask].index.get_indexer(priced[priced].index)
    stack_a, stack_b = market.fit_stack(
        df.loc[priced, "label"].to_numpy(dtype=float), p_mkt, p_blend[idx])
    print(f"  market stack (a=market, b=skill): a={stack_a:.3f}, b={stack_b:.3f} "
          f"on {int(priced.sum())} priced OOS fights")

    weight_round_base, round_loss = finish_round.tune_base_weight(df, windows, seed=seed)
    print(f"  round-of-finish base-rate share: {weight_round_base:.2f}; "
          f"train-era OOS round log loss {round_loss:.4f}")

    from octagon.models import method as method_model

    weight_method_base, method_loss = method_model.tune_base_weight(
        df, windows, seed=seed, include_raw=include_raw)
    print(f"  method base-rate share: {weight_method_base:.2f}; "
          f"train-era OOS method log loss {method_loss:.4f}")

    from octagon.models import debut, debut_stack

    p_blend_series = pd.Series(p_blend, index=df.index[mask])

    if reused is not None and reused.get("debut_params"):
        debut_params = dict(reused["debut_params"])
        print(f"\nReusing debut-model hyperparameters: {debut_params}")
    else:
        print(f"\nTuning debut model ({args.trials} trials) on fights where "
              f"either fighter has < {debut.DEBUT_THRESHOLD} UFC fights...")
        debut_params, debut_cv_loss = debut.tune(df, windows, n_trials=args.trials,
                                                 seed=seed, include_raw=include_raw)
        print(f"  debut model walk-forward CV log loss: {debut_cv_loss:.4f}")

    debut_oos = debut.walk_forward_predict(df, windows, debut_params, seed=seed,
                                           include_raw=include_raw, n_seeds=n_seeds)
    low_hist = debut.low_history_mask(df)
    compare_mask = mask & low_hist & debut_oos.notna()
    compare_idx = df.index[compare_mask]
    n_compare = len(compare_idx)

    debut_model = None
    debut_stack_params = None
    if n_compare >= 50:  # enough OOS low-history fights to trust a comparison
        y_compare = df.loc[compare_idx, "label"].to_numpy(dtype=float)
        p_blend_compare = p_blend_series.loc[compare_idx].to_numpy()
        p_debut_compare = debut_oos.loc[compare_idx].to_numpy()
        blend_loss = metrics.log_loss(y_compare, p_blend_compare)
        debut_loss = metrics.log_loss(y_compare, p_debut_compare)
        print(f"  low-history OOS comparison ({n_compare} fights): "
              f"main blend {blend_loss:.4f} vs. debut model {debut_loss:.4f}")
        if debut_loss < blend_loss:
            d_a, d_b = debut_stack.fit_stack(y_compare, p_blend_compare, p_debut_compare)
            stacked_loss = metrics.log_loss(
                y_compare, debut_stack.predict_stack(d_a, d_b, p_blend_compare, p_debut_compare))
            print(f"  debut model beats the blend -> stacking "
                  f"(a=blend {d_a:.3f}, b=debut {d_b:.3f}); "
                  f"stacked OOS log loss {stacked_loss:.4f}")
            debut_model = debut.fit(df[df["date"] <= through], debut_params,
                                    seed=seed, include_raw=include_raw, n_seeds=n_seeds)
            debut_stack_params = (d_a, d_b)
        else:
            print("  debut model does not beat the blend on held-out low-history "
                  "fights -> not used (predict.py will skip it)")
    else:
        print(f"  only {n_compare} low-history OOS fights — too few to compare "
              "reliably; debut model not used")

    artifacts = resolve_path("artifacts")
    artifacts.mkdir(exist_ok=True)
    metrics.reliability_diagram(
        {"GBM raw": (y_oos, p_oos), "GBM + isotonic": (y_oos, p_cal)},
        artifacts / "calibration_train_oos.png")
    final_model = gbm.fit(df[df["date"] <= through], params, seed=seed,
                          include_raw=include_raw, n_seeds=n_seeds)
    from octagon.lineage import feature_fingerprint

    feature_list = list(gbm.feature_frame(df, include_raw=include_raw).columns)
    joblib.dump({
        "params": params,
        "cv_log_loss": cv_loss,
        "iso": iso,
        "model": final_model,
        "shap_model": final_model.members[0] if hasattr(final_model, "members")
                      else final_model,
        "include_raw": include_raw,
        "n_seeds": n_seeds,
        "weight_lr": weight_lr,
        "lr_C": lr_C,
        "lr_half_life": lr_half_life,
        "market_stack": (stack_a, stack_b),
        "research_weight": float(
            (cfg.get("model") or {}).get("research_weight") or 0.0),
        "weight_round_base": weight_round_base,
        "weight_method_base": weight_method_base,
        "feature_list": feature_list,
        "feature_fingerprint": feature_fingerprint(df, through, include_raw),
        "feature_fingerprint_version": 1,
        "splits": dict(cfg["splits"]),
        "through": through,
        "seed": seed,
        "n_trials": (reused.get("n_trials") if reused is not None else args.trials),
        "params_reused": reused is not None,
        "debut_params": debut_params,
        # The estimator itself would be stale as soon as new fights arrive.
        # Prediction refits it on current point-in-time history when enabled.
        "debut_model": None,
        "debut_enabled": debut_model is not None,
        "debut_stack": debut_stack_params,
    }, artifacts / "gbm.joblib")
    print("Saved artifacts/gbm.joblib + calibration_train_oos.png")


def cmd_evaluate(args: argparse.Namespace, cfg: dict) -> None:
    import pandas as pd

    from octagon.eval.report import evaluate_split

    if args.split == "test":
        print("=" * 70)
        print("WARNING: evaluating on the TEST split (2024+). This is the final")
        print("holdout — do this once, at the end, and report what you get.")
        print("Repeated peeking turns test into a second validation set.")
        print("=" * 70)

    df = pd.read_parquet(resolve_path(cfg["data"]["processed_dir"]) / "features.parquet")
    reports_dir = resolve_path("reports")
    md = evaluate_split(df, cfg["splits"]["train_end"], cfg["splits"]["valid_end"],
                        args.split, reports_dir)
    out = reports_dir / f"evaluation_{args.split}.md"
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nWrote {out}")


def cmd_fetch_card(args: argparse.Namespace, cfg: dict) -> None:
    """Build a card YAML for the next UFC event from Wikipedia."""
    import yaml

    from octagon.scraping.wikipedia import card_yaml, fight_card, next_event

    if args.event:
        page = event_name = args.event
        iso_date = args.date or raise_missing_date()
    else:
        page, event_name, iso_date = next_event()
    bouts = fight_card(page)
    if not bouts:
        raise SystemExit(f"No announced bouts parsed from Wikipedia page '{page}'.")

    card = card_yaml(event_name, iso_date, bouts)
    # Fold accents before slugifying, or 'Medić' becomes 'medi'.
    from octagon.scraping.fighters import slug

    out = Path(args.out) if args.out else resolve_path("cards") / (
        slug(event_name).replace("-", "_") + ".yaml")
    out.parent.mkdir(exist_ok=True)
    out.write_text(yaml.safe_dump(card, sort_keys=False, allow_unicode=True),
                   encoding="utf-8")
    print(f"{event_name} — {iso_date}: {len(bouts)} bouts")
    for b in bouts:
        print(f"  {b['weight_class']}: {b['fighter1']} vs. {b['fighter2']}"
              + ("  [title]" if b["title_fight"] else ""))
    print(f"\nWrote {out}")
    print("Review the names (Wikipedia spellings can differ from ufcstats).")
    print("\n=== fetch-odds ===")
    _fill_card_odds(out, cfg, overwrite=True)
    print("Next:")
    print(f"  uv run python -m octagon fetch-media --card {out}")
    print(f"  uv run python -m octagon predict --card {out}")


def raise_missing_date():
    raise SystemExit("--date YYYY-MM-DD is required when --event is given")


def card_fighter_names(card_path: Path) -> list[str]:
    import yaml

    with open(card_path, encoding="utf-8") as fh:
        card = yaml.safe_load(fh)
    return [name for fight in card["fights"]
            for name in (fight["fighter1"], fight["fighter2"])]


def _fill_card_odds(card_path: Path, cfg: dict, overwrite: bool = True) -> int:
    """Write Odds API moneylines onto a card YAML. Returns fights filled."""
    import yaml

    from octagon.betting import odds_api
    from octagon.config import env_secret

    key = env_secret(cfg, "odds_api_key_env")
    if not key:
        print("No ODDS_API_KEY in model/.env — predict will ship skill-only "
              "on unpriced bouts.")
        return 0

    scrape = cfg.get("scraping") or {}
    try:
        events, meta = odds_api.fetch_mma_odds(
            key,
            sport=str(scrape.get("odds_api_sport") or odds_api.DEFAULT_SPORT),
            regions=str(scrape.get("odds_api_regions") or odds_api.DEFAULT_REGIONS),
        )
    except Exception as exc:  # noqa: BLE001 — surface the API error, never the key
        raise SystemExit(f"Odds API request failed: {exc}") from exc

    remaining = meta.get("remaining") or "?"
    print(f"Odds API: {len(events)} upcoming MMA events "
          f"({remaining} requests remaining this month).")

    with open(card_path, encoding="utf-8") as fh:
        card = yaml.safe_load(fh)
    card, n_filled = odds_api.write_odds_to_card(card, events, overwrite=overwrite)
    if n_filled:
        card_path.write_text(yaml.safe_dump(card, sort_keys=False, allow_unicode=True),
                             encoding="utf-8")
    n_fights = len(card.get("fights") or [])
    print(f"  matched {n_filled}/{n_fights} bouts -> {card_path}")
    if n_filled < n_fights:
        print("  Unmatched fights keep odds: null (skill-only). Names on the "
              "card must match the book listing.")
    return n_filled


def cmd_fetch_odds(args: argparse.Namespace, cfg: dict) -> None:
    """Pull upcoming moneylines from The Odds API onto a card YAML."""
    card_path = Path(args.card)
    if not card_path.exists():
        raise SystemExit(f"Card file not found: {card_path}")
    _fill_card_odds(card_path, cfg, overwrite=not args.keep_existing)


def cmd_fetch_media(args: argparse.Namespace, cfg: dict) -> None:
    """Portraits, records and flags (ufc.com, Wikipedia, then Sherdog)."""
    from octagon.scraping import fighters

    cards = ([Path(args.card)] if args.card
             else sorted(resolve_path("cards").glob("*.yaml")))
    missing = [p for p in cards if not p.exists()]
    if missing:
        raise SystemExit(f"Card file not found: {missing[0]}")

    names = [n for path in cards for n in card_fighter_names(path)]
    media_path = resolve_path(cfg["data"]["media_path"])
    image_dir = resolve_path(cfg["data"]["media_image_dir"])
    delay = args.delay if args.delay is not None else cfg["scraping"]["ufc_delay_seconds"]

    known = fighters.load_cache(media_path)
    todo = {fighters.normalize_name(n) for n in names} - (set() if args.force
                                                          else set(known))
    print(f"{len(set(names))} fighters on {len(cards)} card(s); "
          f"{len(todo)} to fetch at {delay:g}s apart "
          f"(~{len(todo) * delay / 60:.1f} min).")

    def report(record: dict) -> None:
        face = "portrait" if record["portrait"] else (
            "headshot" if record["headshot"] else "no image")
        flag = record["country_code"] or "--"
        print(f"  {record['name']:28} {flag}  {record['record'] or '-':10} {face}")

    media = fighters.refresh(names, media_path, image_dir, delay=delay,
                             force=args.force, on_progress=report)
    with_face = sum(1 for r in media.values() if r["portrait"] or r["headshot"])
    print(f"\n{with_face}/{len(media)} fighters have a photo. "
          f"Cache: {media_path}")


def cmd_fetch_context(args: argparse.Namespace, cfg: dict) -> None:
    """Scrape day-before circumstances, pre-UFC records, style tags, news + YouTube buzz."""
    from octagon.config import env_secret
    from octagon.scraping import context as card_context
    from octagon.scraping import fighters

    card_path = Path(args.card)
    if not card_path.exists():
        raise SystemExit(f"Card file not found: {card_path}")

    media = fighters.load_cache(resolve_path(cfg["data"]["media_path"]))
    yt_key = None if getattr(args, "skip_youtube", False) else env_secret(
        cfg, "youtube_api_key_env")
    if yt_key is None and not getattr(args, "skip_youtube", False):
        print("No YOUTUBE_API_KEY in model/.env — skipping YouTube buzz "
              "(news + Wikipedia still run).")

    scrape = cfg.get("scraping") or {}
    payload = card_context.fetch_card_context(
        card_path,
        wiki_page=args.event,
        media_cache=media,
        delay=args.delay if args.delay is not None else 1.0,
        youtube_api_key=yt_key,
        youtube_videos_per_bout=int(scrape.get("youtube_videos_per_bout", 4)),
        youtube_comments_per_video=int(
            scrape.get("youtube_comments_per_video", 25)),
    )
    out = card_context.context_path(card_path)
    n_short = sum(
        1 for f in payload["fighters"].values()
        if f.get("circumstances", {}).get("short_notice")
        or f.get("circumstances", {}).get("late_replacement"))
    n_debut_rec = sum(1 for f in payload["fighters"].values() if f.get("pro_record"))
    n_yt = sum(1 for b in payload.get("bouts", [])
               if (b.get("youtube") or {}).get("n_signals", 0) > 0)
    print(f"{payload['event']}: context for {len(payload['fighters'])} fighters")
    print(f"  short-notice / late-replacement flags: {n_short}")
    print(f"  fighters with a pro-record prior: {n_debut_rec}")
    print(f"  bouts with YouTube buzz signals: {n_yt}/{len(payload.get('bouts', []))}")
    print(f"  Wrote {out}")
    print("Next: uv run python -m octagon predict --card "
          f"{card_path}")


def cmd_day_before(args: argparse.Namespace, cfg: dict) -> None:
    """Full day-before routine: refresh → media → context → odds → predict.

    Upcoming moneylines come from The Odds API when ODDS_API_KEY is set.
    Unmatched bouts stay skill-only.
    """
    card_path = Path(args.card)
    if not card_path.exists():
        raise SystemExit(f"Card file not found: {card_path}")

    if not args.skip_refresh:
        print("=== refresh-data ===")
        cmd_refresh_data(args, cfg)
    print("\n=== fetch-media ===")
    cmd_fetch_media(args, cfg)
    print("\n=== fetch-context ===")
    # Media crawl-delay is 15s; Wikipedia is fine at ~1s.
    ctx_args = argparse.Namespace(
        card=args.card, event=getattr(args, "event", None), delay=1.0,
        skip_youtube=False)
    cmd_fetch_context(ctx_args, cfg)
    print("\n=== fetch-odds ===")
    _fill_card_odds(card_path, cfg, overwrite=True)
    print("\n=== predict ===")
    cmd_predict(args, cfg)


def cmd_fetch_sherdog(args: argparse.Namespace, cfg: dict) -> None:
    """Fetch regional fight records from Sherdog for a card's fighters."""
    from octagon.scraping import sherdog

    cards = ([Path(args.card)] if args.card
             else sorted(resolve_path("cards").glob("*.yaml")))
    missing = [p for p in cards if not p.exists()]
    if missing:
        raise SystemExit(f"Card file not found: {missing[0]}")

    names = [n for path in cards for n in card_fighter_names(path)]
    cache_path = resolve_path(cfg["data"]["sherdog_cache"])
    delay = args.delay if args.delay is not None else cfg["scraping"]["sherdog_delay_seconds"]

    known_urls = {}
    if args.event_url:
        known_urls = sherdog.event_fighter_urls(args.event_url)
        if not known_urls:
            raise SystemExit(f"No fighter links found at {args.event_url} — "
                             "check the URL (a Sherdog /events/ page).")
        print(f"Resolved {len(known_urls)} fighters from the event page.")

    known = sherdog.load_cache(cache_path)
    todo = {sherdog.normalize_name(n) for n in names} - (set() if args.force
                                                         else set(known))
    print(f"{len(set(names))} fighters on {len(cards)} card(s); "
          f"{len(todo)} to fetch from Sherdog at {delay:g}s apart "
          f"(~{len(todo) * delay / 60:.1f} min).")

    def report(record: dict) -> None:
        n_fights = len(record.get("regional_fights", []))
        url = record.get("sherdog_url") or "no page"
        print(f"  {record['name']:28} {n_fights:3} regional fights ({url})")

    media = sherdog.refresh(names, cache_path, delay=delay,
                           force=args.force, on_progress=report,
                           known_urls=known_urls)
    with_fights = sum(1 for r in media.values() if r.get("regional_fights"))
    print(f"\n{with_fights}/{len(media)} fighters have Sherdog fight history. "
          f"Cache: {cache_path}")


def cmd_load_regional(args: argparse.Namespace, cfg: dict) -> None:
    """Load regional fights and titles into the DB (from Sherdog + Wikipedia)."""
    from octagon.db.regional import load_regional_records
    from octagon.db.schema import connect

    db_path = resolve_path(cfg["data"]["db_path"])
    sherdog_cache = resolve_path(cfg["data"]["sherdog_cache"])
    media_cache = resolve_path(cfg["data"]["media_path"])

    conn = connect(db_path)
    counts = load_regional_records(conn, sherdog_cache, media_cache)
    print(f"Loaded regional records into {db_path}:")
    for table, n in counts.items():
        print(f"  {table:>20}: {n}")


def cmd_predict(args: argparse.Namespace, cfg: dict) -> None:
    """Predict an upcoming card described by a YAML file."""
    import joblib

    from octagon.db.schema import connect
    from octagon.predict import card_predictions, predictions_frame, render_card

    artifact_path = resolve_path("artifacts/gbm.joblib")
    if not artifact_path.exists():
        raise SystemExit("No artifacts/gbm.joblib — run `octagon train` first.")
    card_path = Path(args.card)
    if not card_path.exists():
        raise SystemExit(f"Card file not found: {card_path} "
                         "(see cards/example_card.yaml for the format)")

    artifact = joblib.load(artifact_path)
    conn = connect(resolve_path(cfg["data"]["db_path"]))
    pred = card_predictions(conn, card_path, artifact, cfg)
    md = render_card(pred, artifact, cfg)
    reports = resolve_path("reports")
    reports.mkdir(exist_ok=True)
    out = reports / f"predict_{card_path.stem}.md"
    out.write_text(md, encoding="utf-8")
    frozen = reports / f"card_predictions_{card_path.stem}.parquet"
    predictions_frame(pred).to_parquet(frozen, index=False)
    print(md)
    print(f"\nWrote {out} and {frozen.name}")
    print("The website serves this on the next refresh — no restart needed.")
    warn_missing_media(card_path, cfg)


def warn_missing_media(card_path: Path, cfg: dict) -> None:
    """Nudge toward `fetch-media` if the site would show initials."""
    from octagon.scraping import fighters

    cache = fighters.load_cache(resolve_path(cfg["data"]["media_path"]))
    unknown = {n for n in card_fighter_names(card_path)
               if fighters.normalize_name(n) not in cache}
    if unknown:
        print(f"\n{len(unknown)} fighters have no portrait cached yet — the "
              "site will show their initials. To fetch them:")
        print(f"  uv run python -m octagon fetch-media --card {card_path}")


def cmd_score_card(args: argparse.Namespace, cfg: dict) -> None:
    """Grade a past card against the results now in the database."""
    import joblib

    from octagon.db.schema import connect
    from octagon.eval.scorecard import score_card

    artifact_path = resolve_path("artifacts/gbm.joblib")
    if not artifact_path.exists():
        raise SystemExit("No artifacts/gbm.joblib — run `octagon train` first.")
    card_path = Path(args.card)
    if not card_path.exists():
        raise SystemExit(f"Card file not found: {card_path}")

    conn = connect(resolve_path(cfg["data"]["db_path"]))
    md = score_card(conn, card_path, joblib.load(artifact_path), cfg)
    out = resolve_path("reports") / f"scorecard_{card_path.stem}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nWrote {out}")
    print("If the fights are missing, run `octagon refresh-data` first — "
          "the source CSVs lag a live event by a day or two.")


def cmd_serve(args: argparse.Namespace, cfg: dict) -> None:
    """Serve the findings over HTTP for the Next.js frontend."""
    import uvicorn

    print(f"API on http://{args.host}:{args.port}")
    print(f"Interactive docs:      http://{args.host}:{args.port}/docs")
    uvicorn.run("octagon.api.app:app", host=args.host, port=args.port,
                reload=args.reload)


def cmd_live(args: argparse.Namespace, cfg: dict) -> None:
    """Poll ESPN Fightcenter and publish the live card over a local WebSocket."""
    import json

    from octagon.live.gateway import run, snapshot_once

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


def cmd_backtest(args: argparse.Namespace, cfg: dict) -> None:
    """Paper-trading simulation over the priced validation era."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    from octagon.betting.backtest import DISCLAIMER, equity_curve, run_backtest, summarize

    preds_path = resolve_path("reports/predictions_valid.parquet")
    if not preds_path.exists():
        raise SystemExit("No predictions found — run `octagon evaluate` first.")
    preds = pd.read_parquet(preds_path)
    if "p_blend" not in preds.columns:
        raise SystemExit("Predictions lack the blend — run `octagon train`, then `octagon evaluate`.")

    kelly_fraction = cfg["betting"]["kelly_fraction"]
    lines = [
        "# Paper-trading backtest — validation era (2022-2023)",
        "",
        f"**{DISCLAIMER}**",
        "",
        "Model: LR+GBM blend, walk-forward (each fight predicted by a model "
        "trained only on earlier fights). Odds: betmma best-available closing "
        "lines — a REAL bettor at one book gets worse prices than this. "
        "True CLV is not computable without opening odds; 'edge vs close' "
        "is the model's disagreement with the closing line, not captured value.",
        "",
        "| staking | edge >= | bets | staked | P&L (u) | ROI | 95% CI | hit rate | max DD (u) | avg odds |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    curves = {}
    for staking in ["flat", "kelly"]:
        for threshold in [0.02, 0.05, 0.08]:
            bets = run_backtest(preds, "p_blend", staking, threshold,
                                kelly_fraction=kelly_fraction)
            s = summarize(bets, seed=cfg["seed"])
            if s["n_bets"] == 0:
                lines.append(f"| {staking} | {threshold:.2f} | 0 | - | - | - | - | - | - | - |")
                continue
            lo, hi = s["roi_ci95"]
            lines.append(
                f"| {staking} | {threshold:.2f} | {s['n_bets']} | {s['total_staked']:.0f} "
                f"| {s['total_pnl_units']:+.1f} | {s['roi']:+.1%} | [{lo:+.1%}, {hi:+.1%}] "
                f"| {s['hit_rate']:.1%} | {s['max_drawdown_units']:.1f} | {s['avg_odds']:.2f} |")
            if staking == "flat":
                curves[f"flat, edge>={threshold:.2f}"] = equity_curve(bets)

    fig, ax = plt.subplots(figsize=(10, 5))
    for name, (dates, equity) in curves.items():
        ax.plot(pd.to_datetime(dates), equity, label=name)
    ax.axhline(0, color="k", linewidth=1)
    ax.set_ylabel("cumulative P&L (units, flat 1u stakes)")
    ax.set_title("Paper-trading equity curves — SIMULATION, not advice")
    ax.legend()
    fig.tight_layout()
    reports_dir = resolve_path("reports")
    fig.savefig(reports_dir / "backtest_equity.png", dpi=120)

    lines += [
        "",
        "![equity curves](backtest_equity.png)",
        "",
        "## How to read this",
        "- A 95% CI containing 0 means the result is indistinguishable from luck.",
        "- The M5 error analysis showed the market wins ~61% of disagreements "
        "with this model, so losses here are the expected outcome, not a bug.",
        "- Higher edge thresholds bet less often on bigger disagreements — "
        "which are exactly the fights where the model is most likely wrong.",
    ]
    out = reports_dir / "backtest_valid.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:20]))
    print(f"\nWrote {out} and reports/backtest_equity.png")


def cmd_explain(args: argparse.Namespace, cfg: dict) -> None:
    """SHAP explanations from the trained GBM artifact."""
    import joblib
    import pandas as pd

    from octagon.eval import explain
    from octagon.models import calibration, gbm

    artifact_path = resolve_path("artifacts/gbm.joblib")
    if not artifact_path.exists():
        raise SystemExit("No artifacts/gbm.joblib — run `octagon train` first.")
    artifact = joblib.load(artifact_path)
    df = pd.read_parquet(resolve_path(cfg["data"]["processed_dir"]) / "features.parquet")
    reports_dir = resolve_path("reports")
    reports_dir.mkdir(exist_ok=True)

    if args.fight_id is None:
        valid = df[(df["date"] > cfg["splits"]["train_end"])
                   & (df["date"] <= cfg["splits"]["valid_end"])]
        shap_model = artifact.get("shap_model", artifact["model"])
        raw_flag = artifact.get("include_raw", False)
        importance = explain.global_importance(shap_model, valid, raw_flag)
        out = reports_dir / "shap_summary.png"
        explain.summary_plot(shap_model, valid, out, raw_flag)
        print(f"Global SHAP importance on {len(valid)} validation fights "
              f"(mean |log-odds contribution|):\n")
        for name, value in importance.head(15).items():
            print(f"  {value:.4f}  {name}")
        print(f"\nWrote {out}")
        return

    contributions = explain.explain_fight(
        artifact.get("shap_model", artifact["model"]), df, args.fight_id,
        artifact.get("include_raw", False))
    row = df[df["fight_id"] == args.fight_id]
    p_raw = gbm.predict_sym(artifact["model"], row,
                            include_raw=artifact.get("include_raw", False))
    p_cal = calibration.apply(artifact["iso"], p_raw)[0]
    print(explain.render_fight_text(df, args.fight_id, contributions, p_cal))
    out = reports_dir / f"shap_fight_{args.fight_id}.png"
    explain.waterfall_plot(contributions, out)
    print(f"\nWrote {out}")


def cmd_audit(args: argparse.Namespace, cfg: dict) -> None:
    import pandas as pd

    from octagon.db.schema import connect
    from octagon.eval.audit import run_audit

    conn = connect(resolve_path(cfg["data"]["db_path"]))
    df = pd.read_parquet(resolve_path(cfg["data"]["processed_dir"]) / "features.parquet")
    checks = run_audit(conn, df,
                       train_end=cfg["splits"]["train_end"],
                       valid_end=cfg["splits"]["valid_end"])
    failed = 0
    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}\n         {detail}")
        failed += not passed
    if failed:
        raise SystemExit(f"\n{failed} audit check(s) FAILED — do not trust any model "
                         "trained on this feature table until this is resolved.")
    print(f"\nAll {len(checks)} leakage audit checks passed.")


def cmd_scrape_events(args: argparse.Namespace, cfg: dict) -> None:
    """Fetch the events index and N most recent event pages into the HTML cache."""
    from octagon.scraping.fetch import BotChallengeError, fetch
    from octagon.scraping.ufcstats import COMPLETED_EVENTS_URL, parse_event_page, parse_events_index

    cache_dir = resolve_path(cfg["data"]["html_cache_dir"])
    rate = cfg["scraping"]["rate_limit_seconds"]

    try:
        html = fetch(COMPLETED_EVENTS_URL, cache_dir, rate, force=args.refresh)
    except BotChallengeError as exc:
        raise SystemExit(
            f"{exc}\nufcstats.com is behind an anti-bot wall; we don't bypass those.\n"
            "Data refresh path: the Greco1899/scrape_ufc_stats CSVs (see README)."
        )
    events = parse_events_index(html)
    if not events:
        raise SystemExit("Fetched the events index but parsed 0 events — "
                         "the page markup may have changed; inspect the cached HTML.")
    print(f"Events index: {len(events)} completed events "
          f"({events[-1]['date']} -> {events[0]['date']})")

    for event in events[: args.limit]:
        page = fetch(event["url"], cache_dir, rate)
        fights = parse_event_page(page)
        print(f"  {event['date']}  {event['name']}: {len(fights)} fights parsed")


def main() -> None:
    parser = argparse.ArgumentParser(prog="octagon", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create the SQLite schema").set_defaults(func=cmd_init_db)

    p = sub.add_parser("build-db", help="rebuild data/ufc.db from the raw CSV sources")
    p.set_defaults(func=cmd_build_db)

    p = sub.add_parser("refresh-data",
                       help="re-download Greco CSVs, rebuild DB + features, re-audit")
    p.set_defaults(func=cmd_refresh_data)

    p = sub.add_parser("scrape-events", help="fetch ufcstats events into the HTML cache")
    p.add_argument("--limit", type=int, default=3, help="event pages to fetch (default 3)")
    p.add_argument("--refresh", action="store_true", help="re-download the events index")
    p.set_defaults(func=cmd_scrape_events)

    p = sub.add_parser("build-features",
                       help="build the point-in-time feature table (parquet)")
    p.set_defaults(func=cmd_build_features)

    p = sub.add_parser("audit", help="run the data leakage audit")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("evaluate", help="baselines + models metrics report")
    p.add_argument("--split", choices=["valid", "test"], default="valid",
                   help="which era to score (default: valid; test is the final holdout)")
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("train", help="tune + calibrate the GBM, save artifact")
    p.add_argument("--trials", type=int, default=40, help="Optuna trials (default 40)")
    p.add_argument("--through", default=None,
                   help="walk-forward through this ISO date (default: splits.train_end). "
                        "Use the latest fight date for a production fit on all data.")
    p.add_argument("--reuse-params", action="store_true",
                   help="skip the Optuna searches and keep the hyperparameters from "
                        "the existing artifact; refit calibration, blend, stack and "
                        "final models on the current feature table (minutes, not hours)")
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("explain", help="SHAP: global summary, or one fight")
    p.add_argument("--fight-id", type=int, default=None,
                   help="explain a single fight (default: global summary)")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("backtest", help="paper-trading simulation (educational)")
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("fetch-card",
                       help="build a card YAML for the next UFC event (Wikipedia)")
    p.add_argument("--event", help="Wikipedia page title (default: next event)")
    p.add_argument("--date", help="ISO date, required with --event")
    p.add_argument("--out", help="output YAML path (default: cards/<event>.yaml)")
    p.set_defaults(func=cmd_fetch_card)

    p = sub.add_parser(
        "fetch-odds",
        help="write upcoming moneylines from The Odds API onto a card YAML")
    p.add_argument("--card", required=True, help="path to a card YAML")
    p.add_argument("--keep-existing", action="store_true",
                   help="do not overwrite fights that already have odds")
    p.set_defaults(func=cmd_fetch_odds)

    p = sub.add_parser("fetch-media",
                       help="fighter portraits, records and flags for a card")
    p.add_argument("--card", help="card YAML (default: every card in cards/)")
    p.add_argument("--delay", type=float, default=None,
                   help="seconds between ufc.com requests "
                        "(default: scraping.ufc_delay_seconds)")
    p.add_argument("--force", action="store_true",
                   help="re-fetch fighters already in the cache")
    p.set_defaults(func=cmd_fetch_media)

    p = sub.add_parser(
        "fetch-context",
        help="day-before context: circumstances, debut records, styles, "
             "news + YouTube buzz")
    p.add_argument("--card", required=True, help="path to a card YAML")
    p.add_argument("--event", help="Wikipedia page title (default: event name)")
    p.add_argument("--delay", type=float, default=1.0,
                   help="seconds between Wikipedia fighter lookups")
    p.add_argument("--skip-youtube", action="store_true",
                   help="skip YouTube Data API even if YOUTUBE_API_KEY is set")
    p.set_defaults(func=cmd_fetch_context)

    p = sub.add_parser(
        "day-before",
        help="refresh + media + context + predict (run the day before a card)")
    p.add_argument("--card", required=True, help="path to a card YAML")
    p.add_argument("--event", help="Wikipedia page title for context scrape")
    p.add_argument("--delay", type=float, default=None,
                   help="media crawl delay (also used lightly for context)")
    p.add_argument("--force", action="store_true", help="re-fetch media cache")
    p.add_argument("--skip-refresh", action="store_true",
                   help="skip Greco CSV refresh (faster local loop)")
    p.set_defaults(func=cmd_day_before)

    p = sub.add_parser("fetch-sherdog",
                       help="fetch regional fight records from Sherdog")
    p.add_argument("--card", help="card YAML (default: every card in cards/)")
    p.add_argument("--delay", type=float, default=None,
                   help="seconds between Sherdog requests "
                        "(default: scraping.sherdog_delay_seconds)")
    p.add_argument("--force", action="store_true",
                   help="re-fetch fighters already in the cache")
    p.add_argument("--event-url",
                   help="Sherdog /events/ page for the card — resolves fighters "
                        "by link instead of by name, which is the only safe way "
                        "to tell two fighters called Daniel Rodriguez apart")
    p.set_defaults(func=cmd_fetch_sherdog)

    p = sub.add_parser("load-regional",
                       help="load regional fights into the DB (run after fetch-sherdog)")
    p.set_defaults(func=cmd_load_regional)

    p = sub.add_parser("predict", help="predict an upcoming card from a YAML file")
    p.add_argument("--card", required=True,
                   help="path to a card YAML (see cards/example_card.yaml)")
    p.set_defaults(func=cmd_predict)

    p = sub.add_parser("score-card", help="grade a past card against the results")
    p.add_argument("--card", required=True, help="path to the card YAML that was predicted")
    p.set_defaults(func=cmd_score_card)

    p = sub.add_parser("serve", help="run the read-only findings API (for frontend/)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true", help="restart on code changes")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser(
        "live",
        help="local WebSocket of the live UFC card (ESPN Fightcenter, no paid API)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--interval", type=float, default=1.0,
                   help="seconds between polls (1s is near-live)")
    p.add_argument("--mode", choices=("http", "browser", "auto"), default="http",
                   help="http polls ESPN JSON; browser intercepts the same XHR")
    p.add_argument("--event-id", default=None, help="ESPN event id (auto-detect)")
    p.add_argument("--headed", action="store_true",
                   help="show Chromium when --mode browser")
    p.add_argument("--once", action="store_true",
                   help="print one JSON snapshot and exit")
    p.set_defaults(func=cmd_live)

    args = parser.parse_args()
    args.func(args, load_config())


if __name__ == "__main__":
    main()
