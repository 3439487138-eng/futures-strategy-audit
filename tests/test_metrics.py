import pandas as pd
import pytest

from futures_audit.metrics import calculate_metrics


def test_metrics_are_derived_from_ledger():
    nav = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
        "equity": [100.0, 110.0, 99.0], "daily_return": [0.0, 0.1, -0.1],
        "drawdown": [0.0, 0.0, -0.1], "commission": [0.0, 1.0, 1.0],
        "slippage": [0.0, 2.0, 2.0], "deferred_orders": [0, 0, 1],
        "margin_used": [0.0, 20.0, 10.0], "gross_notional": [0.0, 100.0, 50.0],
    })
    trades = pd.DataFrame({"trade_quantity": [1], "open_price": [100.0], "is_roll": [True]})
    positions = pd.DataFrame({"date": [pd.Timestamp("2025-01-02")], "quantity": [1]})
    metrics = calculate_metrics(nav, trades, positions)
    assert metrics["total_return"] == pytest.approx(-0.01)
    assert metrics["maximum_drawdown"] == -0.1
    assert metrics["total_cost"] == 6.0
    assert metrics["roll_events"] == 1
    assert metrics["deferred_orders"] == 1
