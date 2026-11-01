# Ictus - UFC Prediction Project

## Kalshi trading bot

One command starts the fight feed, the bot and the dashboard:

```bash
./ictus.sh paper              # practice, no money
./ictus.sh live 5             # real money; the bot can never spend more than $5 per event
./ictus.sh paper --in-fight   # also bet between rounds
```

Open http://localhost:3000, enter how much the bot may spend, and press Start.
It finds the event, the prediction card, each fight and its Kalshi market by
itself; if tonight has no predictions yet, the page offers to generate them.
Ctrl+C in that terminal stops everything.

The bot bets only when the model's probability beats the Kalshi price by a
safety margin, so it may spend nothing. **No model guarantees a profit**, and
nothing here shows a proven edge over Kalshi; real-money mode can lose its whole
limit. One-time setup (dashboard token, Kalshi API key), recovery, and every
safety rule: [setup and operation](model/docs/kalshi_trading.md) ·
[model evidence](model/docs/trading_model_readiness.md).

## Prediction pipeline

```text
                  +--------------------------------------+
                  | Historical fights and fighter data   |
                  +-------------------+------------------+
                                      |
                                      v
                  +--------------------------------------+
                  | SQLite database                      |
                  | Fights, fighters, stats, and records  |
                  +-------------------+------------------+
                                      |
                                      v
                  +--------------------------------------+
                  | Pre-fight feature engineering        |
                  | pandas + NumPy                       |
                  |                                      |
                  | Age, reach, striking, grappling,     |
                  | Elo, recent form, and matchup data   |
                  | Uses only earlier fight information  |
                  +-------------------+------------------+
                                      |
                                      v
                  +--------------------------------------+
                  | Feature table                        |
                  | Parquet storage via PyArrow          |
                  +-------------------+------------------+
                                      |
               +----------------------+----------------------+
               |                      |                      |
               v                      v                      v
    +---------------------+ +---------------------+ +---------------------+
    | Logistic regression | | LightGBM winner     | | Method and round    |
    | scikit-learn        | | models              | | models              |
    |                     | |                     | | LightGBM            |
    | Fill missing values | | Average predictions | |                     |
    | Scale inputs        | | across five seeds   | | KO/TKO, submission, |
    | Estimate win chance | |                     | | decision, and round |
    +----------+----------+ +----------+----------+ +----------+----------+
               |                      |                      |
               |                      v                      v
               |           +---------------------+ +---------------------+
               |           | Isotonic calibration| | Blend with          |
               |           | scikit-learn        | | historical rates    |
               |           | Adjust confidence   | |                     |
               |           +----------+----------+ +----------+----------+
               |                      |                      |
               +----------+-----------+                      |
                          |                                  |
                          v                                  |
               +----------------------+                      |
               | Weighted winner blend|                      |
               | Logistic + LightGBM  |                      |
               +----------+-----------+                      |
                          |                                  |
                          +----------------+-----------------+
                                           |
                                           v
                         +-----------------------------------+
                         | Combined outcome probabilities    |
                         | Winner + method + finishing round |
                         +-----------------+-----------------+
                                           |
                                           v
                         +-----------------------------------+
                         | Saved predictions and reports     |
                         | Freeze picks before the event     |
                         | Grade them after results arrive   |
                         +-----------------+-----------------+
                                           |
                                           v
                         +-----------------------------------+
                         | FastAPI + Uvicorn                  |
                         | Read-only API                     |
                         +-----------------+-----------------+
                                           |
                                           v
                         +-----------------------------------+
                         | Next.js + React website           |
                         | Cards, predictions, and results   |
                         +-----------------------------------+


    SUPPORTING TRAINING AND ANALYSIS

    +---------------------+       +---------------------------------------+
    | Optuna              | ----> | Tune LightGBM training settings       |
    +---------------------+       +---------------------------------------+

    +---------------------+       +---------------------------------------+
    | Walk-forward tests  | ----> | Train on past fights; predict later   |
    |                     |       | fights and measure prediction quality |
    +---------------------+       +---------------------------------------+

    +---------------------+       +---------------------------------------+
    | SHAP + Matplotlib   | ----> | Explain tree-model contributions and  |
    |                     |       | draw explanation/evaluation plots     |
    +---------------------+       +---------------------------------------+

    +---------------------+       +---------------------------------------+
    | joblib              | ----> | Save models and training settings     |
    +---------------------+       +---------------------------------------+
```

This diagram shows the main skill-only prediction flow. Optional low-history
specialist and market-aware paths are omitted. The current default excludes
odds, ranking adjustments, and social sentiment from winner probabilities.
