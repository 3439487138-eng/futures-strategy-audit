# Strategy catalog S01–S28

The source material contains 27 numbered concepts (S01–S26 and S28), not 28 complete strategies. S27 is absent. Saved figures are historical notebook outputs and are not new backtest evidence.

| ID | Concept | Status | Reason |
|---|---|---|---|
| S01 | Buy-and-hold analytics | 仅诊断 | Descriptive analysis; no complete futures execution rule |
| S02 | Volatility targeting | 仅诊断 | Full-sample scaling; no delivery-contract roll ledger |
| S03 | Blended long/short volatility | 仅诊断 | Mixes spot and opaque continuous proxies |
| S04 | Risk-balanced IF/T | 仅诊断 | Full-sample IDM and non-executable positions |
| S05 | Moving-average trend filter | 仅诊断 | Signal found; production execution absent |
| S06 | EWMA trend | 仅诊断 | Signal found; production execution absent |
| S07 | Scaled/capped EWMAC | 仅诊断 | Original calibration has look-ahead |
| S08 | Buffered EWMAC | 仅诊断 | No real roll or fill accounting |
| S09 | Multi-speed EWMAC | 已完整实现 | S09-IF-T plus S09-SHFE-CU-RB public-data proxy |
| S10 | 60-day price delta labelled carry | 规则不足 | Momentum is not contract carry |
| S11 | Trend plus pseudo-carry | 规则不足 | Carry is not defined from simultaneous contracts |
| S12 | Special cap/scaling | 仅诊断 | Non-point-in-time calibration |
| S13 | Volatility regime multiplier | 仅诊断 | Futures accounting absent |
| S14 | Synthetic spot from carry | 数据不足 | Point-in-time spot/carry source absent |
| S15 | Seasonal carry | 数据不足 | Validated curve/calendar absent; original fills calendar days |
| S16 | Dynamic trend/carry weights | 规则不足 | Markdown and code disagree |
| S17 | Normalized-price trend | 仅诊断 | No audited delivery-contract implementation |
| S18 | Asset-class normalized trend | 仅诊断 | Executable universe needs a decision |
| S19 | Relative-price momentum | 仅诊断 | Original universe mixes non-futures proxies |
| S20 | Cross-sectional carry | 数据不足 | Requires point-in-time comparable curves |
| S21 | Breakout | 仅诊断 | Order and roll rules absent |
| S22 | Value/relative-price reversal | 规则不足 | Valuation anchor not fully specified |
| S23 | EWMAC acceleration | 仅诊断 | No audited execution implementation |
| S24 | Skew | 仅诊断 | Statistic present, complete trade rule absent |
| S25 | Greedy multi-asset weights | 数据不足 | Cash/yield proxies and full-sample optimization |
| S26 | Mean reversion/limit order | 规则不足 | No valid fill or intraday path rule |
| S27 | Missing | 规则不足 | No S27 notebook or specification |
| S28 | TF/T relative value | 已完整实现 | Adapted rolling market-neutral implementation |

