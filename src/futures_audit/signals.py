from __future__ import annotations

import calendar
import datetime as dt
import math

import numpy as np
import pandas as pd


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> dt.date:
    first_weekday, _ = calendar.monthrange(year, month)
    day = 1 + (weekday - first_weekday) % 7 + (occurrence - 1) * 7
    return dt.date(year, month, day)


def estimated_last_trade_date(delivery_month: str, rule: str) -> dt.date:
    year = 2000 + int(delivery_month[:2])
    month = int(delivery_month[2:])
    if rule == "third_friday":
        return _nth_weekday(year, month, calendar.FRIDAY, 3)
    if rule == "second_friday":
        return _nth_weekday(year, month, calendar.FRIDAY, 2)
    if rule == "day_15":
        return dt.date(year, month, 15)
    raise ValueError(f"Unknown last trade rule: {rule}")


def validate_market_rows(frame: pd.DataFrame) -> None:
    if frame.empty:
        raise ValueError("Market data is empty")
    numeric = ["open", "high", "low", "close", "settle", "pre_settle", "volume", "open_interest"]
    if frame[numeric].isna().any().any():
        raise ValueError("Market data contains null required fields")
    if ((frame["high"] < frame[["open", "close", "low"]].max(axis=1)) | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("OHLC coherence check failed")
    if (frame[["open", "high", "low", "close", "settle", "pre_settle"]] <= 0).any().any():
        raise ValueError("Market prices must be positive")
    if (frame[["volume", "open_interest"]] < 0).any().any():
        raise ValueError("Volume and open interest must be nonnegative")


def build_root_panel(frame: pd.DataFrame, root: str, spec: dict, roll_buffer_days: int) -> pd.DataFrame:
    market = frame[frame["root"] == root].copy()
    if market.empty:
        raise ValueError(f"No market data for {root}")
    market["last_trade_date"] = market["delivery_month"].map(
        lambda value: estimated_last_trade_date(str(value), spec["last_trade_rule"])
    )
    market["days_to_estimated_last_trade"] = [
        (last - value.date()).days for last, value in zip(market["last_trade_date"], market["date"], strict=True)
    ]
    eligible = market[
        (market["days_to_estimated_last_trade"] > roll_buffer_days)
        & (market["volume"] > 0)
        & (market["open_interest"] > 0)
    ].copy()
    if eligible.empty:
        raise ValueError(f"No eligible delivery contracts for {root}")
    selected = (
        eligible.sort_values(["date", "open_interest", "volume", "contract"], ascending=[True, False, False, True])
        .groupby("date", as_index=False)
        .first()
        .set_index("date")
        .sort_index()
    )
    lookup = market.set_index(["date", "contract"])
    signal_prices: list[float] = []
    previous_signal: float | None = None
    previous_date: pd.Timestamp | None = None
    for date, row in selected.iterrows():
        close = float(row["close"])
        if previous_signal is None:
            signal_value = close
        else:
            key = (previous_date, row["contract"])
            if key in lookup.index:
                previous_same_contract_close = float(lookup.loc[key, "close"])
                signal_value = previous_signal + close - previous_same_contract_close
            else:
                signal_value = previous_signal
        signal_prices.append(signal_value)
        previous_signal = signal_value
        previous_date = date
    selected["signal_price"] = signal_prices
    selected["signal_return"] = selected["signal_price"].pct_change()
    selected["selected_from_close_oi"] = True
    return selected


def ewmac_features(panel: pd.DataFrame, signal_config: dict) -> pd.DataFrame:
    output = panel.copy()
    price = output["signal_price"]
    returns = output["signal_return"]
    vol_span = int(signal_config["volatility_span"])
    min_vol = int(signal_config["minimum_volatility_observations"])
    output["annual_volatility"] = returns.ewm(span=vol_span, adjust=False, min_periods=min_vol).std() * math.sqrt(252)
    daily_price_risk = price * output["annual_volatility"] / math.sqrt(252)
    forecasts: list[pd.Series] = []
    for fast_span, scalar in zip(
        signal_config["ewmac_fast_spans"], signal_config["ewmac_scalars"], strict=True
    ):
        slow_span = int(fast_span) * 4
        fast = price.ewm(span=int(fast_span), adjust=False, min_periods=int(fast_span)).mean()
        slow = price.ewm(span=slow_span, adjust=False, min_periods=slow_span).mean()
        forecasts.append(((fast - slow) / daily_price_risk * float(scalar)).clip(-20, 20))
    combined = pd.concat(forecasts, axis=1).mean(axis=1, skipna=False)
    output["forecast"] = (
        combined * float(signal_config["forecast_diversification_multiplier"])
    ).clip(-float(signal_config["forecast_cap"]), float(signal_config["forecast_cap"]))
    return output


def relative_value_features(
    tf_panel: pd.DataFrame, t_panel: pd.DataFrame, signal_config: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    common = tf_panel.index.intersection(t_panel.index)
    tf = tf_panel.loc[common].copy()
    ten = t_panel.loc[common].copy()
    span = int(signal_config["relative_value_span"])
    tf_abs_vol = tf["signal_price"].diff().ewm(span=span, adjust=False, min_periods=span).std()
    t_abs_vol = ten["signal_price"].diff().ewm(span=span, adjust=False, min_periods=span).std()
    hedge_ratio = (tf_abs_vol / t_abs_vol).replace([np.inf, -np.inf], np.nan)
    spread = hedge_ratio * ten["signal_price"] - tf["signal_price"]
    spread_mean = spread.ewm(span=span, adjust=False, min_periods=span).mean()
    spread_std = spread.ewm(span=span, adjust=False, min_periods=span).std()
    zscore = (spread - spread_mean) / spread_std
    pair_forecast = (-10.0 * zscore).clip(
        -float(signal_config["forecast_cap"]), float(signal_config["forecast_cap"])
    )
    min_vol = int(signal_config["minimum_volatility_observations"])
    for panel in (tf, ten):
        panel["annual_volatility"] = panel["signal_return"].ewm(
            span=int(signal_config["volatility_span"]), adjust=False, min_periods=min_vol
        ).std() * math.sqrt(252)
    tf["forecast"] = pair_forecast
    tf["hedge_ratio"] = hedge_ratio
    tf["spread"] = spread
    tf["zscore"] = zscore
    ten["forecast"] = -pair_forecast
    ten["hedge_ratio"] = hedge_ratio
    ten["spread"] = spread
    ten["zscore"] = zscore
    return tf, ten

