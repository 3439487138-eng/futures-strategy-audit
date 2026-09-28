# Local and isolated validation record

## Validated candidate

- Validation date: 2026-09-28 Asia/Shanghai
- Candidate revision: `dfe27b2a189f0521b8123fd261f07255ef1ebeae`
- Runtime: CPython 3.12.10 in a newly created virtual environment
- Installation: exact packages from `requirements.lock`, followed by editable project installation without dependency resolution
- Checkout: independent clone in an operating-system temporary directory

Before the isolated run, every checked-in file under `outputs/` and `reports/` was moved outside the checkout. Previously downloaded official exchange responses were copied into the ignored raw-data cache; this is source-observation reuse, not result reuse. The mutable edge remained live: the requested CFFEX month and the trailing seven SHFE calendar days were downloaded or probed again. No NAV, trade ledger, metric, or report was present when the run began.

## Commands executed

```text
python -m pip install --upgrade pip==25.2
python -m pip install -r requirements.lock
python -m pip install -e . --no-deps
python -m pytest -q
python scripts/security_scan.py .
python -m futures_audit.cli run --config configs/base.toml
python -m futures_audit.cli validate
python scripts/security_scan.py .
```

## Evidence

- Tests: 14 passed.
- Security scan before and after acquisition: passed.
- Requested end: 2026-09-28.
- Accepted common CFFEX/SHFE coverage: 2025-01-02 through 2026-09-24, 421 trading days.
- Interior exchange calendar differences: CFFEX-only 0; SHFE-only 0.
- Trailing unavailable observation: the 2026-09-28 SHFE HTTP-200 response contained no CU/RB delivery-contract rows and was excluded from market data.
- `outputs/metrics.json` SHA-256: `4E85C15AF9F5374FDB3EAAC3C16AA5FB8E82A0616268EE0ADC3C1DB7E2BBD4A1`.
- All ten financial result files under `outputs/` matched the checked-in versions byte for byte after isolated recomputation.
- The isolated report recorded the candidate revision above and passed the embedded-asset and freshness checks.

The auditable outputs are `outputs/source_manifest.json`, `outputs/metrics.json`, each strategy's `nav.csv`, `trades.csv`, and `positions.csv`, plus `reports/replication_report.html` and `reports/report_payload.json`. Raw exchange responses and normalized contract data remain ignored and are not publication artifacts.

This record covers local validation only. GitHub publication, the clean hosted workflow, artifact download, and bot result commit remain separate required gates.
