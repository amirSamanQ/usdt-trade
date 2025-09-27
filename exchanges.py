# -*- coding: utf-8 -*-
"""
Unified Exchange Module (Wallex + Nobitex)
==========================================
Provides only the required functions for usdt_trade.py:
- Wallex: best bid/ask, order placement, cancel, order status, balances
- Nobitex: orderbook
"""

import requests
import time
import pandas as pd
from decimal import Decimal

# -------------------------------------------------------------------
# Wallex API
# -------------------------------------------------------------------
def get_quantity_precision(market: str, api_key: str) -> dict:
    """Get quantity and price precision for a Wallex market."""
    url = "https://api.wallex.ir/v1/markets"
    res = requests.get(url).json()["result"]["symbols"][market]
    return {"q": res["stepSize"], "p": res["tickSize"]}


def get_best_bid_ask(market: str, count: int, api_key: str):
    """Fetch best bid and ask for a Wallex market."""
    url = f"https://api.wallex.ir/v1/depth?symbol={market}"
    attempt = 0
    while attempt < 10:
        try:
            res = requests.get(url, timeout=10).json()
            break
        except:
            attempt += 1
            time.sleep(1.5)
    if attempt == 10:
        return "server_error"
    bids = [{"price": float(x["price"]), "vol": float(x["quantity"])} for x in res["result"]["bid"][:count]]
    asks = [{"price": float(x["price"]), "vol": float(x["quantity"])} for x in res["result"]["ask"][:count]]
    return {"bid": bids, "ask": asks}


def new_order(side: str, quantity: float, market: str, price: float, api_key: str) -> dict:
    """Place a Wallex limit order."""
    head = {"X-API-Key": api_key}
    url = "https://api.wallex.ir/v1/account/orders"
    data = {
        "symbol": market,
        "side": side,
        "type": "LIMIT",
        "quantity": quantity,
        "price": price,
    }
    return requests.post(url, headers=head, json=data).json()


def cancel_order_wallex(order_id: str, api_key: str) -> dict:
    """Cancel a Wallex order."""
    head = {"X-API-Key": api_key}
    url = f"https://api.wallex.ir/v1/account/orders/{order_id}"
    return requests.delete(url, headers=head).json()


def check_order(order_id: str, api_key: str) -> dict:
    """Check Wallex order status."""
    head = {"X-API-Key": api_key}
    url = f"https://api.wallex.ir/v1/account/orders/{order_id}"
    return requests.get(url, headers=head).json()


def get_balance(symbol: str, free: bool, api_key: str, balance_path: str = None) -> float:
    """
    Get Wallex balance.
    - If balance_path is provided: read balance from local pickle file.
    - Else: fetch from Wallex API.
    """
    if balance_path:
        try:
            blnc_data = pd.read_pickle(balance_path)
            res = blnc_data.get(symbol.upper())
            return float(res.get("free") if free else res.get("total"))
        except Exception:
            return 0.0

    url = "https://api.wallex.ir/v1/account/balances"
    head = {"X-API-Key": api_key}
    result = requests.get(url, headers=head).json()["result"]["balances"]
    if symbol in result:
        if free:
            return float(result[symbol]["value"]) - float(result[symbol]["locked"])
        return float(result[symbol]["value"])
    return 0.0


# -------------------------------------------------------------------
# Nobitex API
# -------------------------------------------------------------------
def get_nobitex_orderbook(market: str, depth: int, api_token: str) -> dict:
    """Fetch Nobitex orderbook for a market."""
    url = f"https://apiv2.nobitex.ir/v3/orderbook/{market.upper()}"
    headers = {"Authorization": f"Token {api_token}", "Content-Type": "application/json"}
    response = requests.get(url, headers=headers, timeout=7)
    response.raise_for_status()
    return response.json()
