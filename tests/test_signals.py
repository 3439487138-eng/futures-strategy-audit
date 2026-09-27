import pandas as pd

from futures_audit.signals import build_root_panel, estimated_last_trade_date, ewmac_features


def _row(date, contract, month, oi, close):
    return {
        "date": pd.Timestamp(date), "exchange": "CFFEX", "root": "IF", "contract": contract,
        "delivery_month": month, "open": close, "high": close + 1, "low": close - 1,
        "close": close, "settle": close, "pre_settle": close - 1, "volume": 100,
        "open_interest": oi,
    }


def test_roll_uses_same_day_close_open_interest_and_gapless_signal():
    frame = pd.DataFrame([
        _row("2025-01-02", "IF2503", "2503", 200, 100),
        _row("2025-01-02", "IF2506", "2506", 100, 110),
        _row("2025-01-03", "IF2503", "2503", 90, 101),
        _row("2025-01-03", "IF2506", "2506", 300, 112),
    ])
    panel = build_root_panel(frame, "IF", {"last_trade_rule": "third_friday"}, 10)
    assert panel.loc[pd.Timestamp("2025-01-02"), "contract"] == "IF2503"
    assert panel.loc[pd.Timestamp("2025-01-03"), "contract"] == "IF2506"
    assert panel.loc[pd.Timestamp("2025-01-03"), "signal_price"] == 102


def test_last_trade_rules_are_deterministic():
    assert estimated_last_trade_date("2503", "third_friday").isoformat() == "2025-03-21"
    assert estimated_last_trade_date("2503", "second_friday").isoformat() == "2025-03-14"
    assert estimated_last_trade_date("2503", "day_15").isoformat() == "2025-03-15"


def test_future_price_change_does_not_change_prior_forecast():
    index = pd.date_range("2024-01-01", periods=320, freq="B")
    base = pd.DataFrame({"signal_price": range(1000, 1320)}, index=index, dtype=float)
    base["signal_return"] = base["signal_price"].pct_change()
    config = {
        "volatility_span": 32, "minimum_volatility_observations": 64,
        "ewmac_fast_spans": [2, 4, 8, 16, 32, 64],
        "ewmac_scalars": [12.1, 8.53, 5.95, 4.1, 2.79, 1.91],
        "forecast_diversification_multiplier": 1.26, "forecast_cap": 20.0,
    }
    first = ewmac_features(base, config)
    changed = base.copy()
    changed.iloc[-1, changed.columns.get_loc("signal_price")] += 500
    changed["signal_return"] = changed["signal_price"].pct_change()
    second = ewmac_features(changed, config)
    pd.testing.assert_series_equal(first["forecast"].iloc[:-1], second["forecast"].iloc[:-1])

