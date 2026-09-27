from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Holding:
    contract: str | None = None
    quantity: int = 0


def _round_toward_zero(value: float) -> int:
    if not np.isfinite(value):
        return 0
    return math.floor(value) if value >= 0 else math.ceil(value)


def _per_contract_cost(spec: dict, price: float) -> tuple[float, float]:
    commission = float(spec["commission_fixed"]) + float(spec["commission_rate"]) * price * float(spec["multiplier"])
    slippage = float(spec["slippage_ticks"]) * float(spec["tick_size"]) * float(spec["multiplier"])
    return commission, slippage


def _buffer_target(raw_target: int, current: int, fraction: float, same_contract: bool) -> int:
    if not same_contract:
        return raw_target
    width = max(1, int(round(abs(raw_target) * fraction)))
    if raw_target - width <= current <= raw_target + width:
        return current
    return raw_target


def _raw_ewmac_targets(
    prior_rows: dict[str, pd.Series], equity: float, strategy: dict, specs: dict, risk_target: float
) -> dict[str, int]:
    targets: dict[str, int] = {}
    for root, weight in zip(strategy["instruments"], strategy["weights"], strict=True):
        row = prior_rows[root]
        forecast = float(row.get("forecast", np.nan))
        volatility = float(row.get("annual_volatility", np.nan))
        price = float(row["close"])
        if not np.isfinite(forecast) or not np.isfinite(volatility) or volatility <= 0:
            targets[root] = 0
            continue
        denominator = float(specs[root]["multiplier"]) * price * volatility
        targets[root] = int(round((forecast / 10.0) * equity * risk_target * float(weight) / denominator))
    return targets


def _raw_relative_targets(
    prior_rows: dict[str, pd.Series], equity: float, strategy: dict, specs: dict, risk_target: float
) -> dict[str, int]:
    tf_root, t_root = strategy["instruments"]
    tf_row = prior_rows[tf_root]
    forecast = float(tf_row.get("forecast", np.nan))
    volatility = float(tf_row.get("annual_volatility", np.nan))
    hedge_ratio = float(tf_row.get("hedge_ratio", np.nan))
    if not all(np.isfinite(value) for value in (forecast, volatility, hedge_ratio)) or volatility <= 0:
        return {tf_root: 0, t_root: 0}
    tf_spec = specs[tf_root]
    t_spec = specs[t_root]
    tf_quantity = int(
        round(
            (forecast / 10.0)
            * equity
            * risk_target
            * 0.5
            / (float(tf_spec["multiplier"]) * float(tf_row["close"]) * volatility)
        )
    )
    t_quantity = int(
        round(-tf_quantity * hedge_ratio * float(tf_spec["multiplier"]) / float(t_spec["multiplier"]))
    )
    return {tf_root: tf_quantity, t_root: t_quantity}


def _constrain_targets(
    targets: dict[str, int], execution_rows: dict[str, pd.Series], equity: float, specs: dict,
    max_margin_fraction: float, max_gross_leverage: float,
) -> dict[str, int]:
    if equity <= 0:
        return {root: 0 for root in targets}
    margin = 0.0
    gross = 0.0
    for root, quantity in targets.items():
        notional = abs(quantity) * float(execution_rows[root]["open"]) * float(specs[root]["multiplier"])
        gross += notional
        margin += notional * float(specs[root]["margin_rate"])
    scale = 1.0
    if margin > equity * max_margin_fraction:
        scale = min(scale, equity * max_margin_fraction / margin)
    if gross > equity * max_gross_leverage:
        scale = min(scale, equity * max_gross_leverage / gross)
    if scale < 1.0:
        return {root: _round_toward_zero(quantity * scale) for root, quantity in targets.items()}
    return targets


def run_strategy(
    strategy_id: str,
    strategy: dict,
    panels: dict[str, pd.DataFrame],
    market: pd.DataFrame,
    specs: dict,
    run_config: dict,
    signal_config: dict,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    roots = list(strategy["instruments"])
    common_dates = panels[roots[0]].index
    for root in roots[1:]:
        common_dates = common_dates.intersection(panels[root].index)
    common_dates = common_dates.sort_values()
    if len(common_dates) < 2:
        raise ValueError(f"Insufficient common dates for {strategy_id}")
    lookup = market.set_index(["date", "contract"]).sort_index()
    holdings = {root: Holding() for root in roots}
    equity = float(run_config["initial_capital"])
    nav_rows: list[dict] = []
    trade_rows: list[dict] = []
    position_rows: list[dict] = []
    prior_date: pd.Timestamp | None = None

    for index, date in enumerate(common_dates):
        if index == 0:
            nav_rows.append(
                {
                    "date": date, "strategy_id": strategy_id, "equity": equity, "gross_pnl": 0.0,
                    "commission": 0.0, "slippage": 0.0, "net_pnl": 0.0, "daily_return": 0.0,
                    "margin_used": 0.0, "gross_notional": 0.0, "deferred_orders": 0,
                }
            )
            prior_date = date
            continue

        prior_rows = {root: panels[root].loc[prior_date] for root in roots}
        execution_rows: dict[str, pd.Series] = {}
        target_contracts: dict[str, str] = {}
        execution_available = True
        for root in roots:
            target_contract = str(prior_rows[root]["contract"])
            target_contracts[root] = target_contract
            key = (date, target_contract)
            if key not in lookup.index:
                execution_available = False
                break
            row = lookup.loc[key]
            if isinstance(row, pd.DataFrame):
                raise ValueError(f"Duplicate execution quote for {key}")
            if float(row["volume"]) <= 0 or not np.isfinite(float(row["open"])):
                execution_available = False
                break
            execution_rows[root] = row

        if strategy["kind"] == "ewmac_portfolio":
            raw_targets = _raw_ewmac_targets(
                prior_rows, equity, strategy, specs, float(run_config["annual_risk_target"])
            )
        elif strategy["kind"] == "relative_value":
            raw_targets = _raw_relative_targets(
                prior_rows, equity, strategy, specs, float(run_config["annual_risk_target"])
            )
        else:
            raise ValueError(f"Unknown strategy kind {strategy['kind']}")

        deferred_orders = 0
        if execution_available:
            buffered_targets = {
                root: _buffer_target(
                    raw_targets[root],
                    holdings[root].quantity,
                    float(signal_config["position_buffer_fraction"]),
                    holdings[root].contract == target_contracts[root],
                )
                for root in roots
            }
            raw_targets = _constrain_targets(
                buffered_targets,
                execution_rows,
                equity,
                specs,
                float(run_config["max_margin_fraction"]),
                float(run_config["max_gross_leverage"]),
            )
            execution_gross = sum(
                abs(raw_targets[root])
                * float(execution_rows[root]["open"])
                * float(specs[root]["multiplier"])
                for root in roots
            )
            execution_margin = sum(
                abs(raw_targets[root])
                * float(execution_rows[root]["open"])
                * float(specs[root]["multiplier"])
                * float(specs[root]["margin_rate"])
                for root in roots
            )
            if execution_margin > equity * float(run_config["max_margin_fraction"]) * 1.001:
                raise AssertionError("Execution-time margin constraint violated")
            if execution_gross > equity * float(run_config["max_gross_leverage"]) * 1.001:
                raise AssertionError("Execution-time leverage constraint violated")
        else:
            deferred_orders = sum(
                int(raw_targets[root] != holdings[root].quantity or target_contracts[root] != holdings[root].contract)
                for root in roots
            )

        gross_pnl = 0.0
        commission_total = 0.0
        slippage_total = 0.0
        for root in roots:
            spec = specs[root]
            multiplier = float(spec["multiplier"])
            holding = holdings[root]
            old_contract = holding.contract
            old_quantity = holding.quantity

            if not execution_available:
                target_contract = old_contract
                target_quantity = old_quantity
            else:
                target_contract = target_contracts[root]
                target_quantity = raw_targets[root]

            if old_contract is not None and old_quantity != 0:
                today_old_key = (date, old_contract)
                prior_old_key = (prior_date, old_contract)
                if today_old_key not in lookup.index or prior_old_key not in lookup.index:
                    raise RuntimeError(f"Missing held-contract mark for {root} {old_contract} on {date.date()}")
                today_old = lookup.loc[today_old_key]
                prior_old = lookup.loc[prior_old_key]
                if execution_available:
                    gross_pnl += old_quantity * multiplier * (
                        float(today_old["open"]) - float(prior_old["settle"])
                    )
                else:
                    gross_pnl += old_quantity * multiplier * (
                        float(today_old["settle"]) - float(prior_old["settle"])
                    )

            if execution_available:
                today_new = execution_rows[root]
                gross_pnl += target_quantity * multiplier * (
                    float(today_new["settle"]) - float(today_new["open"])
                )
                if old_contract == target_contract:
                    traded = abs(target_quantity - old_quantity)
                else:
                    traded = abs(old_quantity) + abs(target_quantity)
                commission_per, slippage_per = _per_contract_cost(spec, float(today_new["open"]))
                commission = traded * commission_per
                slippage = traded * slippage_per
                commission_total += commission
                slippage_total += slippage
                if traded:
                    trade_rows.append(
                        {
                            "date": date,
                            "strategy_id": strategy_id,
                            "root": root,
                            "old_contract": old_contract or "",
                            "new_contract": target_contract or "",
                            "old_quantity": old_quantity,
                            "new_quantity": target_quantity,
                            "trade_quantity": traded,
                            "execution_basis": "official daily open; signal formed after prior close",
                            "open_price": float(today_new["open"]),
                            "commission": commission,
                            "slippage": slippage,
                            "is_roll": bool(old_contract and old_contract != target_contract),
                        }
                    )
                holdings[root] = Holding(target_contract, target_quantity)

        net_pnl = gross_pnl - commission_total - slippage_total
        prior_equity = equity
        equity += net_pnl
        if equity <= 0:
            raise RuntimeError(f"Strategy {strategy_id} exhausted capital on {date.date()}")
        margin_used = 0.0
        gross_notional = 0.0
        for root in roots:
            holding = holdings[root]
            if holding.contract is None or holding.quantity == 0:
                mark = 0.0
            else:
                mark = float(lookup.loc[(date, holding.contract), "settle"])
            notional = abs(holding.quantity) * mark * float(specs[root]["multiplier"])
            margin = notional * float(specs[root]["margin_rate"])
            gross_notional += notional
            margin_used += margin
            position_rows.append(
                {
                    "date": date,
                    "strategy_id": strategy_id,
                    "root": root,
                    "contract": holding.contract or "",
                    "quantity": holding.quantity,
                    "settle": mark,
                    "notional": notional,
                    "margin": margin,
                    "signal_date": prior_date,
                    "forecast": float(prior_rows[root].get("forecast", np.nan)),
                }
            )
        nav_rows.append(
            {
                "date": date,
                "strategy_id": strategy_id,
                "equity": equity,
                "gross_pnl": gross_pnl,
                "commission": commission_total,
                "slippage": slippage_total,
                "net_pnl": net_pnl,
                "daily_return": net_pnl / prior_equity,
                "margin_used": margin_used,
                "gross_notional": gross_notional,
                "deferred_orders": deferred_orders,
            }
        )
        prior_date = date

    nav = pd.DataFrame(nav_rows)
    nav["running_peak"] = nav["equity"].cummax()
    nav["drawdown"] = nav["equity"] / nav["running_peak"] - 1.0
    return nav, pd.DataFrame(trade_rows), pd.DataFrame(position_rows)
