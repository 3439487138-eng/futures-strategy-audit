# Data sources and observed feasibility

## Production inputs

| Provider | Interface | Fields used | Coverage policy |
|---|---|---|---|
| CFFEX | `http://www.cffex.com.cn/sj/historysj/YYYYMM/zip/YYYYMM.zip` | delivery contract, open, high, low, close, settlement, prior settlement, volume, open interest | Every month from configured start through current month |
| SHFE | `https://www.shfe.com.cn/data/tradedata/future/dailydata/kxYYYYMMDD.dat` | product, delivery month, open, high, low, close, settlement, prior settlement, volume, open interest | Every weekday from configured start through current date; official 404s and HTTP-200 responses without CU/RB rows are retained separately in the manifest |
| CFFEX | official IF/TF/T product specification pages | multiplier, tick, listed months, last trade rule, minimum margin | Retrieved and hashed on every clean run |
| SHFE | `ContractBaseInfoYYYYMMDD.dat` and `ContractDailyTradeArgumentYYYYMMDD.dat` | listing/expiry/delivery dates, current long/short margin and limit parameters | Latest common observed trading day |

The SHFE route is not guessed from a third-party wrapper. It is the route invoked by SHFE's own `generateData_kx_f.js` through `api_futures_kx()` in `api.js`. CFFEX monthly ZIPs contain one official CSV per trading day. No Tushare, Yahoo, cash index, yield index, continuous futures, or synthetic market observation is permitted in production.

## Direct preflight evidence (2026-09-27 Asia/Shanghai)

- CFFEX `202508.zip`: HTTP 200, `application/zip`, 465,495 bytes, SHA-256 `676D391001D90D0F36C065BCCD807E94B96D76E42B300F7E1C0F12A542179758`. It contained 21 daily CSV files and actual IF, TF, and T delivery-month rows with OHLC, volume, open interest, settlement, and prior settlement.
- CFFEX current `202609.zip`: HTTP 200, `application/zip`, 383,092 bytes during preflight. The current-month path is therefore live, not only historical documentation.
- SHFE `kx20260924.dat`: HTTP 200, `application/json`, 123,100 bytes, SHA-256 `6C3DC7380FD763E1A5BC281697FE94C1F0E46AD330EF9CD77D75BCD2B345FD20`. The document had 332 rows; CU and RB each had 12 numeric delivery months with complete OHLC, volume, open interest, settlement, and prior settlement.
- SHFE `kx20260925.dat`: HTTP 404 during repeated preflight; 2026-09-24 was the latest successful observation. The pipeline does not infer whether a 404 is a holiday. It cross-checks successful dates against CFFEX and fails on an interior mismatch.
- On 2026-09-28 at 09:51 Asia/Shanghai, SHFE `kx20260928.dat` returned HTTP 200 but contained no CU/RB delivery-contract rows. The run records `no_target_contract_rows` with a payload hash and does not count this response as a market observation. A no-target response inside established common coverage fails validation; at the trailing edge it documents that the current session is not yet usable.
- SHFE annual 2025 archive was advertised as 76,397,695 bytes and was too slow for the audited local link. This is why the pipeline uses the smaller daily official documents and keeps only CU/RB after validation.
- SHFE `ContractBaseInfo20260924.dat` and `ContractDailyTradeArgument20260924.dat`: HTTP 200 with 301 rows each. The CU example included open, expiry, and delivery dates; the trading-argument row included speculative and hedge long/short margin ratios plus upper/lower limits.

## Stability and gaps

CFFEX HTTPS timed out repeatedly from the audited local environment, while the official-domain HTTP monthly ZIP returned successfully. The manifest records the exact URL and SHA-256 of every downloaded month. This transport limitation is explicit; it is not hidden behind a third-party mirror.

Both providers are retried with bounded exponential backoff. Cached raw responses may speed a repeated local run, but each cache item is hashed and raw caches are ignored by Git. Completed CFFEX months may be reused, while the requested end month is always downloaded again. SHFE observations and 404 markers in the trailing seven days are always probed again because a same-day response may change after settlement publication. A transient SHFE failure other than a confirmed 404 fails the run. GitHub Actions begins without the raw cache and must fetch all inputs anew.

The observed trading calendar is the set of successful official daily observations. CFFEX daily entries and SHFE daily JSON dates are compared inside their shared coverage. A date available from only one exchange inside that interval is an unresolved gap and fails publication.

## Contract metadata and assumptions

- IF: CFFEX contract multiplier CNY 300 per index point, minimum tick 0.2, third-Friday last trading date rule.
- TF and T: CFFEX CNY 1,000,000 notional quoted per CNY 100, hence CNY 10,000 per price point; minimum tick 0.005; second-Friday last trading date rule.
- CU: SHFE 5 tonnes per contract, minimum tick CNY 10 per tonne, day-15 last trading date rule.
- RB: SHFE 10 tonnes per contract, minimum tick CNY 1 per tonne, day-15 last trading date rule.

The multiplier and expiry-rule sources are the official product/rule URLs in `configs/base.toml`. Historical exchange/broker margin and fee schedules were not present in the source material, so conservative fixed parameters are disclosed in configuration. They are constraints and cost assumptions, not claimed historical reconstructions.
