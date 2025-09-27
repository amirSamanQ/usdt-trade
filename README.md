# USDT↔TMN Arbitrage Trading Project

## Overview
This repository implements a full workflow for detecting and trading arbitrage opportunities between **Wallex (USDTTMN)** and **Nobitex (USDTIRT)**.  

The project is divided into three main parts:
1. **Backtesting Notebooks** – Simulation on both candle data and tick-level data.  
2. **Forward Trading Bot** – Live arbitrage execution using Wallex/Nobitex APIs.  
3. **Unified Exchange Module** – Clean wrapper for the APIs with only required functions.  

---

## Project Structure


---

## Backtests

### 1. Candle Backtest (`candle_backtest.ipynb`)
- Input data: 1-minute candles from Wallex & Nobitex.  
- Logic:  
  - `z = wlx - nbtx`  
  - If `z > upper_bound` → SELL USDT (convert to TMN).  
  - If `z < lower_bound` → BUY USDT (convert to USDT).  
- Tracks:  
  - Portfolio evolution  
  - Number of trades  
  - Relative performance vs. a **Buy & Hold** benchmark  

**Sample dataset (`candle_backtest`):**

| ts_main            | nbtx  | ts                | wlx   | diff | ratio       |
|--------------------|-------|------------------|-------|------|-------------|
| 8/18/2025 14:40    | 93438 | 8/18/2025 14:40  | 93117 | -321 | 0.996564567 |
| 8/18/2025 14:41    | 93362 | 8/18/2025 14:41  | 93148 | -214 | 0.997707847 |
| 8/18/2025 14:42    | 93362 | 8/18/2025 14:42  | 93145 | -217 | 0.997675714 |
| ...                | ...   | ...              | ...   | ...  | ...         |

---

### 2. Tick Backtest (`tick_backtest.ipynb`)
- Input data: tick-level snapshots of both orderbooks.  
- Features:  
  - Rolling bands (`mean ± K·std`) or static thresholds.  
  - Execution modes:  
    - **Taker** – market orders, always filled.  
    - **Mid** – orders at (bid+ask)/2, probabilistic fills.  
    - **Maker** – one-tick-better limit orders, probabilistic fills.  
  - Full trade log with balance evolution and performance metrics.  

**Sample dataset (`tick_backtest`):**

| ts_utc                  | y_bid | y_ask | y_mid   | y_bid_vol | y_ask_vol | x_bid | x_ask | x_mid | x_bid_vol | x_ask_vol | z   |
|--------------------------|-------|-------|---------|-----------|-----------|-------|-------|-------|-----------|-----------|-----|
| 2025-09-17T10:10:59.487  | 99200 | 99249 | 99224.5 | 17.13     | 294       | 99170 | 99230 | 99200 | 12.16     | 1857.75   | 24.5 |
| 2025-09-17T10:11:03.694  | 99200 | 99249 | 99224.5 | 30.19     | 289.01    | 99170 | 99230 | 99200 | 12.16     | 1842.75   | 24.5 |
| 2025-09-17T10:11:08.065  | 99200 | 99250 | 99225   | 30.19     | 1179.44   | 99170 | 99230 | 99200 | 12.16     | 1842.75   | 25   |
| ...                      | ...   | ...   | ...     | ...       | ...       | ...   | ...   | ...   | ...       | ...       | ... |

---

### 3. Tick Grid Backtest (`tick_grid_backtest.ipynb`)
- Performs grid search across:  
  - Window sizes  
  - K multipliers  
  - Execution modes (taker, mid, maker)  
  - Fill probabilities  
- Outputs:  
  - `results_raw.csv` → per replication  
  - `results_mean.csv` → grouped averages  

---

## Forward Trading (`usdt_trade.py`)
- Continuously monitors live prices from Wallex and Nobitex.  
- Maintains rolling/static bands.  
- Executes trades when spread crosses thresholds:  
  - **SELL USDT** when Wallex is overpriced.  
  - **BUY USDT** when Wallex is underpriced.  
- Features:  
  - Limit orders placed one tick better.  
  - Track & cancel if no longer top of book.  
  - Rotating tick logs (`ticks_1.csv`, `ticks_2.csv`, ...).  
  - Trade history saved in pickle.  

---

## Unified Exchange Module (`exchanges.py`)
- Minimal wrapper with only required functions:  
  - Wallex: `get_best_bid_ask`, `new_order`, `cancel_order_wallex`, `check_order`, `get_balance`.  
  - Nobitex: `get_nobitex_orderbook`.  

---

## Configuration
Example config file (`config.json.example`):

```json
{
  "USDT_TRADE": {
    "WALLEX_API_KEY": "YOUR_WALLEX_API_KEY_HERE",
    "NOBITEX_API_KEY": "YOUR_NOBITEX_API_KEY_HERE",

    "PAIR_WLX": "USDTTMN",
    "PAIR_NBX": "USDTIRT",
    "K": 2.0,
    "ROLLING": true,
    "ROLL_N": 20,
    "Z_MIN_SPACING_S": 20,
    "STATIC_LOWER": -100.0,
    "STATIC_UPPER": 100.0,
    "ORDER_QTY_USDT": 100,
    "SLEEP_LOOP": 5,
    "TRACK_POLL": 2,
    "TRADES_PKL": "trades.pkl",
    "TICKS_DIR": "ticks",
    "BASE_NAME": "ticks",
    "MAX_FILE_SIZE_MB": 5,
    "TMN_LOWER": 50000,
    "USDT_LOWER": 10,
    "BALANCE_PATH": null
  }
}
