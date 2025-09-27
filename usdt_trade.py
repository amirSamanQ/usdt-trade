# -*- coding: utf-8 -*-
"""
USDT↔TMN Arbitrage Forward Trading
==================================
- Spread = Wallex mid - Nobitex mid
- Signals: buy/sell based on rolling/static bands
- Execution: limit one-tick-better, track and cancel logic
- All ticks logged into rotating CSV files
"""

import sys, io, os, time, json, traceback
from datetime import datetime, timezone
from collections import deque
import pandas as pd

# Fix UTF-8 print for Supervisor (for Persian logs)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

print("📌 Program started")

# Import unified exchange module
import exchanges as ex

# ---------------- Load Config ----------------
def load_config(path="config.json"):
    with open(path, "r") as f:
        return json.load(f)

CONFIG_FILE = os.environ.get("CONFIG_FILE", "config.json")
cfg = load_config(CONFIG_FILE)["USDT_TRADE"]
print("⚙️ Config Loaded:\n", cfg)

# Shortcuts
WALLEX_KEY = cfg["WALLEX_API_KEY"]
NOBITEX_KEY = cfg["NOBITEX_API_KEY"]

PAIR_WLX = cfg["PAIR_WLX"]
PAIR_NBX = cfg["PAIR_NBX"]
K = cfg["K"]
ROLLING = cfg["ROLLING"]
ROLL_N = cfg["ROLL_N"]
Z_MIN_SPACING_S = cfg["Z_MIN_SPACING_S"]
STATIC_LOWER = cfg["STATIC_LOWER"]
STATIC_UPPER = cfg["STATIC_UPPER"]
ORDER_QTY_USDT = cfg["ORDER_QTY_USDT"]
SLEEP_LOOP = cfg["SLEEP_LOOP"]
TRACK_POLL = cfg["TRACK_POLL"]
TRADES_PKL = cfg["TRADES_PKL"]
TICKS_DIR = cfg["TICKS_DIR"]
BASE_NAME = cfg["BASE_NAME"]
MAX_FILE_SIZE_MB = cfg["MAX_FILE_SIZE_MB"]
TMN_LOWER = cfg["TMN_LOWER"]
USDT_LOWER = cfg["USDT_LOWER"]
BALANCE_PATH = cfg.get("BALANCE_PATH")

# ---------------- Helpers ----------------
def one_tick(symbol: str) -> float:
    """Return one tick size for a symbol."""
    p = ex.get_quantity_precision(symbol, WALLEX_KEY)["p"]
    return 1.0 / (10**p) if p > 0 else 1.0

def wallex_top(symbol: str):
    """Get Wallex top bid/ask and mid price."""
    d = ex.get_best_bid_ask(symbol, count=1, api_key=WALLEX_KEY)
    bid = float(d["bid"][0]["price"]); ask = float(d["ask"][0]["price"])
    bvol = float(d["bid"][0]["vol"]); avol = float(d["ask"][0]["vol"])
    mid = (bid + ask) / 2.0
    return bid, ask, mid, bvol, avol

def nobitex_top(market: str):
    """Get Nobitex top bid/ask and mid price."""
    ob = ex.get_nobitex_orderbook(market, depth=1, api_token=NOBITEX_KEY)
    bid = float(ob["bids"][0][0]); ask = float(ob["asks"][0][0])
    bvol = float(ob["bids"][0][1]); avol = float(ob["asks"][0][1])
    mid = (bid + ask) / 2.0
    return bid, ask, mid, bvol, avol

# ---------------- File Rotation ----------------
def current_csv_path(base_dir=TICKS_DIR, base_name=BASE_NAME, max_mb=MAX_FILE_SIZE_MB):
    """Return the current CSV file path for tick logging (rotate if size exceeded)."""
    os.makedirs(base_dir, exist_ok=True)
    idx = 1
    while True:
        path = os.path.join(base_dir, f"{base_name}_{idx}.csv")
        if not os.path.exists(path) or (os.path.getsize(path) / (1024 * 1024) < max_mb):
            return path
        idx += 1

def append_tick(row: dict):
    """Append a tick row into rotating CSV file."""
    path = current_csv_path()
    df = pd.DataFrame([row])
    header = not os.path.exists(path) or os.path.getsize(path) == 0
    df.to_csv(path, mode="a", index=False, header=header, encoding="utf-8")
    print(f"📝 Tick appended to {path}")

# ---------------- Trading Helpers ----------------
def clamp_buy(bid, ask, tick):  
    return max(min(bid + tick, ask - tick), tick)

def clamp_sell(bid, ask, tick): 
    return max(min(ask - tick, ask), bid + tick)

def save_trade(side, price, qty, extra=None):
    """Save executed trade into pickle log."""
    rec = {
        "side": side,
        "price": float(price),
        "qty": float(qty),
        "ts": datetime.now(timezone.utc).isoformat(),
        **(extra or {})
    }
    try:
        lst = pd.read_pickle(TRADES_PKL) if os.path.exists(TRADES_PKL) else []
        if not isinstance(lst, list):
            lst = []
        lst.append(rec)
        pd.to_pickle(lst, TRADES_PKL)
        print(f"💾 Trade saved: {rec}")
    except Exception as e:
        print("⚠️ save_trade:", e)

def track_until_not_top_and_cancel(side, my_price, symbol):
    """Track order until no longer top, then cancel."""
    print(f"🔎 Tracking order side={side}, price={my_price}")
    while True:
        try:
            w_bid, w_ask, *_ = wallex_top(symbol)
            top = w_bid if side == "buy" else w_ask
            if abs(top - my_price) > 1e-9:
                print("📉 No longer top, will cancel")
                break
            time.sleep(TRACK_POLL)
        except Exception:
            break
    return True

def cancel_and_check(order_id, side, min_notional_tmn=50_000):
    """Cancel Wallex order and check if partially filled."""
    try:
        ex.cancel_order_wallex(order_id, WALLEX_KEY)
        print(f"⚠️ Cancel sent for order {order_id}")
    except Exception as e:
        print("⚠️ cancel:", e)
    try:
        st = ex.check_order(order_id, WALLEX_KEY)
        res = st.get("result", {})
        ex_q = float(res.get("executedQty", 0.0))
        ex_v = float(res.get("executedSum", 0.0))
        if ex_v > min_notional_tmn and ex_q > 0:
            px = float(res.get("executedPrice", 0.0)) or 0.0
            save_trade(side, px, ex_q, extra={"orderId": order_id, "val_tmn": ex_v})
            print(f"✅ FILLED {side}: qty={ex_q} val={int(ex_v)}")
        else:
            print(f"🚫 Not filled: order {order_id}")
    except Exception as e:
        print("⚠️ check_order:", e)

def place_limit_and_track(side, price, qty, symbol):
    """Place Wallex limit order, track it and cancel if needed."""
    try:
        print(f"📤 Placing {side.upper()} order: qty={qty} @ {price}")
        r = ex.new_order(side=side, quantity=qty, market=symbol, price=price, api_key=WALLEX_KEY)
        if not r.get("success"):
            print(f"❌ Order failed: {r}")
            return
        oid = r["result"]["clientOrderId"]
        track_until_not_top_and_cancel(side, price, symbol)
        cancel_and_check(oid, side)
    except Exception as e:
        print("⚠️ place/track:", e)
        traceback.print_exc()

# ---------------- Main Loop ----------------
def main():
    tick = one_tick(PAIR_WLX)
    zs = deque(maxlen=ROLL_N if ROLLING else 1)
    last_z_ts = 0.0
    print("▶️ Main loop started...")

    while True:
        loop_ts = time.time()
        try:
            # 1) Prices
            w_bid, w_ask, w_mid, w_bvol, w_avol = wallex_top(PAIR_WLX)
            x_bid, x_ask, x_mid, x_bvol, x_avol = nobitex_top(PAIR_NBX)
            z = w_mid - x_mid
            print(f"[Z] {datetime.now(timezone.utc).isoformat()} | w_mid={w_mid:.2f} | x_mid={x_mid:.2f} | z={z:.2f}")

            # 2) Save tick
            append_tick({
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "y_bid": w_bid, "y_ask": w_ask, "y_mid": w_mid,
                "y_bid_vol": w_bvol, "y_ask_vol": w_avol,
                "x_bid": x_bid, "x_ask": x_ask, "x_mid": x_mid,
                "x_bid_vol": x_bvol, "x_ask_vol": x_avol,
                "z": z
            })

            # 3) Rolling gating
            if ROLLING and (loop_ts - last_z_ts >= Z_MIN_SPACING_S):
                zs.append(z)
                last_z_ts = loop_ts

            # 4) Bands
            have_roll = (ROLLING and len(zs) == ROLL_N)
            if have_roll:
                s = pd.Series(zs)
                mean, std = s.mean(), s.std(ddof=1) or 0.0
                upper, lower = mean + K * std, mean - K * std
                mode = "rolling"
            else:
                upper, lower = STATIC_UPPER, STATIC_LOWER
                mode = "static"
            print(f"📊 Bands {mode}: LB={lower:.2f}, UB={upper:.2f}, n={len(zs)}")

            # 5) Balances
            usdt_free = ex.get_balance("USDT", free=True, api_key=WALLEX_KEY, balance_path=BALANCE_PATH)
            tmn_free  = ex.get_balance("TMN",  free=True, api_key=WALLEX_KEY, balance_path=BALANCE_PATH)
            print(f"💰 Balances: USDT={usdt_free:.2f}, TMN={tmn_free:.0f}")

            # 6) Signals
            if z > upper:
                print("🔴 SELL signal")
                if usdt_free < USDT_LOWER:
                    print("⛔ Skip SELL: not enough USDT")
                else:
                    px = clamp_sell(w_bid, w_ask, tick)
                    qty = min(ORDER_QTY_USDT, usdt_free)
                    if qty > 0.5:
                        place_limit_and_track("sell", px, qty, PAIR_WLX)

            elif z < lower:
                print("🟢 BUY signal")
                if tmn_free < TMN_LOWER:
                    print("⛔ Skip BUY: not enough TMN")
                else:
                    px = clamp_buy(w_bid, w_ask, tick)
                    qty = min(ORDER_QTY_USDT, tmn_free / px)
                    if qty > 0:
                        place_limit_and_track("buy", px, qty, PAIR_WLX)

        except Exception as e:
            print("⚠️ loop:", e)
            traceback.print_exc()

        time.sleep(SLEEP_LOOP)


if __name__ == "__main__":
    main()
