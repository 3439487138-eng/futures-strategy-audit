from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
import re
import subprocess
from pathlib import Path

import pandas as pd

from .catalog import CATALOG


def _fmt_percent(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.2%}"


def _fmt_number(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:,.3f}"


def _git_sha(root: Path) -> str:
    environment_sha = os.environ.get("GITHUB_SHA", "").strip()
    if re.fullmatch(r"[0-9a-fA-F]{40}", environment_sha):
        return environment_sha.lower()
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, OSError):
        return "uncommitted-local-run"


def _svg_series(nav: pd.DataFrame, column: str, title: str, color: str) -> str:
    width, height, pad = 900, 250, 35
    values = nav[column].astype(float).tolist()
    if not values:
        raise ValueError(f"No values for chart {title}")
    low, high = min(values), max(values)
    if math.isclose(low, high):
        high = low + 1.0
    points = []
    for index, value in enumerate(values):
        x = pad + (width - 2 * pad) * index / max(1, len(values) - 1)
        y = pad + (height - 2 * pad) * (high - value) / (high - low)
        points.append(f"{x:.1f},{y:.1f}")
    return (
        f'<figure><figcaption>{html.escape(title)}</figcaption>'
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fff"/>'
        f'<line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#bbb"/>'
        f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(points)}"/>'
        f'<text x="{pad}" y="20" font-size="12">max {high:,.3f}</text>'
        f'<text x="{pad}" y="{height-8}" font-size="12">min {low:,.3f}</text>'
        "</svg></figure>"
    )


def render_report(root: Path, metrics: dict, manifest: dict, outputs: dict[str, dict]) -> Path:
    generated = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    sha = _git_sha(root)
    metric_rows = []
    figures = []
    holdings_rows = []
    trade_rows = []
    for strategy_id, values in metrics.items():
        metric_rows.append(
            "<tr>" + "".join(
                f"<td>{html.escape(text)}</td>"
                for text in [
                    strategy_id,
                    values["sample_end"],
                    _fmt_percent(values["total_return"]),
                    _fmt_percent(values["annualized_return"]),
                    _fmt_percent(values["annualized_volatility"]),
                    _fmt_number(values["sharpe_ratio_rf0"]),
                    _fmt_percent(values["maximum_drawdown"]),
                    f"{values['trade_events']}",
                    f"{values['total_cost']:,.2f}",
                ]
            ) + "</tr>"
        )
        nav = outputs[strategy_id]["nav"]
        figures.append(_svg_series(nav, "equity", f"{strategy_id} equity (CNY)", "#155eef"))
        figures.append(_svg_series(nav, "drawdown", f"{strategy_id} drawdown", "#c4320a"))
        positions = outputs[strategy_id]["positions"]
        if not positions.empty:
            latest = positions[positions["date"] == positions["date"].max()]
            for _, row in latest.iterrows():
                holdings_rows.append(
                    f"<tr><td>{strategy_id}</td><td>{row['root']}</td><td>{row['contract']}</td>"
                    f"<td>{int(row['quantity'])}</td><td>{float(row['settle']):,.3f}</td></tr>"
                )
        trades = outputs[strategy_id]["trades"]
        if not trades.empty:
            for _, row in trades.tail(10).iterrows():
                trade_rows.append(
                    f"<tr><td>{strategy_id}</td><td>{pd.Timestamp(row['date']).date()}</td><td>{row['root']}</td>"
                    f"<td>{row['old_contract']}</td><td>{row['new_contract']}</td><td>{int(row['old_quantity'])}</td>"
                    f"<td>{int(row['new_quantity'])}</td><td>{float(row['commission']) + float(row['slippage']):,.2f}</td></tr>"
                )
    catalog_rows = "".join(
        f"<tr><td>{item['id']}</td><td>{html.escape(item['concept'])}</td><td>{item['status']}</td><td>{html.escape(item['reason'])}</td></tr>"
        for item in CATALOG
    )
    coverage = manifest["coverage"]
    gaps = manifest["calendar_gaps"]
    trailing_no_target = manifest.get("trailing_no_target_contract_rows", [])
    source_summary = "".join(
        f"<li>{exchange}: {values['start']} to {values['end']}; {values['trading_days']} observed trading days</li>"
        for exchange, values in coverage.items()
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Futures Strategy Replication Audit</title><style>
body{{font:15px/1.5 system-ui,sans-serif;color:#172b4d;max-width:1180px;margin:24px auto;padding:0 18px;background:#f7f8fa}}
h1,h2{{color:#101828}} section{{background:#fff;border:1px solid #d0d5dd;border-radius:10px;padding:18px;margin:16px 0}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{border:1px solid #d0d5dd;padding:7px;text-align:left;vertical-align:top}}
th{{background:#eef4ff}} .tag{{display:inline-block;background:#ecfdf3;color:#027a48;padding:3px 8px;border-radius:12px}}
.warn{{background:#fffaeb;border-left:4px solid #f79009;padding:10px}} figure{{margin:20px 0}} svg{{width:100%;height:auto;border:1px solid #eee}}
code{{background:#f2f4f7;padding:2px 4px}} </style></head><body>
<h1>Futures Strategy Replication Audit</h1>
<section><h2>Executive Summary</h2><p><span class="tag">adapted replication</span></p>
<p>Three independently executable strategies are rebuilt from the audited source concepts. They use actual delivery-month contracts from CFFEX and SHFE. This report does not treat the original folder as one reproduced strategy and does not reuse saved notebook outputs.</p>
<p class="warn"><strong>Research only; not investment advice.</strong> S09-SHFE-CU-RB is explicitly a public-data proxy version, not a strict reproduction of a commodity notebook.</p></section>
<section><h2>Headline Metrics</h2><table><thead><tr><th>Strategy</th><th>Data end</th><th>Total return</th><th>Annualized return</th><th>Annualized volatility</th><th>Sharpe (rf=0)</th><th>Max drawdown</th><th>Trade events</th><th>Total cost (CNY)</th></tr></thead><tbody>{''.join(metric_rows)}</tbody></table></section>
<section><h2>Figures and Result Tables</h2>{''.join(figures)}
<h3>Current holdings</h3><table><thead><tr><th>Strategy</th><th>Root</th><th>Contract</th><th>Contracts</th><th>Settlement</th></tr></thead><tbody>{''.join(holdings_rows) or '<tr><td colspan="5">unavailable</td></tr>'}</tbody></table>
<h3>Last ten transactions per strategy</h3><table><thead><tr><th>Strategy</th><th>Date</th><th>Root</th><th>Old contract</th><th>New contract</th><th>Old qty</th><th>New qty</th><th>Cost</th></tr></thead><tbody>{''.join(trade_rows) or '<tr><td colspan="8">unavailable</td></tr>'}</tbody></table></section>
<section><h2>Methodology Mapping</h2><table><thead><tr><th>Original rule</th><th>Implementation</th><th>Status</th></tr></thead><tbody>
<tr><td>S09 multi-speed EWMAC (2/8 through 64/256), fixed scalars, FDM 1.26, cap ±20 and position buffer</td><td>Point-in-time gapless signal series; integer delivery-contract positions; prior-close signal and next official open execution.</td><td>adapted</td></tr>
<tr><td>S28 TF/T volatility-ratio relative value</td><td>Rolling-only hedge ratio and spread z-score; explicitly market-neutral opposite legs, unlike the ambiguous same-sign notebook code.</td><td>adapted</td></tr>
<tr><td>Commodity strategy material</td><td>S09 signal applied to actual SHFE CU/RB delivery contracts.</td><td>adapted / public-data proxy version</td></tr>
</tbody></table></section>
<section><h2>Data and Assumptions</h2><ul>{source_summary}</ul>
<p>Retrieved rows: {manifest['normalized_rows']:,}; contracts: {manifest['contract_count']}; retrieval manifest contains URL, UTC time, byte count and SHA-256 for every response.</p>
<p>CFFEX source: official monthly ZIP files. SHFE source: official daily JSON. Observed exchange files define the trading calendar; cross-exchange mismatches inside shared coverage fail the run. CFFEX transport uses the official HTTP endpoint because HTTPS timed out in the audited environment; hashes are retained.</p>
<p>Signals use closing data after day t. Orders execute no earlier than day t+1 at the official reported open, only when volume is positive. Daily P&amp;L is marked to settlement. Fixed conservative margin rates and transparent cost/slippage assumptions are configuration inputs, not claims of reconstructed historical broker schedules.</p>
<p>Calendar differences recorded: CFFEX-only {len(gaps['CFFEX_only'])}; SHFE-only {len(gaps['SHFE_only'])}.</p>
<p>Trailing SHFE HTTP-200 responses without CU/RB rows: {html.escape(', '.join(trailing_no_target) or 'none')}. These are not accepted as market observations.</p></section>
<section><h2>Fidelity Gaps and Limitations</h2><ul>
<li>The original notebooks queried continuous/root symbols and did not specify a valid delivery-contract roll. The new roll uses prior-close open interest and exits before estimated last trade dates.</li>
<li>Additive same-contract close changes create signal-only series; all P&amp;L uses raw contracts, so roll jumps are never booked as returns.</li>
<li>Daily OHLC cannot prove intraday queue priority or limit-lock fillability. Positive volume and coherent OHLC are required; reported execution is a daily-open approximation, not a tick-level fill claim.</li>
<li>Historical margin and broker fee schedules are unavailable in the source materials. Conservative fixed assumptions are disclosed in configuration.</li>
</ul></section>
<section><h2>Strategy Inventory S01–S28</h2><table><thead><tr><th>ID</th><th>Concept</th><th>Status</th><th>Reason</th></tr></thead><tbody>{catalog_rows}</tbody></table></section>
<section><h2>Reproducibility</h2><ul><li>Generated: {generated}</li><li>Strategy commit: {html.escape(sha)}</li><li>Command: <code>python -m futures_audit.cli run --config configs/base.toml</code></li><li>Runtime: Python 3.12; dependencies pinned in pyproject.toml</li><li>paper-replicator skill SHA-256: A086CE12A88874C66B1CE006169B343F2151552001B8B1E3BFB5E446CEA6260F</li></ul></section>
</body></html>"""
    path = root / "reports" / "replication_report.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
    payload = {
        "paper": {"title": "Futures strategy source-material reconstruction", "citation": "Source notebooks (audited)", "source": "excluded original materials"},
        "run": {"status": "adapted", "mode": "practical adaptation", "sample": f"{coverage['common']['start']} to {coverage['common']['end']}", "generated_at": generated, "commit_sha": sha, "command": "python -m futures_audit.cli run --config configs/base.toml"},
        "summary": "Three strategies were recomputed from official delivery-contract data.",
        "metrics": metrics,
        "methodology": ["prior-close signal / next-open execution", "real delivery contracts", "daily settlement mark-to-market"],
        "assumptions": ["fixed conservative margin and costs", "zero risk-free rate for Sharpe"],
        "fidelity_gaps": ["adapted roll rules", "daily bars do not prove intraday fills"],
        "trailing_no_target_contract_rows": trailing_no_target,
        "figures": ["embedded SVG equity and drawdown"],
        "tables": ["metrics", "holdings", "transactions", "strategy inventory"],
    }
    (root / "reports" / "report_payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
