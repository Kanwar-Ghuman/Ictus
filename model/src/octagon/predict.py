"""Upcoming-card predictions.

Cards come from `octagon fetch-card` (Wikipedia) plus optional
`octagon fetch-odds`. Models are refit at predict time on all history before
the card date. The artifact supplies tuned hyperparameters, the calibration
map, and the blend weight — not a 2021-stopped final model.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from octagon.betting.odds import implied_probability, remove_vig
from octagon.features.build import (Bout, build_feature_rows, elo_kwargs, load_bouts,
                                    load_tott)
from octagon.features.research import research_brief
from octagon.models.market import (
    apply_market_layer, apply_ranking_nudge, resolve_research_weight,
)


@dataclass
class CardFight:
    fighter1: str
    fighter2: str
    weight_class: str | None = None
    title_fight: bool = False
    rounds: int = 3
    odds: tuple[float, float] | None = None
    section: str | None = None  # 'Main card' / 'Preliminary card'; display only
    ranking: tuple[int, int] | None = None  # dual-debut skill nudge
    region: tuple[str, str] | None = None


def _optional_pair(value) -> tuple | None:
    if not value:
        return None
    first, second = value[0], value[1]
    return (first, second)


def load_card(path: Path) -> tuple[str, str, list[CardFight]]:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    fights = [CardFight(
        fighter1=f["fighter1"], fighter2=f["fighter2"],
        weight_class=f.get("weight_class"), title_fight=bool(f.get("title_fight")),
        rounds=int(f.get("rounds", 3)),
        odds=tuple(f["odds"]) if f.get("odds") else None,
        section=f.get("section"),
        ranking=_optional_pair(f.get("ranking")),
        region=_optional_pair(f.get("region")),
    ) for f in raw["fights"]]
    return str(raw["date"]), raw.get("event", "Upcoming card"), fights


def pick_call(prob: float, f1: str, f2: str, low: float, high: float,
              call_all: bool = False) -> str:
    """Decisive pick, or no-call when the shipped number sits in the dead zone."""
    pick = f1 if prob >= 0.5 else f2
    conf = max(prob, 1.0 - prob)
    if low <= prob <= high:
        if call_all:
            return f"pick: {pick} ({conf:.0%}; close fight)"
        return f"no call ({conf:.0%} lean {pick})"
    return f"pick: {pick} ({conf:.0%})"


def _ending_lines(joint_row, ending_row, f1: str, f2: str,
                  scheduled: int, pick_corner: str) -> tuple[list[str], list[str]]:
    """One fight's outcome distribution, as (headline bullets, grid).

    The headlines answer what a reader asks first — does this go the
    distance, and what is the single likeliest ending? The grid is the
    whole joint distribution behind those two sentences.
    """
    from octagon.models import finish_round

    rounds = [r for r in finish_round.ROUNDS if r <= scheduled]
    decision = float(joint_row["f1_dec"] + joint_row["f2_dec"])
    by_round = " / ".join(f"R{r} {ending_row[f'r{r}']:.0%}" for r in rounds)
    selected = finish_round.select_outcome(joint_row, pick_corner)
    selected_name = f1 if pick_corner == "f1" else f2
    if selected["round"] is None:
        pick_line = (
            f"- pick outcome: {selected_name} by decision "
            f"({selected['method_probability']:.0%})"
        )
    else:
        method_label = ("KO/TKO" if selected["method"] == "KO/TKO"
                        else "submission")
        pick_line = (
            f"- pick outcome: {selected_name} by {method_label}, "
            f"round {selected['round']} (method {selected['method_probability']:.0%}; "
            f"round given method {selected['round_probability']:.0%}; "
            f"exact outcome {selected['exact_probability']:.0%})"
        )
    likeliest = ", ".join(
        f"{finish_round.describe(name, f1, f2)} ({value:.0%})"
        for name, value in joint_row.sort_values(ascending=False).head(3).items())
    headlines = [
        pick_line,
        f"- how it ends: finish {1 - decision:.0%} ({by_round}) "
        f"vs. decision {decision:.0%}",
        f"- likeliest endings: {likeliest}",
    ]

    grid = ["| ending | " + " | ".join(f"R{r}" for r in rounds) + " | any round |",
            "|---" * (len(rounds) + 2) + "|"]
    for corner, name in (("f1", f1), ("f2", f2)):
        for group, label in (("ko", "KO/TKO"), ("sub", "submission")):
            cells = [float(joint_row[f"{corner}_{group}_r{r}"]) for r in rounds]
            grid.append(f"| {name} by {label} | "
                        + " | ".join(f"{v:.1%}" for v in cells)
                        + f" | **{sum(cells):.1%}** |")
    grid.append("| decision (either fighter) | " + " | ".join("—" for _ in rounds)
                + f" | **{decision:.1%}** |")
    return headlines, grid


@dataclass
class CardPrediction:
    """Everything the models say about one card, before any rendering.

    Kept separate from the markdown so the same numbers can be graded
    against results later (`octagon score-card`) without re-deriving them
    from a report — and so grading can never quietly use a different model
    than the prediction did.
    """

    date: str
    event: str
    upcoming: "object"        # DataFrame: one feature row per announced bout
    history: "object"         # DataFrame: every fight before the card
    win_prob: "object"        # ndarray: P(fighter1 wins), row-aligned — the
                              # market-aware stack where odds were provided,
                              # the skill blend elsewhere
    skill_prob: "object"      # ndarray: the skill-only blend, always
    market_prob: "object"     # ndarray: vig-free market P(f1), NaN if no odds
    methods: "object"         # DataFrame: 6 method classes
    joint: "object"           # DataFrame: fighter x method x round, sums to 1
    endings: "object"         # DataFrame: P(ends in round r) + P(decision)
    drivers: "object"         # DataFrame: SHAP log-odds contributions per bout
    card_order: dict          # fight_id -> position on the announced card
    sections: dict            # fight_id -> broadcast segment, when known
    renames: list[str]
    shap_model: "object"
    include_raw: bool
    context_notes: dict = field(default_factory=dict)  # bout idx -> notes
    context: object | None = None  # day-before scrape payload, if present
    prediction_mode: str = "market_aware"
    call_all: bool = False
    component_prob: object | None = None  # DataFrame: independent LR and GBM votes
    recent_fights: dict = field(default_factory=dict)


def card_predictions(conn, card_path: Path, artifact: dict, cfg: dict) -> CardPrediction:
    """Fit every model on history strictly before the card and predict it.

    Fights on or after the card date are excluded by construction, so this
    stays point-in-time even once the results are in the database.
    """
    import numpy as np
    import pandas as pd

    from octagon.db.parsing import normalize_name
    from octagon.models import calibration, ensemble, finish_round, gbm, logistic, method

    date, event, card = load_card(card_path)
    policy = cfg.get("prediction") or {}
    mode = policy.get("mode", "market_aware")
    if mode not in {"skill_only", "market_aware"}:
        raise ValueError(f"Unknown prediction mode: {mode}")
    bouts = [b for b in load_bouts(conn) if b.date < date]
    recent_fights = {}
    for b in bouts:
        for name, opponent, won in ((b.fighter1, b.fighter2, "fighter1"),
                                    (b.fighter2, b.fighter1, "fighter2")):
            recent_fights.setdefault(name, []).append({
                "date": b.date, "opponent": opponent,
                "result": ("win" if b.winner == won else "loss"
                           if b.winner in {"fighter1", "fighter2"} else b.winner),
                "method": b.method, "round": b.end_round,
            })

    known: dict[str, str] = {}
    for b in bouts:
        known.setdefault(normalize_name(b.fighter1), b.fighter1)
        known.setdefault(normalize_name(b.fighter2), b.fighter2)
    renames = []
    for f in card:
        for attr in ("fighter1", "fighter2"):
            name = getattr(f, attr)
            match = known.get(normalize_name(name))
            if match and match != name:
                renames.append(f"{name} -> {match}")
                setattr(f, attr, match)

    for i, f in enumerate(card):
        bouts.append(Bout(
            fight_id=-(i + 1), date=date, fighter1=f.fighter1, fighter2=f.fighter2,
            winner="upcoming", method=None, end_round=None, duration_s=None,
            weight_class=f.weight_class, title_fight=int(f.title_fight),
            scheduled_rounds=f.rounds, stats1=None, stats2=None,
            odds1=f.odds[0] if f.odds else None, odds2=f.odds[1] if f.odds else None,
        ))

    from octagon.features.regional import load_regional

    regional_by_name = load_regional(conn)
    for fight in card:
        for name in (fight.fighter1, fight.fighter2):
            records = recent_fights.setdefault(name, [])
            seen = {(f["date"], normalize_name(f["opponent"])) for f in records}
            for f in regional_by_name.get(normalize_name(name), []):
                key = (f["date"], normalize_name(f.get("opponent") or ""))
                if f["date"] < date and not f.get("is_amateur") and key not in seen:
                    records.append({"date": f["date"], "opponent": f.get("opponent"),
                                    "result": f["result"], "method": f.get("method"),
                                    "round": None})
                    seen.add(key)
            records.sort(key=lambda f: f["date"])

    df = pd.DataFrame(build_feature_rows(
        bouts, load_tott(conn), regional_by_name=regional_by_name,
        seed=cfg["seed"], **elo_kwargs(cfg)))
    history = df[df["label"].notna()]
    upcoming = df[df["label"].isna()]

    raw_flag = artifact.get("include_raw", False)
    from octagon.lineage import verify_artifact_snapshot

    verify_artifact_snapshot(history, artifact)
    n_seeds = artifact.get("n_seeds", 1)
    gbm_model = gbm.fit(history, artifact["params"], seed=artifact["seed"],
                        include_raw=raw_flag, n_seeds=n_seeds)
    shap_model = gbm_model.members[0] if hasattr(gbm_model, "members") else gbm_model
    lr_model = logistic.fit(history, C=artifact.get("lr_C", 1.0),
                            half_life_years=artifact.get("lr_half_life"), as_of=date)
    p_gbm = calibration.apply(artifact["iso"],
                              gbm.predict_sym(gbm_model, upcoming, include_raw=raw_flag))
    p_lr = logistic.predict(lr_model, upcoming)
    p_skill = ensemble.blend(p_lr, p_gbm, artifact["weight_lr"])

    if artifact.get("debut_stack") is not None and artifact.get("debut_params"):
        from octagon.models import debut
        from octagon.models import debut_stack as debut_stack_model

        low_hist = debut.low_history_mask(upcoming).to_numpy()
        if low_hist.any():
            current_debut_model = debut.fit(
                history, artifact["debut_params"], seed=artifact["seed"],
                include_raw=raw_flag, n_seeds=n_seeds)
            p_debut = debut.predict_sym(current_debut_model, upcoming,
                                        include_raw=raw_flag)
            d_a, d_b = artifact["debut_stack"]
            p_stacked = debut_stack_model.predict_stack(d_a, d_b, p_skill, p_debut)
            p_skill = np.where(low_hist, p_stacked, p_skill)

    context_notes: dict[int, list[str]] = {}
    for i, fight in enumerate(card):
        if mode == "skill_only" or not fight.ranking:
            continue
        row = upcoming.iloc[i]
        adjusted, note = apply_ranking_nudge(
            float(p_skill[i]), fight.ranking[0], fight.ranking[1],
            float(row["f1_n_fights"] or 0), float(row["f2_n_fights"] or 0))
        p_skill[i] = adjusted
        if note:
            context_notes.setdefault(i, []).append(note)

    fair = np.full(len(upcoming), np.nan)
    for i, (_, row) in enumerate(upcoming.iterrows()):
        if row["f1_odds"] is not None and not pd.isna(row["f1_odds"]):
            fair[i], _ = remove_vig(implied_probability(row["f1_odds"]),
                                    implied_probability(row["f2_odds"]))
    if mode == "skill_only":
        p = p_skill.copy()
    else:
        p, trapped = apply_market_layer(
            p_skill, fair,
            upcoming["f1_n_fights"].to_numpy(), upcoming["f2_n_fights"].to_numpy(),
            stack=artifact.get("market_stack"),
            research_weight=resolve_research_weight(artifact, cfg),
            career1=upcoming["f1_career_n_fights"].to_numpy(),
            career2=upcoming["f2_career_n_fights"].to_numpy())
        for i in np.flatnonzero(trapped):
            context_notes.setdefault(int(i), []).append(
                f"market-trap guard: skill={float(p_skill[i]):.2f} but market="
                f"{float(fair[i]):.2f} on a debut bout — abstaining")

    context_payload = None
    try:
        from octagon.scraping import context as card_context

        context_payload = card_context.load_context(card_path)
        if context_payload and mode != "skill_only":
            for i, (_, row) in enumerate(upcoming.iterrows()):
                adjusted, notes = card_context.adjust_bout(
                    context_payload, row["f1_name"], row["f2_name"], float(p[i]),
                    f1_n_fights=float(row["f1_n_fights"] or 0),
                    f2_n_fights=float(row["f2_n_fights"] or 0),
                    has_market_odds=bool(np.isfinite(fair[i])),
                    skill_p=float(p_skill[i]))
                if notes:
                    p[i] = adjusted
                    context_notes.setdefault(i, []).extend(notes)
    except Exception:  # noqa: BLE001 — context is optional at predict time
        context_payload = None

    method_model = method.fit(history, seed=artifact["seed"],
                              include_raw=raw_flag)
    methods = method.condition_on_win_prob(
        method.blend(
            method.base_rate_methods(history, upcoming),
            method.predict_sym(method_model, upcoming, include_raw=raw_flag),
            artifact.get("weight_method_base", 0.0)),
        p)
    round_model = finish_round.fit(history, seed=artifact["seed"])
    rounds = finish_round.blend(
        finish_round.base_rate_rounds(history, upcoming),
        finish_round.predict_rounds(round_model, upcoming),
        artifact.get("weight_round_base", 0.5))
    joint = finish_round.joint_outcomes(methods, rounds)
    endings = finish_round.ending_summary(joint)

    from octagon.eval import explain

    drivers, _ = explain.shap_symmetrized(shap_model, upcoming, include_raw=raw_flag)

    return CardPrediction(
        date=date, event=event, upcoming=upcoming, history=history, win_prob=p,
        skill_prob=p_skill, market_prob=fair,
        methods=methods, joint=joint, endings=endings, drivers=drivers,
        card_order={-(i + 1): i for i in range(len(card))},
        sections={-(i + 1): f.section for i, f in enumerate(card)},
        renames=renames, shap_model=shap_model, include_raw=raw_flag,
        context_notes=context_notes, context=context_payload,
        prediction_mode=mode, call_all=bool(policy.get("call_all", False)),
        component_prob=pd.DataFrame({"p_lr": p_lr, "p_gbm": p_gbm}, index=upcoming.index),
        recent_fights={name: fights[-3:] for name, fights in recent_fights.items()})


def top_drivers(contributions, top: int = 6) -> list[dict]:
    """The features that moved one bout most, largest absolute pull first."""
    ranked = contributions.sort_values(key=abs, ascending=False).head(top)
    return [{"feature": name, "value": round(float(value), 4)}
            for name, value in ranked.items() if abs(value) > 1e-3]


def predictions_frame(pred: CardPrediction):
    """One row per bout: identities, win probability, full outcome grid.

    Saved next to the report so `octagon score-card` grades the numbers that
    were actually published. Re-deriving them later is not the same thing —
    the source CSVs get revised and a refit moves individual fights by a
    couple of points, which is exactly the kind of drift that lets a
    post-hoc grade flatter itself.

    The card position, broadcast segment and SHAP drivers ride along so the
    website can show a card the way it was announced, and explain a pick,
    without re-running anything.
    """
    import json

    import pandas as pd

    frame = pred.upcoming[["f1_name", "f2_name", "weight_class",
                           "scheduled_rounds"]].copy()
    frame.insert(0, "date", pred.date)
    frame.insert(1, "event", pred.event)
    fight_ids = pred.upcoming["fight_id"]
    frame["bout_order"] = [pred.card_order.get(i, n)
                           for n, i in enumerate(fight_ids)]
    frame["section"] = [pred.sections.get(i) for i in fight_ids]
    for corner in ("f1", "f2"):
        frame[f"{corner}_ufc_fights"] = (
            pred.upcoming[f"{corner}_n_fights"].fillna(0).astype(int).to_numpy())
    frame["p_f1_wins"] = pred.win_prob
    frame["p_skill"] = pred.skill_prob
    frame["p_market"] = pred.market_prob
    frame["prediction_mode"] = pred.prediction_mode
    frame["call_all"] = pred.call_all
    if pred.component_prob is not None:
        for name in ("p_lr", "p_gbm"):
            frame[name] = pred.component_prob[name].to_numpy()
    frame["drivers"] = [json.dumps(top_drivers(pred.drivers.loc[idx]))
                        for idx in pred.upcoming.index]
    notes = pred.context_notes or {}
    ctx = pred.context or {}
    fighters_ctx = ctx.get("fighters", {}) if isinstance(ctx, dict) else {}
    bout_rows = []
    for i, (_, row) in enumerate(pred.upcoming.iterrows()):
        from octagon.db.parsing import normalize_name

        k1, k2 = normalize_name(row["f1_name"]), normalize_name(row["f2_name"])
        c1, c2 = fighters_ctx.get(k1, {}), fighters_ctx.get(k2, {})
        bout_rows.append({
            "adjustments": notes.get(i, []),
            "research": research_brief(row.to_dict(), row["f1_name"], row["f2_name"]),
            "recent_fights": {name: pred.recent_fights.get(name, [])
                              for name in (row["f1_name"], row["f2_name"])},
            "evidence": {
                corner: {key: (None if pd.isna(row.get(f"{corner}_{key}"))
                               else float(row[f"{corner}_{key}"]))
                         for key in EVIDENCE_KEYS}
                for corner in ("f1", "f2")},
            "f1": {
                "styles": c1.get("styles") or [],
                "pro_record": c1.get("pro_record"),
                "circumstances": c1.get("circumstances") or {},
                "sentiment": c1.get("sentiment"),
                "summary": (c1.get("summary") or "")[:400] or None,
                "headlines": (c1.get("headlines") or [])[:4],
            },
            "f2": {
                "styles": c2.get("styles") or [],
                "pro_record": c2.get("pro_record"),
                "circumstances": c2.get("circumstances") or {},
                "sentiment": c2.get("sentiment"),
                "summary": (c2.get("summary") or "")[:400] or None,
                "headlines": (c2.get("headlines") or [])[:4],
            },
        })
    frame["context"] = [json.dumps(b, ensure_ascii=False) for b in bout_rows]
    return pd.concat([frame.reset_index(drop=True),
                      pred.joint.reset_index(drop=True)], axis=1)


EVIDENCE_KEYS = (
    "age", "reach_cm", "n_fights", "career_n_fights", "layoff_days",
    "slpm_l3", "sapm_l3", "slpm_l5", "sapm_l5", "sig_def_l5",
    "td15_l5", "td_def_l5", "ctrl_pct_l5", "kd15_l5", "sub15_l5",
    "opp_elo_l5", "form_l3", "form_l5", "times_koed",
)


def _pro_record(name: str, cfg: dict) -> str | None:
    """A debutant's career record outside the UFC, if we know it.

    Sherdog first, ufc.com second. For a true debutant ufc.com's roster page
    is exactly the wrong source — it carries the fighter's UFC record, which
    is 0-0-0 until they have fought, so the caution line ended up telling
    the reader that a 19-3 regional champion had never won a fight. The
    Sherdog cache is the pre-UFC history the model itself is scoring on.
    Read-only: no network at predict time.
    """
    from octagon.config import resolve_path
    from octagon.scraping import fighters, sherdog

    data = cfg.get("data", {})
    regional = sherdog.lookup([name], resolve_path(
        data.get("sherdog_cache", "data/sherdog_records.json")))
    fights = (regional.get(name) or {}).get("regional_fights") or []
    if fights:
        wins = sum(1 for f in fights if f.get("result") == "win")
        losses = sum(1 for f in fights if f.get("result") == "loss")
        draws = sum(1 for f in fights if f.get("result") == "draw")
        return f"{wins}-{losses}-{draws}"

    record = fighters.lookup([name], resolve_path(
        data.get("media_path", "data/fighter_media.json"))
    ).get(name, {}).get("record")
    # '0-0-0' from ufc.com means "not yet fought in the UFC", not "no career".
    return None if record in (None, "0-0-0", "0-0") else record


def render_card(pred: CardPrediction, artifact: dict, cfg: dict) -> str:
    import pandas as pd

    date, event, upcoming = pred.date, pred.event, pred.upcoming
    p, methods, joint, endings = (pred.win_prob, pred.methods, pred.joint,
                                  pred.endings)
    renames = pred.renames
    history_size = len(pred.history)

    lines = [
        f"# {event} — {date}",
        "",
        f"Point-in-time predictions from {history_size} historical fights. "
        "Educational output — NOT betting advice; the backtest shows this "
        "model does not beat the market.",
        "",
    ]
    if renames:
        lines += ["Name spellings resolved against ufcstats: " + "; ".join(renames), ""]
    lines += [f"Prediction mode: **{pred.prediction_mode}**. "
              + ("Odds, ranking nudges and social sentiment do not change these probabilities."
                 if pred.prediction_mode == "skill_only" else "Market layer enabled."),
              f"Historical results available through {pred.history['date'].max()}.", ""]
    for i, (idx, row) in enumerate(upcoming.iterrows()):
        prob = float(p[i])
        f1, f2 = row["f1_name"], row["f2_name"]
        band = cfg.get("abstain") or {}
        call = pick_call(prob, f1, f2,
                         float(band.get("low", 0.42)),
                         float(band.get("high", 0.58)), call_all=pred.call_all)
        lines += [f"## {f1} vs. {f2}"
                  + (f" — {row['weight_class']}" if row["weight_class"] else ""),
                  f"P({f1} wins) = {prob:.3f}  ->  {call}"]

        for name, n_fights in [(f1, row["f1_n_fights"]), (f2, row["f2_n_fights"])]:
            if n_fights == 0:
                pro = _pro_record(name, cfg)
                context = (f" Pro record outside the UFC: {pro}."
                           if pro else "")
                lines.append(f"- CAUTION: no UFC history for {name} "
                             f"(debut or misspelled name?) — prediction is "
                             f"weak.{context}")
        for note in (pred.context_notes or {}).get(i, []):
            lines.append(f"- context: {note}")
        from octagon.db.parsing import normalize_name

        verified = (pred.context or {}).get("fighters", {})
        for name in (f1, f2):
            fact = verified.get(normalize_name(name), {})
            if fact.get("summary"):
                sources = [h.get("url") for h in fact.get("headlines", []) if h.get("url")]
                source = f" [Source]({sources[0]})." if sources else ""
                lines.append(f"- verified context, {name}: {fact['summary']}{source}")
        for note in research_brief(row.to_dict(), f1, f2):
            lines.append(f"- research: {note}")
        for name in (f1, f2):
            recent = pred.recent_fights.get(name, [])
            if recent:
                lines.append(f"- recent fights, {name}: " + "; ".join(
                    f"{f['date']} {f['result']} vs {f['opponent']} ({f['method']})"
                    for f in reversed(recent)))
        if pred.component_prob is not None:
            votes = pred.component_prob.loc[idx]
            lines.append(f"- independent model votes for {f1}: logistic {votes['p_lr']:.1%}, "
                         f"calibrated GBM {votes['p_gbm']:.1%}. "
                         "Their spread is a sensitivity check, not a confidence interval.")
        lines += ["", f"| Pre-fight evidence | {f1} | {f2} |", "|---|---:|---:|"]
        for key, label in (("age", "Age"), ("reach_cm", "Reach (cm)"),
                           ("n_fights", "UFC fights"), ("layoff_days", "Days since UFC fight"),
                           ("slpm_l3", "Last 3: sig. strikes landed/min"),
                           ("sapm_l3", "Last 3: sig. strikes absorbed/min"),
                           ("td15_l5", "Last 5: takedowns/15 min"),
                           ("td_def_l5", "Last 5: takedown defense (fraction)"),
                           ("ctrl_pct_l5", "Last 5: control-time fraction"),
                           ("opp_elo_l5", "Last 5: opponent pre-fight Elo")):
            values = [row.get(f"{corner}_{key}") for corner in ("f1", "f2")]
            cells = ["unavailable" if pd.isna(v) else f"{float(v):.2f}" for v in values]
            lines.append(f"| {label} | {' | '.join(cells)} |")
        lines.append("")
        fair1, skill1 = float(pred.market_prob[i]), float(pred.skill_prob[i])
        if not pd.isna(fair1):
            lines.append(f"- skill-only research model P({f1}) = {skill1:.3f}; "
                         f"vig-free market = {fair1:.3f} "
                         f"(gap {skill1 - fair1:+.3f}). "
                         + ("Market shown for comparison only."
                            if pred.prediction_mode == "skill_only" else
                            "Shipped number mixes both; deeper UFC history weights skill more."))

        m = methods.loc[idx]
        lines.append(
            f"- method: {f1} by KO {m['f1_ko']:.0%} / sub {m['f1_sub']:.0%} / "
            f"dec {m['f1_dec']:.0%}; {f2} by KO {m['f2_ko']:.0%} / "
            f"sub {m['f2_sub']:.0%} / dec {m['f2_dec']:.0%}")
        headlines, table = _ending_lines(
            joint.loc[idx], endings.loc[idx], f1, f2,
            int(row["scheduled_rounds"] or 3), "f1" if prob >= 0.5 else "f2")
        lines += headlines

        drivers = ", ".join(f"{d['feature']} {d['value']:+.2f}"
                            for d in top_drivers(pred.drivers.loc[idx], top=5))
        lines += [f"- drivers (log-odds): {drivers}", ""] + table + [""]

    lines += ["---", "*Simulation/educational project. No betting advice. "
              "The market knows more than this model.*"]
    return "\n".join(lines)


def predict_card(conn, card_path: Path, artifact: dict, cfg: dict) -> str:
    """Predict a card and render it — the one-call path for simple uses."""
    return render_card(card_predictions(conn, card_path, artifact, cfg),
                       artifact, cfg)
