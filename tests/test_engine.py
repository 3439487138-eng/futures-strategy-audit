import pandas as pd

from futures_audit.engine import run_strategy


def test_signal_executes_next_day_and_costs_reduce_equity():
    dates = pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"])
    market = pd.DataFrame({
        "date": dates, "root": ["IF"] * 3, "contract": ["IF2503"] * 3,
        "open": [100.0, 101.0, 103.0], "settle": [100.0, 102.0, 104.0], "volume": [100] * 3,
    })
    panel = pd.DataFrame({
        "contract": ["IF2503"] * 3, "close": [100.0, 102.0, 104.0],
        "forecast": [10.0, 10.0, 10.0], "annual_volatility": [0.2, 0.2, 0.2],
    }, index=dates)
    spec = {
        "IF": {"multiplier": 10.0, "margin_rate": 0.1, "commission_fixed": 1.0,
               "commission_rate": 0.0, "slippage_ticks": 1.0, "tick_size": 0.5}
    }
    nav, trades, positions = run_strategy(
        "X", {"kind": "ewmac_portfolio", "instruments": ["IF"], "weights": [1.0]},
        {"IF": panel}, market, spec,
        {"initial_capital": 100000.0, "annual_risk_target": 0.2, "max_margin_fraction": 0.6, "max_gross_leverage": 4.0},
        {"position_buffer_fraction": 0.1},
    )
    assert pd.Timestamp(trades.iloc[0]["date"]) == pd.Timestamp("2025-01-03")
    assert trades.iloc[0]["commission"] > 0
    assert trades.iloc[0]["slippage"] > 0
    assert nav.iloc[1]["net_pnl"] < nav.iloc[1]["gross_pnl"]
    assert pd.Timestamp(positions.iloc[0]["signal_date"]) == pd.Timestamp("2025-01-02")


def test_margin_and_leverage_constraints_hold():
    dates = pd.to_datetime(["2025-01-02", "2025-01-03"])
    market = pd.DataFrame({"date": dates, "root": ["IF"] * 2, "contract": ["IF2503"] * 2,
                           "open": [100.0, 100.0], "settle": [100.0, 100.0], "volume": [100, 100]})
    panel = pd.DataFrame({"contract": ["IF2503"] * 2, "close": [100.0, 100.0],
                          "forecast": [20.0, 20.0], "annual_volatility": [0.001, 0.001]}, index=dates)
    spec = {"IF": {"multiplier": 100.0, "margin_rate": 0.2, "commission_fixed": 0.0,
                    "commission_rate": 0.0, "slippage_ticks": 0.0, "tick_size": 1.0}}
    nav, _, _ = run_strategy(
        "X", {"kind": "ewmac_portfolio", "instruments": ["IF"], "weights": [1.0]}, {"IF": panel},
        market, spec, {"initial_capital": 100000.0, "annual_risk_target": 1.0,
                       "max_margin_fraction": 0.5, "max_gross_leverage": 2.0},
        {"position_buffer_fraction": 0.0},
    )
    assert (nav["margin_used"] <= nav["equity"] * 0.501).all()
    assert (nav["gross_notional"] <= nav["equity"] * 2.001).all()

