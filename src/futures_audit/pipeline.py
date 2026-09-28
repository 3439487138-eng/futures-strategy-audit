from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd

from .config import load_config
from .data import acquire_exchange_data, write_json, write_normalized
from .engine import run_strategy
from .metrics import calculate_metrics
from .report import render_report
from .signals import build_root_panel, ewmac_features, relative_value_features, validate_market_rows


def run_pipeline(root: Path, config_path: Path) -> dict:
    config = load_config(config_path)
    start = dt.date.fromisoformat(config["run"]["start_date"])
    end = dt.date.fromisoformat(config["run"]["end_date"])
    market, manifest = acquire_exchange_data(
        start, end, root / "data" / "raw", int(config["run"]["workers"])
    )
    validate_market_rows(market)
    write_normalized(market, root / "data" / "processed" / "contracts.csv")
    write_json(manifest, root / "outputs" / "source_manifest.json")
    base_panels = {
        root_code: build_root_panel(
            market, root_code, spec, int(config["run"]["roll_buffer_calendar_days"])
        )
        for root_code, spec in config["instruments"].items()
    }
    metrics: dict[str, dict] = {}
    report_outputs: dict[str, dict] = {}
    for strategy_id, strategy in config["strategies"].items():
        if strategy["kind"] == "ewmac_portfolio":
            panels = {
                root_code: ewmac_features(base_panels[root_code], config["signal"])
                for root_code in strategy["instruments"]
            }
        else:
            first, second = strategy["instruments"]
            first_panel, second_panel = relative_value_features(
                base_panels[first], base_panels[second], config["signal"]
            )
            panels = {first: first_panel, second: second_panel}
        nav, trades, positions = run_strategy(
            strategy_id,
            strategy,
            panels,
            market,
            config["instruments"],
            config["run"],
            config["signal"],
        )
        strategy_dir = root / "outputs" / strategy_id
        strategy_dir.mkdir(parents=True, exist_ok=True)
        nav.to_csv(strategy_dir / "nav.csv", index=False, date_format="%Y-%m-%d")
        trades.to_csv(strategy_dir / "trades.csv", index=False, date_format="%Y-%m-%d")
        positions.to_csv(strategy_dir / "positions.csv", index=False, date_format="%Y-%m-%d")
        metrics[strategy_id] = calculate_metrics(nav, trades, positions)
        report_outputs[strategy_id] = {"nav": nav, "trades": trades, "positions": positions}
    write_json(metrics, root / "outputs" / "metrics.json")
    render_report(root, metrics, manifest, report_outputs)
    return {"metrics": metrics, "manifest": manifest}


def validate_outputs(root: Path) -> None:
    manifest_path = root / "outputs" / "source_manifest.json"
    metrics_path = root / "outputs" / "metrics.json"
    report_path = root / "reports" / "replication_report.html"
    payload_path = root / "reports" / "report_payload.json"
    for path in (manifest_path, metrics_path, report_path, payload_path):
        if not path.exists() or path.stat().st_size == 0:
            raise AssertionError(f"Missing or empty required output: {path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    if set(metrics) != {"S09-IF-T", "S28-TF-T", "S09-SHFE-CU-RB"}:
        raise AssertionError("Published strategy set is incomplete or unexpected")
    if manifest["calendar_gaps"]["CFFEX_only"] or manifest["calendar_gaps"]["SHFE_only"]:
        raise AssertionError("Exchange calendar gaps remain unresolved")
    allowed_statuses = {"ok", "cache", "http_404", "no_target_contract_rows"}
    unexpected = sorted({item["status"] for item in manifest["sources"]} - allowed_statuses)
    if unexpected:
        raise AssertionError(f"Unexpected source status: {unexpected}")
    payload_records = [
        item for item in manifest["sources"]
        if item["status"] in {"ok", "cache", "no_target_contract_rows"}
    ]
    if not payload_records or any(not item["sha256"] for item in payload_records):
        raise AssertionError("Every source response payload must have a SHA-256 hash")
    common_end = manifest["coverage"]["common"]["end"]
    if any(value <= common_end for value in manifest["trailing_no_target_contract_rows"]):
        raise AssertionError("No-target SHFE response appears inside common source coverage")
    if any("tushare" in item["requested_url"].lower() for item in manifest["sources"]):
        raise AssertionError("Forbidden provider in production manifest")
    report = report_path.read_text(encoding="utf-8")
    required = [
        "Executive Summary", "Headline Metrics", "Figures and Result Tables", "Methodology Mapping",
        "Data and Assumptions", "Fidelity Gaps and Limitations", "Reproducibility", "Strategy Inventory S01–S28",
    ]
    missing = [section for section in required if section not in report]
    if missing:
        raise AssertionError(f"Report is missing sections: {missing}")
    if "<svg" not in report or re.search(r'<(?:script|img|link)[^>]+(?:src|href)=["\']https?://', report, re.I):
        raise AssertionError("Report must contain embedded figures and no external assets")
    for strategy_id, values in metrics.items():
        if values["sample_end"] != manifest["coverage"]["common"]["end"]:
            raise AssertionError(f"{strategy_id} is stale relative to common source coverage")
        for filename in ("nav.csv", "trades.csv", "positions.csv"):
            path = root / "outputs" / strategy_id / filename
            if not path.exists():
                raise AssertionError(f"Missing strategy output {path}")
        nav = pd.read_csv(root / "outputs" / strategy_id / "nav.csv")
        if nav.empty or not (nav["equity"].diff().abs().fillna(0) > 0).any():
            raise AssertionError(f"{strategy_id} did not produce a nontrivial recomputed NAV")
