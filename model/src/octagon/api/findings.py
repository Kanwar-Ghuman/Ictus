"""Load evaluation dumps, artifacts, and frozen cards for the API."""

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from octagon.config import load_config, project_root, resolve_path
from octagon.eval import metrics

SPLITS = ("valid", "test")

MODELS = [
    ("p_market", "Market (vig-free)", "Closing odds, overround removed. The benchmark."),
    ("p_lr", "Logistic regression", "Antisymmetric, differential features only."),
    ("p_gbm_cal", "LightGBM (calibrated)", "Seed-ensembled, isotonic-calibrated."),
    ("p_blend", "Skill blend", "Frozen convex mix of logistic and calibrated LightGBM."),
    ("p_shipped", "Shipped prediction", "Skill blend plus the market layer when odds exist."),
]


_CACHE: dict[str, tuple[int | None, object]] = {}


def reset_cache() -> None:
    _CACHE.clear()


def _cached(key: str, path: Path, load):
    """Load `path` at most once per version of it.

    Keying on the modification time is what makes "rerun the model and
    refresh the page" work: the CLI rewrites a parquet, the timestamp
    moves, and the next request reloads it. A missing file caches as None
    so a not-yet-produced report doesn't cost a stat-and-miss every time.
    """
    stamp = path.stat().st_mtime_ns if path.exists() else None
    hit = _CACHE.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    value = load(path) if stamp is not None else None
    _CACHE[key] = (stamp, value)
    return value


def config() -> dict:
    return _cached("config", resolve_path("config.yaml"), load_config) or {}


def artifact() -> dict | None:
    """Training artifact metadata — never the fitted estimators themselves.

    Unpickling LightGBM on every worker to read a blend weight would be
    silly, and shipping estimator objects toward the web tier would be
    worse, so only the scalars and lists come back.
    """
    def load(path: Path) -> dict:
        import joblib

        raw = joblib.load(path)
        return {k: v for k, v in raw.items()
                if k not in ("model", "shap_model", "iso")}

    return _cached("artifact", resolve_path("artifacts/gbm.joblib"), load)


def split_frame(split: str) -> pd.DataFrame | None:
    return _cached(f"split:{split}",
                   resolve_path("reports") / f"predictions_{split}.parquet",
                   pd.read_parquet)


def _data_path(key: str, default: str) -> Path:
    """A path from config's data section, defaulted for older config files."""
    return resolve_path(config().get("data", {}).get(key, default))


def dataset_summary() -> dict:
    def load(path: Path) -> dict:
        df = pd.read_parquet(path, columns=["date", "label", "weight_class"])
        return {
            "available": True,
            "n_fights": int(len(df)),
            "first_fight": str(df["date"].min()),
            "last_fight": str(df["date"].max()),
            "n_weight_classes": int(df["weight_class"].nunique()),
        }

    path = _data_path("processed_dir", "data/processed") / "features.parquet"
    return _cached("dataset", path, load) or {"available": False}


def media_index() -> dict[str, dict]:
    """The fighter media cache, or an empty one if nobody has fetched it."""
    import json

    return _cached("media", _data_path("media_path", "data/fighter_media.json"),
                   lambda p: json.loads(p.read_text(encoding="utf-8"))) or {}


def last_updated() -> str | None:
    """When the model last wrote anything the site shows."""
    paths = [resolve_path("artifacts/gbm.joblib"),
             *resolve_path("reports").glob("*.parquet")]
    stamps = [p.stat().st_mtime for p in paths if p.exists()]
    if not stamps:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(max(stamps), timezone.utc).isoformat()


def overview() -> dict:
    cfg, art = config(), artifact()
    splits = cfg["splits"]
    return {
        "name": "Ictus",
        "summary": "UFC fight outcome prediction with calibrated probabilities, "
                   "point-in-time features and a walk-forward backtest.",
        "disclaimer": "Educational project. Not betting advice — the backtest "
                      "shows this model does not beat the market.",
        "dataset": dataset_summary(),
        "updated_at": last_updated(),
        "splits": {
            "train": f"through {splits['train_end']}",
            "validation": f"{splits['train_end']} to {splits['valid_end']}",
            "test": f"after {splits['valid_end']}",
        },
        "abstain_band": [cfg["abstain"]["low"], cfg["abstain"]["high"]],
        "model": None if art is None else {
            "n_seeds": art.get("n_seeds"),
            "include_raw": art.get("include_raw"),
            "weight_lr": art.get("weight_lr"),
            "weight_round_base": art.get("weight_round_base"),
            "n_features": len(art.get("feature_list", [])),
            "tuning_trials": art.get("n_trials"),
            "cv_log_loss": art.get("cv_log_loss"),
            "seed": art.get("seed"),
        },
        "trained": art is not None,
    }


def split_metrics(split: str) -> dict:
    """Headline metrics per model, plus the two baselines worth beating.

    The market is scored only on the fights it priced, so its row carries
    its own `n` and a paired row for the blend over the same subset —
    comparing a 1,312-fight model score against a 900-fight market score
    would be the easiest way to accidentally claim an edge.
    """
    df = split_frame(split)
    if df is None:
        return {"available": False, "split": split}

    y = df["label"].to_numpy(dtype=float)
    rows = []
    for column, label, note in MODELS:
        if column not in df:
            continue
        mask = df[column].notna().to_numpy()
        if not mask.any():
            continue
        rows.append({"key": column, "model": label, "note": note,
                     "priced_only": bool(column == "p_market"),
                     **metrics.summarize(y[mask], df[column].to_numpy()[mask])})

    priced = df["p_market"].notna().to_numpy() if "p_market" in df else None
    if priced is not None and priced.any():
        rows.append({"key": "p_blend_priced", "model": "Blend, priced fights only",
                     "note": "Same fights the market row is scored on.",
                     "priced_only": True,
                     **metrics.summarize(y[priced], df["p_blend"].to_numpy()[priced])})

    coin = np.full(len(y), 0.5)
    rows.append({"key": "coin_flip", "model": "Coin flip", "note": "0.5 every fight.",
                 "priced_only": False, **metrics.summarize(y, coin)})

    return {"available": True, "split": split, "n_fights": int(len(df)),
            "date_range": [str(df["date"].min()), str(df["date"].max())],
            "models": rows, "abstain": abstain_curve(split)}


def abstain_curve(split: str) -> dict | None:
    """Accuracy vs coverage as the no-call band widens."""
    df = split_frame(split)
    if df is None or "p_blend" not in df:
        return None
    y = df["label"].to_numpy(dtype=float)
    probability_column = "p_shipped" if "p_shipped" in df else "p_blend"
    p = df[probability_column].to_numpy()
    cfg = config()["abstain"]
    points = []
    for half_width in np.arange(0.0, 0.155, 0.01):
        keep = np.abs(p - 0.5) >= half_width
        if keep.sum() < 30:
            break
        points.append({"band": [round(0.5 - half_width, 3), round(0.5 + half_width, 3)],
                       "coverage": float(keep.mean()),
                       "accuracy": float(((p[keep] > 0.5) == (y[keep] == 1)).mean()),
                       "n": int(keep.sum())})
    return {"shipped_band": [cfg["low"], cfg["high"]], "points": points}


def calibration(split: str, n_bins: int = 10, min_count: int = 20) -> dict:
    """Reliability data: predicted probability against observed win rate.

    Bins thinner than `min_count` are dropped, matching the threshold in
    `metrics.reliability_diagram` so the site and the committed plot tell
    the same story. A five-fight bin lands on 0.0 or 1.0 by luck and reads
    as a dramatic miscalibration that isn't there. ECE is still computed
    over everything — it weights bins by size, so it doesn't need the guard.
    """
    df = split_frame(split)
    if df is None:
        return {"available": False, "split": split}
    y = df["label"].to_numpy(dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    series = []
    for column, label, _ in MODELS:
        if column not in df:
            continue
        p = df[column].to_numpy(dtype=float)
        valid = ~np.isnan(p)
        if not valid.any():
            # No odds in the test era, for instance. An empty series would
            # render as a perfectly calibrated market (ECE 0.000), which is
            # the most flattering possible lie about a model we don't have.
            continue
        bins = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            mask = valid & (p >= lo) & ((p < hi) if hi < 1.0 else (p <= hi))
            if mask.sum() < min_count:
                continue
            bins.append({"predicted": float(p[mask].mean()),
                         "observed": float(y[mask].mean()),
                         "n": int(mask.sum())})
        series.append({"key": column, "model": label, "bins": bins,
                       "ece": metrics.ece(y[valid], p[valid])})
    return {"available": True, "split": split, "series": series}


def _slug(path: Path) -> str:
    return path.stem.replace("card_predictions_", "")


def card_files() -> list[Path]:
    return sorted(resolve_path("reports").glob("card_predictions_*.parquet"))


def _card_meta(path: Path) -> dict:
    """Header metadata for one card parquet, cached by file mtime.

    Re-reads only when `octagon predict` rewrites the file. Avoids loading
    every card's parquet on each `/api/cards` or `/api/next-card` request.
    """
    def _read(p: Path) -> dict:
        frame = pd.read_parquet(p, columns=["date", "event"])
        return {
            "slug": _slug(p),
            "event": str(frame["event"].iat[0]),
            "date": str(frame["date"].iat[0]),
            "n_bouts": int(len(frame)),
        }

    result = _cached(f"card_meta:{path}", path, _read)
    # _cached returns None when the file disappears mid-request; skip it.
    return result  # type: ignore[return-value]


def list_cards() -> list[dict]:
    cards = [m for path in card_files() if (m := _card_meta(path)) is not None]
    return sorted(cards, key=lambda c: c["date"], reverse=True)


def next_card_slug(today: str | None = None) -> str | None:
    """The card the homepage should lead with.

    The soonest card that hasn't happened yet, or — between events, which
    is most of the time — the most recent one, whose scorecard is the
    interesting thing by then.
    """
    cards = list_cards()
    if not cards:
        return None
    today = today or date.today().isoformat()
    future = [c for c in cards if c["date"] >= today]
    return (min(future, key=lambda c: c["date"]) if future else cards[0])["slug"]


PORTRAIT_ROUTE = "/api/portraits/"

# What the website is allowed to know about a fighter. Deliberately not
# `**record`: the cache also holds source URLs and fetch bookkeeping that
# the page has no use for.
MEDIA_FIELDS = ("nickname", "record", "rank", "division", "country",
                "country_code", "profile", "wiki_page", "description")


def fighter_media(name: str) -> dict:
    """Portrait, record and flag for one fighter, as the site consumes them."""
    from octagon.db.parsing import normalize_name

    record = media_index().get(normalize_name(name), {})
    portrait = record.get("portrait") or record.get("headshot")
    return {
        "name": name,
        "portrait": PORTRAIT_ROUTE + portrait if portrait else None,
        **{field: record.get(field) for field in MEDIA_FIELDS},
    }


def _drivers(row) -> list[dict]:
    """The SHAP contributions `predict` froze with the bout, if it did."""
    import json

    raw = row.get("drivers")
    return json.loads(raw) if isinstance(raw, str) and raw else []


def _opt_float(value) -> float | None:
    """A JSON-safe float, or None when the column is absent/NaN."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    return float(value)


def _opt_int(value) -> int | None:
    """An int the JSON encoder will accept, or None when the column is absent."""
    return None if value is None or pd.isna(value) else int(value)


def _bout_context(row) -> dict:
    """Day-before context frozen beside the prediction, if present."""
    import json

    raw = row.get("context")
    if isinstance(raw, str) and raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def card_detail(slug: str) -> dict | None:
    from octagon.models import finish_round

    path = resolve_path("reports") / f"card_predictions_{slug}.parquet"
    if not path.exists():
        return None
    frame = pd.read_parquet(path)
    if "bout_order" in frame:
        frame = frame.sort_values("bout_order")
    columns = finish_round.outcome_columns()

    bouts = []
    for _, row in frame.iterrows():
        joint = {c: float(row[c]) for c in columns}
        p = float(row["p_f1_wins"])
        low, high = config()["abstain"]["low"], config()["abstain"]["high"]
        pick_corner = "f1" if p >= 0.5 else "f2"
        called = bool(row.get("call_all", False)) or not (low <= p <= high)
        selected = finish_round.select_outcome(joint, pick_corner)
        outcome_col = selected["column"]
        bouts.append({
            "f1": row["f1_name"], "f2": row["f2_name"],
            "f1_media": fighter_media(row["f1_name"]),
            "f2_media": fighter_media(row["f2_name"]),
            "weight_class": row.get("weight_class"),
            "section": row.get("section") or None,
            "scheduled_rounds": int(row["scheduled_rounds"] or 3),
            "f1_ufc_fights": _opt_int(row.get("f1_ufc_fights")),
            "f2_ufc_fights": _opt_int(row.get("f2_ufc_fights")),
            "p_f1_wins": p,
            "p_skill": _opt_float(row.get("p_skill")),
            "p_market": _opt_float(row.get("p_market")),
            "pick": row["f1_name"] if p >= 0.5 else row["f2_name"],
            "confidence": max(p, 1.0 - p),
            "called": called,
            "prediction_mode": row.get("prediction_mode", "market_aware"),
            "top_outcome": {
                "label": _outcome_phrase(outcome_col),
                "probability": selected["exact_probability"],
                "method": selected["method"],
                "round": selected["round"],
                "method_probability": selected["method_probability"],
                "round_probability": selected["round_probability"],
            },
            "statement": (
                f"{row['f1_name'] if p >= 0.5 else row['f2_name']} "
                f"{_outcome_phrase(outcome_col)}"
                if called else None),
            "context": _bout_context(row),
            "drivers": _drivers(row),
            "methods": {
                "f1_ko": _channel(joint, "f1", "ko"), "f1_sub": _channel(joint, "f1", "sub"),
                "f1_dec": joint["f1_dec"],
                "f2_ko": _channel(joint, "f2", "ko"), "f2_sub": _channel(joint, "f2", "sub"),
                "f2_dec": joint["f2_dec"],
            },
            "by_round": [
                {"round": r,
                 "f1_ko": joint[f"f1_ko_r{r}"], "f1_sub": joint[f"f1_sub_r{r}"],
                 "f2_ko": joint[f"f2_ko_r{r}"], "f2_sub": joint[f"f2_sub_r{r}"]}
                for r in finish_round.ROUNDS
                if r <= int(row["scheduled_rounds"] or 3)
            ],
            "p_decision": joint["f1_dec"] + joint["f2_dec"],
        })
    return {"slug": slug, "event": str(frame["event"].iat[0]),
            "date": str(frame["date"].iat[0]),
            "upcoming": str(frame["date"].iat[0]) >= date.today().isoformat(),
            "predicted_at": pd.Timestamp(path.stat().st_mtime, unit="s",
                                         tz="UTC").isoformat(),
            "headline": _headline(bouts),
            "bouts": bouts}


def dashboard_picks(today: str | None = None) -> dict:
    """The pick table, from the saved card. No bot and no live feed."""
    slug = next_card_slug(today)
    detail = card_detail(slug) if slug else None
    if detail is None:
        return {"event": None, "date": None, "fights": []}
    return {
        "event": detail["event"],
        "date": str(detail["date"])[:10],
        "fights": [_dashboard_fight(bout) for bout in detail["bouts"]],
    }


def write_site_picks(target: Path | None = None) -> Path:
    """Write the pick table the deployed site ships in frontend/public."""
    import json

    target = target or (project_root().parent / "frontend" / "public" / "picks.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dashboard_picks(), indent=2) + "\n", encoding="utf-8")
    return target


def _dashboard_fight(bout: dict) -> dict:
    outcome = bout.get("top_outcome") or {}
    rnd = outcome.get("round")
    return {
        "f1": bout["f1"], "f2": bout["f2"],
        "p_f1": _num(bout.get("p_f1_wins")), "line": None,
        "pick": {
            "winner": bout["pick"],
            "confidence": _num(bout.get("confidence")),
            "method": outcome.get("method"),
            "round": None if rnd is None else int(rnd),
            "exact_probability": _num(outcome.get("probability")),
        },
        "weight_class": _text(bout.get("weight_class")),
        "result": None, "bout_id": None, "status": None, "round": None,
        "ticker": None, "yes_fighter": None, "yes_bid": None, "yes_ask": None,
        "rules_primary": None, "rules_secondary": None,
        "include": False, "note": "", "winner": None,
    }


def _text(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value)


def _num(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _outcome_phrase(column: str) -> str:
    """'f1_ko_r2' -> 'by KO/TKO in round 2'; 'f2_dec' -> 'by decision'."""
    _, rest = column.split("_", 1)
    if rest == "dec":
        return "by decision"
    group, rnd = rest.split("_r")
    return f"by {'KO/TKO' if group == 'ko' else 'submission'} in round {rnd}"


def _headline(bouts: list[dict]) -> dict | None:
    """Most confident called bout; if none are called, the closest to a pick."""
    if not bouts:
        return None
    pool = [b for b in bouts if b["called"]] or bouts
    best = max(pool, key=lambda b: b["confidence"])
    opponent = best["f2"] if best["pick"] == best["f1"] else best["f1"]
    return {
        "pick": best["pick"],
        "opponent": opponent,
        "weight_class": best.get("weight_class"),
        "confidence": best["confidence"],
        "outcome": best["top_outcome"]["label"],
        "outcome_probability": best["top_outcome"]["probability"],
        "statement": f"{best['pick']} beats {opponent} "
                     f"{best['top_outcome']['label']}",
    }


def portrait_path(file_name: str) -> Path | None:
    """Resolve a portrait file name to a path inside the image directory.

    The name arrives from a URL, so it gets resolved and then checked to be
    inside the directory — a route that serves files by name is exactly
    where '../../etc/passwd' shows up.
    """
    root = _data_path("media_image_dir", "data/fighter_images").resolve()
    candidate = (root / file_name).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return None
    return candidate


def _channel(joint: dict[str, float], corner: str, group: str) -> float:
    from octagon.models import finish_round

    return sum(joint[f"{corner}_{group}_r{r}"] for r in finish_round.ROUNDS)


def card_scorecard(slug: str) -> dict | None:
    """Grade a card if its results are in the database. No model needed."""
    from octagon.db.schema import connect
    from octagon.eval import scorecard

    path = resolve_path("reports") / f"card_predictions_{slug}.parquet"
    db_path = resolve_path(config()["data"]["db_path"])
    if not path.exists() or not db_path.exists():
        return None
    cfg = config()
    graded = scorecard.grade(connect(db_path), pd.read_parquet(path),
                             (cfg["abstain"]["low"], cfg["abstain"]["high"]))
    return graded if graded["fights"] else None
