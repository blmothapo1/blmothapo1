import time
import json
import warnings
from datetime import datetime
import os
from data_utils import get_candle_data
from stock_api import (
    place_order, get_account, get_position, close_position,
    get_current_price
)
from strategy_logic import get_stock_signal
from sentiment_filter import is_sentiment_favorable
from telegram import send_telegram_message
from position_tracker import (
    track_new_position, update_position, reset_position,
    should_exit, get_peak_price
)
from chart_snapshot import capture_chart_snapshot
from telegram import send_telegram_photo
from day_trade_tracker import (
    has_hit_day_trade_limit, record_day_trade
)
from chart_vision import analyze_candles
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import pandas as pd
from fastapi import FastAPI, BackgroundTasks, HTTPException
import logging
import concurrent.futures

try:
    import schedule  # type: ignore
except ImportError:
    import subprocess
    import sys
    print("[INFO] Installing 'schedule' package...")
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'schedule'])
    import schedule  # type: ignore

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.get("/")
def read_root():
    return {"status": "ok"}


@app.post("/run-bot/{user_id}")
def run_bot_endpoint(user_id: str, background_tasks: BackgroundTasks):
    raise HTTPException(status_code=400, detail="Bot only runs locally now. No Firestore config.")


@app.get("/health")
def health_check() -> dict:
    status = {"alpaca": False, "disk": False, "openai": False, "yfinance": False}
    try:
        acct = get_account()
        status["alpaca"] = acct is not None
    except Exception:
        status["alpaca"] = False
    try:
        with open("trade_memory.json", "r") as f:
            _ = json.load(f)
        status["disk"] = True
    except Exception:
        status["disk"] = False
    try:
        import openai
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        if OPENAI_API_KEY:
            openai.api_key = OPENAI_API_KEY
            openai.Engine.list()
            status["openai"] = True
    except Exception:
        status["openai"] = False
    try:
        import yfinance as yf
        test = yf.Ticker("AAPL").history(period="1d")
        status["yfinance"] = not test.empty
    except Exception:
        status["yfinance"] = False
    return {"status": status, "ok": all(status.values())}


stocks = []


def run_with_timeout(func, *args, timeout=10, default=None, **kwargs):
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            return future.result(timeout=timeout)
    except Exception as e:
        print(f"[TIMEOUT/ERROR] {func.__name__}: {e}")
        return default


def calculate_dynamic_qty(symbol, confidence, price, base_trade_amount):
    import math
    account = run_with_timeout(get_account, timeout=10, default=None)
    if account is None:
        print(f"⚠️ Could not fetch account info for {symbol}.")
        send_telegram_message(f"⚠️ Skipped *{symbol}*: Could not fetch account info.")
        return 0
    if price is None or isinstance(price, float) and (math.isnan(price) or price <= 0):
        print(f"⚠️ Skipping {symbol}: Invalid price ({price}) for entry.")
        send_telegram_message(f"⚠️ Skipped *{symbol}*: Invalid price ({price}) for entry.")
        return 0
    buying_power = float(account.get("buying_power", 0))
    confidence_scale = {1: 0.2, 2: 0.4, 3: 0.6, 4: 0.8, 5: 1.0}
    scale = confidence_scale.get(int(confidence * 5), 0.2)
    trade_amount = min(base_trade_amount * scale, buying_power)
    if math.isnan(trade_amount) or trade_amount < price:
        print(f"⚠️ Skipping {symbol}: Not enough funds for entry.")
        send_telegram_message(f"⚠️ Skipped *{symbol}*: Not enough funds for entry.")
        return 0
    qty = round(trade_amount / price)
    return max(qty, 1)


def record_trade_memory(ticker, signal, action, qty, price, outcome=None):
    try:
        with open("trade_memory.json", "r") as f:
            trades = json.load(f)
    except Exception:
        trades = []
    trade_entry = {
        "time": datetime.now().isoformat(),
        "ticker": ticker,
        "signal_source": signal.get("reason", "unknown"),
        "sentiment": "N/A",
        "confidence": signal.get("confidence", 0),
        "outcome": outcome if outcome is not None else 0,
        "extra": {
            "action": action,
            "qty": qty,
            "price": price,
        },
    }
    trades.append(trade_entry)
    with open("trade_memory.json", "w") as f:
        json.dump(trades, f, indent=2)


def run_bot_with_config(config):
    global stocks
    if config.get("use_daily_movers", False):
        try:
            from daily_movers import get_daily_movers
            movers = get_daily_movers()
            if movers and len(movers) > 0:
                stocks = movers
                send_telegram_message(
                    f"🟢 Trading universe for today (daily movers): {', '.join(stocks)}"
                )
                print(
                    f"[INFO] Trading universe for today (daily movers): {', '.join(stocks)}"
                )
            else:
                stocks = config["stocks_to_watch"]
                send_telegram_message(
                    "⚠️ Fallback: Using static stocks list. Movers fetch failed or empty."
                )
                print(
                    "[WARN] Fallback: Using static stocks list. Movers fetch failed or empty."
                )
        except Exception as e:
            stocks = config["stocks_to_watch"]
            send_telegram_message(
                f"⚠️ Fallback: Using static stocks list due to error: {e}"
            )
            print(f"[WARN] Fallback: Using static stocks list due to error: {e}")
    else:
        stocks = config["stocks_to_watch"]

    print(f"[DEBUG] config loaded: {json.dumps(config, indent=2)}")
    print(f"[DEBUG] stocks list: {stocks}")
    if not stocks or len(stocks) == 0:
        send_telegram_message(
            "🛑 No tickers to trade today! Movers and static list are both empty."
        )
        print(
            "[FATAL] No tickers to trade today! Movers and static list are both empty."
        )
        return

    send_telegram_message(f"🟢 Trading universe for today: {', '.join(stocks)}")
    print(f"[INFO] Trading universe for today: {', '.join(stocks)}")
    BASE_TRADE_AMOUNT = config["trade_amount_usd"]
    USE_SENTIMENT = config["use_sentiment_filter"]
    TRAILING_STOP_PERCENT = config.get("trailing_stop_pct", 2.0)
    API_KEY = config["alpaca"]["api_key"]
    API_SECRET = config["alpaca"]["api_secret"]
    BASE_URL = config["alpaca"]["base_url"]

    print("📡 CryptoMint Stock Edition is online.")
    send_telegram_message("🚀 *CryptoMint is LIVE* and scanning.")

    while True:
        loop_summary = []
        print(f"[LOOP] Starting trading loop for tickers: {stocks}")
        for symbol in stocks:
            print(f"[LOOP] Processing symbol: {symbol}")
            try:
                signal = get_stock_signal(symbol)
                if not isinstance(signal, dict):
                    reason = f"Signal not a dict. Signal: {signal}"
                    send_telegram_message(f"[SKIP] {symbol}: {reason}")
                    loop_summary.append({"symbol": symbol, "action": "SKIP", "reason": reason})
                    continue
                if "buy" not in signal:
                    reason = f"No 'buy' key in signal. Signal: {signal}"
                    send_telegram_message(f"[SKIP] {symbol}: {reason}")
                    loop_summary.append({"symbol": symbol, "action": "SKIP", "reason": reason})
                    continue
                if "confidence" not in signal:
                    reason = f"No 'confidence' key in signal. Signal: {signal}"
                    send_telegram_message(f"[SKIP] {symbol}: {reason}")
                    loop_summary.append({"symbol": symbol, "action": "SKIP", "reason": reason})
                    continue
                position = get_position(symbol)
            except Exception as e:
                reason = f"Error: {e}"
                send_telegram_message(f"⚠️ {symbol} error: {e}")
                loop_summary.append({"symbol": symbol, "action": "ERROR", "reason": str(e)})
                continue
            try:
                df = get_candle_data(symbol)
                vision = analyze_candles(df)
                signal["vision_patterns"] = vision.get("engulfing", "none")
                signal["vision_trend"] = vision.get("trend", "unknown")
                try:
                    chart_path = capture_chart_snapshot(symbol)
                    send_telegram_photo(chart_path, caption=f"{symbol} chart snapshot")
                except Exception:
                    pass
            except Exception:
                signal["vision_patterns"] = []
                signal["vision_trend"] = "unknown"

            if signal["buy"] and not position:
                if USE_SENTIMENT and not is_sentiment_favorable(symbol):
                    reason = f"Blocked by sentiment: {symbol}"
                    send_telegram_message(f"[SKIP] {reason}")
                    loop_summary.append({"symbol": symbol, "action": "SKIP", "reason": reason})
                    continue
                if has_hit_day_trade_limit():
                    reason = f"PDT protection: Cannot buy {symbol} today."
                    send_telegram_message(f"[SKIP] {reason}")
                    loop_summary.append({"symbol": symbol, "action": "SKIP", "reason": reason})
                    continue
                price = get_current_price(symbol)
                if price is None:
                    reason = "No price data."
                    send_telegram_message(f"[SKIP] {symbol}: {reason}")
                    loop_summary.append({"symbol": symbol, "action": "SKIP", "reason": reason})
                    continue
                qty = calculate_dynamic_qty(symbol, signal.get("confidence", 0.5), price, BASE_TRADE_AMOUNT)
                if qty == 0:
                    reason = "Not enough funds for entry."
                    send_telegram_message(f"[SKIP] {symbol}: {reason}")
                    loop_summary.append({"symbol": symbol, "action": "SKIP", "reason": reason})
                    continue
                response = place_order(symbol, max(qty, 1), side="buy")
                track_new_position(symbol, price)
                record_day_trade(symbol, price, datetime.now())
                record_trade_memory(symbol, signal, "buy", max(qty, 1), price)
                send_telegram_message(
                    f"BUY {symbol}\nQty: {max(qty, 1)} @ ${price if price else 'N/A'}\n"
                    f"Confidence: {signal.get('confidence', 0.5)} | Reason: {signal.get('reason', '-')}\n"
                    f"Trend: {signal['vision_trend']} | Patterns: {signal['vision_patterns'] or 'None'}"
                )
                loop_summary.append({"symbol": symbol, "action": "TRADED", "reason": "BUY", "qty": max(qty, 1), "price": price})
            elif position:
                current_price = get_current_price(symbol)
                if current_price is None:
                    reason = "No current price for exit."
                    send_telegram_message(f"[SKIP] {symbol}: {reason}")
                    loop_summary.append({"symbol": symbol, "action": "SKIP", "reason": reason})
                    continue
                entry_price = float(position.get("avg_entry_price", 0))
                qty = position.get("qty", 0)
                gain_pct = ((current_price - entry_price) / entry_price) * 100
                if gain_pct >= 10:
                    response = close_position(symbol)
                    if response.get("status", "") == "filled":
                        reset_position(symbol)
                        record_trade_memory(symbol, signal, "sell", qty, current_price, gain_pct)
                        send_telegram_message(
                            f"{symbol}: Hard take profit exit at +{gain_pct:.2f}% (>=10%)."
                        )
                        loop_summary.append({"symbol": symbol, "action": "TRADED", "reason": "SELL (hard TP)", "qty": qty, "price": current_price})
                    continue
                if gain_pct >= 5 and not position.get("partial_taken", False) and qty > 1:
                    half_qty = max(int(qty // 2), 1)
                    response = place_order(symbol, half_qty, side="sell")
                    if response.get("status", "") == "filled":
                        position["partial_taken"] = True
                        record_trade_memory(symbol, signal, "sell", half_qty, current_price, gain_pct)
                        send_telegram_message(
                            f"{symbol}: Partial take profit (half position) at +{gain_pct:.2f}%."
                        )
                        loop_summary.append({"symbol": symbol, "action": "TRADED", "reason": "SELL (partial TP)", "qty": half_qty, "price": current_price})
        summary_lines = []
        for entry in loop_summary:
            if entry["action"] == "TRADED":
                summary_lines.append(
                    f"✅ {entry['symbol']}: {entry['reason']} Qty: {entry.get('qty', '-')}" +
                    f", Price: {entry.get('price', '-') }"
                )
            elif entry["action"] == "SKIP":
                summary_lines.append(f"⏭️ {entry['symbol']}: {entry['reason']}")
            elif entry["action"] == "ERROR":
                summary_lines.append(f"❌ {entry['symbol']}: {entry['reason']}")
        summary_text = "\n".join(summary_lines) if summary_lines else "No actions taken."
        send_telegram_message(
            f"\n=== Trading Loop Summary ===\n" + summary_text + "\n===========================\n"
        )
        time.sleep(2)


if __name__ == "__main__":
    config = {
        "alpaca": {
            "api_key": "AKEDNX0G1ZD3081YJXN2",
            "api_secret": "ctHOOkXrTbIZBtxmZiwZ7LQVHCLjbZHCByKz5RUl",
            "base_url": "https://paper-api.alpaca.markets",
        },
        "stocks_to_watch": [
            "AAPL",
            "MSFT",
            "NVDA",
            "GOOG",
            "META",
            "TSLA",
            "XLF",
            "INKT",
            "HIMS",
            "BTC",
            "ETH",
            "SPY",
            "QQQ",
            "ABVE",
            "BABA",
            "AMZN",
            "NFLX",
            "DIS",
            "PYPL",
            "SNAP",
            "SDST",
            "SOFI",
            "AMD",
            "SMR",
            "MP",
        ],
        "trade_amount_usd": 1000,
        "use_sentiment_filter": False,
        "trailing_stop_pct": 2.0,
        "use_daily_movers": False,
    }
    run_bot_with_config(config)
