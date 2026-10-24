"""Forecasting: 7-day moving-average baseline + a global LightGBM model.

Two models, evaluated the same honest way:
  * baseline  -- predict each day as the mean of the previous 7 actual days.
  * lightgbm  -- one global model trained across ALL items with lag / rolling /
                 calendar / festival features, plus item_id as a categorical.

Backtest: hold out the last 28 days. Both models predict those days one-step-
ahead using ACTUAL lagged values (teacher forcing), so WAPE compares pure model
quality. WAPE = sum(|actual - pred|) / sum(actual). Results go to metrics.json.

The trained model + metrics are cached in-process (train_global_model) and the
live /forecast endpoint uses recursive multi-step prediction for the future,
where no actuals exist yet.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from models import Item, Sale
from seed import is_festival

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
METRICS_PATH = os.path.join(BASE_DIR, "metrics.json")

HORIZON = 7
BACKTEST_DAYS = 28
FEATURES = ["lag_1", "lag_7", "lag_14", "roll_mean_7", "roll_mean_28", "dow", "month", "is_festival", "item_id"]
CATEGORICAL = ["item_id"]

# In-process cache populated by train_global_model().
_MODEL = None
_METRICS: dict | None = None


# --------------------------------------------------------------------------- #
# Data loading / feature engineering
# --------------------------------------------------------------------------- #
def load_sales(db: Session) -> pd.DataFrame:
    """Return long-form sales: columns item_id, date, qty (sorted)."""
    rows = db.query(Sale.item_id, Sale.date, Sale.qty).all()
    df = pd.DataFrame(rows, columns=["item_id", "date", "qty"])
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["item_id", "date"]).reset_index(drop=True)


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add lag / rolling / calendar / festival features per item."""
    df = df.sort_values(["item_id", "date"]).copy()
    g = df.groupby("item_id")["qty"]
    df["lag_1"] = g.shift(1)
    df["lag_7"] = g.shift(7)
    df["lag_14"] = g.shift(14)
    # Rolling means use only past days (shift(1) first so today isn't leaked).
    df["roll_mean_7"] = g.shift(1).rolling(7).mean().reset_index(level=0, drop=True)
    df["roll_mean_28"] = g.shift(1).rolling(28).mean().reset_index(level=0, drop=True)
    df["dow"] = df["date"].dt.dayofweek
    df["month"] = df["date"].dt.month
    df["is_festival"] = df["date"].dt.date.map(is_festival).astype(int)
    return df


def _wape(actual: np.ndarray, pred: np.ndarray) -> float:
    denom = np.sum(np.abs(actual))
    if denom == 0:
        return 0.0
    return float(np.sum(np.abs(actual - pred)) / denom)


# --------------------------------------------------------------------------- #
# Training + backtest
# --------------------------------------------------------------------------- #
def train_global_model(db: Session) -> dict:
    """Train LightGBM on all-but-last-28-days, backtest both models, cache + save.

    Returns the metrics dict. Also trains a FINAL model on the full history for
    live forecasting, and caches it in _MODEL.
    """
    global _MODEL, _METRICS
    import lightgbm as lgb

    df = load_sales(db)
    if df.empty:
        raise RuntimeError("No sales data. Run seed.py first.")

    feat = add_features(df).dropna(subset=FEATURES).reset_index(drop=True)
    cutoff = df["date"].max() - pd.Timedelta(days=BACKTEST_DAYS)

    train = feat[feat["date"] <= cutoff]
    test = feat[feat["date"] > cutoff]
    if train.empty or test.empty:
        raise RuntimeError("Not enough history for a 28-day backtest.")

    lgb_params = dict(
        objective="regression",
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=20,
        subsample=0.9,
        colsample_bytree=0.9,
        verbose=-1,
    )
    bt_model = lgb.LGBMRegressor(**lgb_params)
    bt_model.fit(train[FEATURES], train["qty"], categorical_feature=CATEGORICAL)

    # LightGBM backtest (one-step-ahead using actual lags).
    lgb_pred = np.clip(bt_model.predict(test[FEATURES]), 0, None)
    wape_lgb = _wape(test["qty"].to_numpy(), lgb_pred)

    # Baseline backtest: predict each test day = mean of previous 7 actual days.
    # roll_mean_7 was built from past actuals only, so it IS that baseline.
    baseline_pred = np.clip(test["roll_mean_7"].to_numpy(), 0, None)
    wape_baseline = _wape(test["qty"].to_numpy(), baseline_pred)

    metrics = {
        "wape_baseline": round(wape_baseline, 4),
        "wape_lightgbm": round(wape_lgb, 4),
        "wape_baseline_pct": round(wape_baseline * 100, 2),
        "wape_lightgbm_pct": round(wape_lgb * 100, 2),
        "backtest_days": BACKTEST_DAYS,
        "n_train_rows": int(len(train)),
        "n_test_rows": int(len(test)),
        "note": "SYNTHETIC data. WAPE = sum(|actual-pred|)/sum(actual), lower is better.",
    }
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    # Final model on full history for live forecasting.
    final_model = lgb.LGBMRegressor(**lgb_params)
    final_model.fit(feat[FEATURES], feat["qty"], categorical_feature=CATEGORICAL)

    _MODEL = final_model
    _METRICS = metrics
    return metrics


def get_metrics(db: Session) -> dict:
    """Return cached metrics, training the model if needed."""
    if _METRICS is None:
        train_global_model(db)
    return _METRICS  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Live forecasting
# --------------------------------------------------------------------------- #
def forecast_item(db: Session, item_id: int, horizon: int = HORIZON) -> dict:
    """Forecast the next `horizon` days for one item.

    Returns both the LightGBM forecast (recursive multi-step) and the 7-day
    moving-average baseline, so the mobile app can show them side by side.
    """
    if _MODEL is None:
        train_global_model(db)
    model = _MODEL

    item = db.get(Item, item_id)
    if item is None:
        raise ValueError(f"Item {item_id} not found")

    hist = (
        db.query(Sale.date, Sale.qty)
        .filter(Sale.item_id == item_id)
        .order_by(Sale.date)
        .all()
    )
    if not hist:
        # Newly added item (e.g. via voice) with no sales yet: forecast zero
        # demand instead of crashing. Callers (alerts, detail screen) handle it.
        from datetime import date as _date, timedelta as _td

        today = _date.today()
        zeros = [
            {"date": (today + _td(days=s)).isoformat(), "qty": 0.0}
            for s in range(1, horizon + 1)
        ]
        return {
            "item_id": item_id,
            "item_name": item.name,
            "unit": item.unit,
            "horizon": horizon,
            "forecast": zeros,
            "baseline": [dict(z) for z in zeros],
            "metrics": get_metrics(db),
            "note": "No sales history yet for this item.",
        }

    # Working series of (date, qty); we append predictions as we roll forward.
    dates = [pd.Timestamp(d) for d, _ in hist]
    qtys = [float(q) for _, q in hist]

    last_date = dates[-1]
    baseline_value = float(np.mean(qtys[-7:]))  # flat 7-day MA baseline

    lgb_forecast: list[dict] = []
    baseline_forecast: list[dict] = []

    for step in range(1, horizon + 1):
        fdate = last_date + pd.Timedelta(days=step)
        series = pd.Series(qtys)
        feat_row = {
            "lag_1": qtys[-1],
            "lag_7": qtys[-7] if len(qtys) >= 7 else qtys[0],
            "lag_14": qtys[-14] if len(qtys) >= 14 else qtys[0],
            "roll_mean_7": float(series.iloc[-7:].mean()),
            "roll_mean_28": float(series.iloc[-28:].mean()),
            "dow": fdate.dayofweek,
            "month": fdate.month,
            "is_festival": int(is_festival(fdate.date())),
            "item_id": item_id,
        }
        X = pd.DataFrame([feat_row])[FEATURES]
        pred = float(np.clip(model.predict(X)[0], 0, None))

        lgb_forecast.append({"date": fdate.date().isoformat(), "qty": round(pred, 1)})
        baseline_forecast.append({"date": fdate.date().isoformat(), "qty": round(baseline_value, 1)})

        # Feed the prediction back in for the next step (recursive).
        dates.append(fdate)
        qtys.append(pred)

    return {
        "item_id": item_id,
        "item_name": item.name,
        "unit": item.unit,
        "horizon": horizon,
        "forecast": lgb_forecast,
        "baseline": baseline_forecast,
        "metrics": get_metrics(db),
    }


def forecast_next_n_total(db: Session, item_id: int, days: int) -> float:
    """Sum of the LightGBM forecast demand over the next `days` days.

    Used by the stockout alert check (Step 5).
    """
    result = forecast_item(db, item_id, horizon=days)
    return float(sum(d["qty"] for d in result["forecast"]))
