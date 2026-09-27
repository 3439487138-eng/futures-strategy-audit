# Futures Strategy Audit

This repository is an independent, auditable reconstruction of three selected strategies from the excluded source-material folder. It does not publish the original notebooks, licensed data, local paths, or credentials, and it does not describe the whole source folder as one reproduced strategy.

Published strategies:

| Strategy | Market | Status | Fidelity |
|---|---|---|---|
| S09-IF-T | CFFEX IF and T delivery contracts | Fully implemented | Adapted replication |
| S28-TF-T | CFFEX TF and T delivery contracts | Fully implemented | Adapted, market-neutral relative value |
| S09-SHFE-CU-RB | SHFE CU and RB delivery contracts | Fully implemented | Public-data proxy version; not a strict commodity-notebook reproduction |

The complete S01–S28 disposition is in [docs/strategy_catalog.md](docs/strategy_catalog.md). S27 is explicitly retained as missing/insufficient rather than silently skipped.

## Reproduce locally

Python 3.12 is required. No API key is used.

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python -m pip install -e . --no-deps
python -m pytest
python scripts/security_scan.py
python -m futures_audit.cli run --config configs/base.toml
python -m futures_audit.cli validate
```

The run fetches official exchange files again. Raw and normalized market data remain ignored. Safe derived ledgers, metrics, source hashes, and the standalone HTML report are written under `outputs/` and `reports/`.

## Execution and accounting contract

- A day-t close signal may first trade at the reported day-t+1 open.
- A trade requires an official delivery-contract row, a finite coherent OHLC bar, and positive daily volume.
- Contract selection uses only close-of-day open interest known on the signal date.
- Signals use an additive same-contract-change series; P&L always uses raw delivery contracts.
- Positions are integer contracts and are constrained by margin usage and gross leverage.
- Roll trades, commission, explicit slippage, daily settlement mark-to-market, NAV, drawdown, and metrics are derived from the ledgers.
- A missing held-contract settlement is fatal. There is no cash-index, yield-index, continuous-contract, random-data, or hard-coded-result fallback.

See [docs/methodology.md](docs/methodology.md) and [docs/data_sources.md](docs/data_sources.md) for the exact rules and limitations.

## GitHub Actions

`.github/workflows/replication.yml` is manual-dispatch only. A clean runner installs pinned dependencies, runs tests and the security scan, fetches current official data, runs every published strategy, validates report freshness, uploads an artifact, and commits safe derived results back to the selected branch. Any failed prerequisite fails the workflow; there is no `continue-on-error`, stale result cache, or skipped backtest path.

The workflow needs `contents: write` and repository policy must permit the Actions bot to push to the dispatched branch.

## License

No license is included because no authorization decision was provided. Public repository visibility does not itself grant reuse rights.
