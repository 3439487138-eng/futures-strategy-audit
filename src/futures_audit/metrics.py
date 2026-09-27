from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _max_drawdown_duration(drawdown: pd.Series) -> int:
    longest = 0
    current = 0
    for value in drawdown:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def calculate_metrics(nav: pd.DataFrame, trades: pd.DataFrame, positions: pd.DataFrame) -> dict:
    returns = nav["daily_return"].astype(float)
    start_equity = float(nav["equity"].iloc[0])
    end_equity = float(nav["equity"].iloc[-1])
    calendar_days = max(1, (pd.Timestamp(nav["date"].iloc[-1]) - pd.Timestamp(nav["date"].iloc[0])).days)
    years = calendar_days / 365.2425
    total_return = end_equity / start_equity - 1.0
    annual_return = (end_equity / start_equity) ** (1.0 / years) - 1.0
    annual_volatility = float(returns.std(ddof=1) * math.sqrt(252))
    sharpe = float(returns.mean() * 252 / annual_volatility) if annual_volatility > 0 else None
    total_cost = float(nav["commission"].sum() + nav["slippage"].sum())
    traded_notional = 0.0
    if not trades.empty:
        traded_notional = float((trades["trade_quantity"] * trades["open_price"]).sum())
    active = positions[positions["quantity"] != 0] if not positions.empty else positions
    active_start = pd.Timestamp(active["date"].min()).date().isoformat() if not active.empty else None
    return {
        "sample_start": pd.Timestamp(nav["date"].iloc[0]).date().isoformat(),
        "sample_end": pd.Timestamp(nav["date"].iloc[-1]).date().isoformat(),
        "active_start": active_start,
        "initial_capital": start_equity,
        "ending_equity": end_equity,
        "total_return": total_return,
        "annualized_return": annual_return,
        "annualized_volatility": annual_volatility,
        "sharpe_ratio_rf0": sharpe,
        "maximum_drawdown": float(nav["drawdown"].min()),
        "maximum_drawdown_duration_trading_days": _max_drawdown_duration(nav["drawdown"]),
        "trade_events": int(len(trades)),
        "roll_events": int(trades["is_roll"].sum()) if not trades.empty else 0,
        "total_commission": float(nav["commission"].sum()),
        "total_slippage": float(nav["slippage"].sum()),
        "total_cost": total_cost,
        "cost_as_fraction_initial_capital": total_cost / start_equity,
        "deferred_orders": int(nav["deferred_orders"].sum()),
        "maximum_margin_fraction": float((nav["margin_used"] / nav["equity"]).max()),
        "maximum_gross_leverage": float((nav["gross_notional"] / nav["equity"]).max()),
        "traded_price_units": traded_notional,
    }

