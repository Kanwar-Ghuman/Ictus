# Does day-before context improve the bot's number?

The bot does not use YouTube lean, headline sentiment, short-notice flags, or
debutants' pro records. This compares its number as it stands with the same
number after those nudges, on fights that have finished. Lower log loss is better.

**Too early to say. The context has moved 7 finished fights; this needs 40 before it can tell a real effect from luck.**

| Fights | n | Log loss, bot's number | Log loss, with context | Winners called | With context |
|---|---:|---:|---:|---:|---:|
| All scored fights | 77 | 0.5981 | 0.5949 | 54 | 54 |
| Fights the context moved | 7 | 0.6586 | 0.6234 | 5 | 5 |
| Moved by: YouTube lean | 3 | 0.4972 | 0.4910 | 3 | 3 |
| Moved by: Headline sentiment | 0 | | | | |
| Moved by: Short notice or late replacement | 5 | 0.7529 | 0.7143 | 3 | 3 |
| Moved by: Debutant's pro record | 0 | | | | |

## YouTube on its own

YouTube comments clearly leaned to one fighter in 11 finished fights and
that fighter won 5 of them. It disagreed with the bot's pick in
7, and was right in 1 of those.

## Cards

| Card | Date | Context fetched | Fights scored | Status |
|---|---|---|---:|---|
| dwcs_2026_week_3 | 2026-08-25 | 2026-08-25 | 0 | no results in the database yet |
| noche_ufc_silva_vs_delgado_2026 | 2026-09-12 |  | 0 | saved context has no fetch date; left out |
| ufc_330_makhachev_vs_machado_garry | 2026-08-15 | 2026-08-15 | 12 | scored |
| ufc_fight_night_cortes_acosta_vs_walker | 2026-11-07 | 2026-11-07 | 0 | no results in the database yet |
| ufc_fight_night_gamrot_vs_salkilld | 2026-08-08 | 2026-08-07 | 12 | scored |
| ufc_fight_night_hernandez_vs_rodrigues | 2026-08-22 | 2026-08-21 | 13 | scored |
| ufc_fight_night_hooker_vs_parnasse | 2026-09-05 | 2026-09-04 | 14 | scored |
| ufc_fight_night_medic_vs_rodriguez | 2026-08-01 | 2026-07-31 | 14 | scored |
| ufc_fight_night_nurmagomedov_vs_song | 2026-08-29 | 2026-08-28 | 12 | scored |

Rebuild with `uv run python -m octagon score-context` after `refresh-data`.
