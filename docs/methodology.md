# Methodology and fidelity decisions

## Shared contract selection

For every root and date, the engine excludes nonnumeric delivery-month summaries, zero-volume rows, zero-open-interest rows, and contracts within ten calendar days of the estimated last trading date. Among eligible contracts it selects the highest open-interest contract, breaking ties by volume and contract code. Selection is made from day-t closing observations and becomes eligible for execution only on day t+1.

When the selected contract changes, the signal series adds the new contract's same-contract close change. If no prior close exists for that delivery month, the signal series is unchanged for that day. This prevents the price level gap between two delivery months from becoming a trading return. Account P&L never uses this adjusted series.

## S09-IF-T

IF and T receive equal risk budgets. Each uses six EWMAC pairs: 2/8, 4/16, 8/32, 16/64, 32/128, and 64/256. Fixed forecast scalars are 12.1, 8.53, 5.95, 4.10, 2.79, and 1.91. Individual forecasts and the final forecast are capped at ±20; the six-rule mean is multiplied by 1.26. Volatility is a point-in-time exponentially weighted estimate. The forecast is converted to integer contracts and subjected to a 10% position buffer.

This preserves the auditable signal idea from S09 while removing the original full-sample IDM, same-close execution, wrong IF multiplier, fractional positions, and continuous-symbol roll jump.

## S28-TF-T

The original notebook computes a volatility ratio and a TF/T price spread, but it uses a full-sample correlation and produces same-sign legs despite describing a cross-market relative position. The published implementation is therefore explicitly adapted: a rolling 60-day absolute-price-volatility ratio scales T against TF; the spread's rolling z-score forms a capped mean-reversion forecast; TF and T are held in opposite, multiplier-aware integer legs.

This is not claimed as a strict reproduction of the ambiguous notebook code.

## S09-SHFE-CU-RB

The S09 multi-speed trend rule is applied independently to actual CU and RB delivery contracts with equal risk budgets. The original so-called commodity notebooks actually reused IF/T inputs, so this strategy is labelled “公开数据代理版本 / public-data proxy version.” It is a valid new futures backtest, not evidence that the old commodity notebooks were strictly reproduced.

## Execution, daily settlement, and costs

The signal is frozen after day t close. On day t+1, the target can trade only at an official reported open with positive daily volume. At a rebalance or roll, the prior holding earns the move from prior settlement to current open, and the new holding earns the move from current open to current settlement. On unchanged holdings these components equal settlement-to-settlement P&L.

Commission and one-tick slippage are charged for every opened or closed contract. Rolls charge both closing and opening quantities. The ledger records gross P&L, commission, slippage, net P&L, margin, gross notional, positions, and transactions. Metrics are recalculated only from these generated ledgers with a zero risk-free rate for Sharpe.

Daily bars cannot establish tick-level queue priority or prove that an opening print was executable for arbitrary size. “Next open” here means an explicit daily-bar approximation backed by an official open and positive volume; it is not presented as a tick simulation.

