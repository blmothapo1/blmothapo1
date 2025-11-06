import json
import os
import time
from datetime import datetime, timedelta

import pandas as pd
import pytz
import yfinance as yf
from json import JSONDecodeError

# --- Optional external dependencies ---
try:
    from data_utils import get_candle_data
    from stock_api import (
        place_order, get_account, get_position, close_position,
        get_current_price
    )
    from daily_movers import get_dynamic_top_movers as get_daily_movers
    from strategy_logic import get_stock_signal
    from sentiment_filter import is_sentiment_favorable
    from telegram import send_telegram_message, send_telegram_photo
    from position_tracker import (
        track_new_position, update_position, reset_position,
        should_exit, get_peak_price
    )
    from chart_snapshot import capture_chart_snapshot
    from day_trade_tracker import has_hit_day_trade_limit, record_day_trade
    from chart_vision import analyze_candles
    from pnl_tracker import PnLTracker
    from order_utils import has_open_order
    from sector_strength import get_strong_sectors
    from premarket_scanner import get_premarket_gaps
    from pdt_guard import get_day_trades_left, save_pdt_status
except Exception:
    # When running the script outside of the full environment we may
    # not have all helper modules available. Provide stubs so the
    # script can still be executed for testing or development.
    def _stub(*args, **kwargs):
        return None
    place_order = get_account = get_position = close_position = _stub
    get_current_price = _stub
    get_daily_movers = get_stock_signal = is_sentiment_favorable = _stub
    send_telegram_message = send_telegram_photo = _stub
    track_new_position = update_position = reset_position = _stub
    should_exit = get_peak_price = _stub
    has_hit_day_trade_limit = record_day_trade = _stub
    analyze_candles = _stub
    PnLTracker = object
    has_open_order = _stub
    get_strong_sectors = get_premarket_gaps = _stub
    get_day_trades_left = save_pdt_status = _stub


TRAILING_STOP_PERCENT = 2.0
REENTRY_COOLDOWN_MINUTES = 15
STOPLOSS_COOLDOWN_MINUTES = 30
TRADE_LOG_CSV = "trade_log.csv"
MAX_RETRIES = 3
RETRY_INTERVAL_MINUTES = 5


def load_config(path: str = "config.json") -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file '{path}' not found")
    with open(path) as f:
        return json.load(f)


def log_trade(symbol: str, direction: str, entry: float, exit_price: float, result: str) -> None:
    """Append a trade to the CSV log."""
    row = {
        "timestamp": datetime.utcnow().isoformat(),
        "symbol": symbol,
        "direction": direction,
        "entry": entry,
        "exit": exit_price,
        "result": result,
    }
    file_exists = os.path.isfile(TRADE_LOG_CSV)
    with open(TRADE_LOG_CSV, "a", newline="") as f:
        writer = pd.DataFrame([row])
        if not file_exists:
            writer.to_csv(f, header=True, index=False)
        else:
            writer.to_csv(f, header=False, index=False)


def print_eod_summary() -> None:
    if not os.path.isfile(TRADE_LOG_CSV):
        print("No trades logged today.")
        return
    df = pd.read_csv(TRADE_LOG_CSV)
    today = datetime.utcnow().date().isoformat()
    df_today = df[df["timestamp"].str.startswith(today)]
    total = len(df_today)
    wins = (df_today["result"] == "win").sum()
    win_rate = (wins / total * 100) if total else 0
    pnl = (df_today["exit"].astype(float) - df_today["entry"].astype(float)).sum()
    print(f"EOD Summary: {total} trades | Win rate: {win_rate:.1f}% | PnL: ${pnl:.2f}")


# --- Data helpers ---

def robust_download(ticker: str, period: str, interval: str, retries: int = 3, delay: int = 2):
    for attempt in range(1, retries + 1):
        try:
            df = yf.download(ticker, period=period, interval=interval, auto_adjust=True, progress=False)
            if df is not None and not df.empty:
                return df
            else:
                print(f"⚠️ Skipping [{ticker}] due to bad Yahoo response (empty data, attempt {attempt}/{retries})")
        except JSONDecodeError:
            print(
                f"⚠️ Skipping [{ticker}] due to bad Yahoo response (JSON decode error, attempt {attempt}/{retries})"
            )
        except Exception as e:
            print(f"⚠️ {ticker}: Error loading data (attempt {attempt}/{retries}): {e}")
        if attempt < retries:
            time.sleep(delay)
    print(f"⚠️ Skipping [{ticker}] due to bad Yahoo response (all attempts failed)")
    return None


def safe_get_candle_data(ticker: str, interval: str = "5m", limit: int | None = None):
    df = robust_download(ticker, period="1d", interval=interval)
    return df


# --- Main trading loop ---

def run_bot() -> None:
    """Main entry point for the trading bot."""
    config = load_config()
    pnl_tracker = PnLTracker() if callable(PnLTracker) else PnLTracker
    mode = "scalp_mode"
    last_pdt_check = None
    retry_queue: dict[str, dict] = {}

    send_telegram_message("🚀 *CryptoMint is LIVE* and scanning.")
    print("📡 CryptoMint Stock Edition is online.")

    while True:
        try:
            now_mt = datetime.now(pytz.timezone("US/Mountain"))
            if now_mt.hour == 7 and 30 <= now_mt.minute < 45:
                print("⏳ Waiting for market to stabilize...")
                send_telegram_message("⏳ Waiting for market to stabilize...")
                time.sleep(60)
                continue

            now = datetime.now(pytz.UTC)
            if not last_pdt_check or (now - last_pdt_check).seconds > 120:
                day_trades_left = get_day_trades_left() or 0
                prev_mode = mode
                mode = "swing_mode" if day_trades_left <= 1 else "scalp_mode"
                if prev_mode != mode:
                    send_telegram_message(
                        f"⚠️ PDT mode switch: {prev_mode} → {mode}. Day trades left: {day_trades_left}"
                    )
                save_pdt_status(mode, day_trades_left)
                last_pdt_check = now

            for symbol in list(retry_queue.keys()):
                retry_data = retry_queue[symbol]
                time_since_last = datetime.now(pytz.UTC) - retry_data["last_attempt"]
                if retry_data["retries"] >= MAX_RETRIES:
                    del retry_queue[symbol]
                    continue
                if time_since_last < timedelta(minutes=RETRY_INTERVAL_MINUTES):
                    continue

                signal = retry_data["signal"]
                price = get_current_price(symbol)
                if price is None or (config["use_sentiment_filter"] and not is_sentiment_favorable(symbol)):
                    retry_data["retries"] += 1
                    retry_data["last_attempt"] = datetime.now(pytz.UTC)
                    continue
                if has_open_order(symbol):
                    send_telegram_message(f"⏳ Skipping *{symbol}* retry: Open order already exists.")
                    retry_data["retries"] += 1
                    retry_data["last_attempt"] = datetime.now(pytz.UTC)
                    continue
                qty = round(config["trade_amount_usd"] / price)
                if qty <= 0:
                    retry_data["retries"] += 1
                    retry_data["last_attempt"] = datetime.now(pytz.UTC)
                    continue
                place_order(symbol, qty, side="buy")
                track_new_position(symbol, price)
                send_telegram_message(
                    f"🔁 *Retry Buy Executed* for {symbol}\nQty: {qty} @ ${price:.2f}\n"
                    f"Confidence: {signal.get('confidence', 0.5)} | Reason: {signal.get('reason', '-')}"
                )
                del retry_queue[symbol]

                img_path = capture_chart_snapshot(symbol)
                if img_path:
                    send_telegram_photo(img_path, f"📸 *{symbol}* Entry Snapshot")

            now_et = datetime.now(pytz.timezone("America/New_York"))
            if now_et.weekday() >= 5 or not (now_et.hour > 9 or (now_et.hour == 9 and now_et.minute >= 30)) or (
                now_et.hour >= 16
            ):
                print("⏸️ Market is closed. Skipping trading logic.")
                time.sleep(600)
                continue

            universe = config.get("stocks_to_watch", [])

            premarket_gaps = get_premarket_gaps(universe, gap_threshold=2.0) or {}
            high_priority = set(premarket_gaps.keys())

            strong_sectors = get_strong_sectors() or []
            filtered_universe = []
            for symbol in universe:
                sector = None
                if sector is None or sector in strong_sectors:
                    filtered_universe.append(symbol)
            universe = filtered_universe

            for symbol in universe:
                try:
                    signal = get_stock_signal(symbol)
                    if not signal or not isinstance(signal, dict):
                        continue
                except Exception as e:
                    send_telegram_message(f"⚠️ *{symbol}* error: {e}")
                    continue

                if mode == "swing_mode":
                    if not (signal.get("confidence", 0) >= 0.9 and signal.get("timeframe", "") == "1d"):
                        continue

                price = get_current_price(symbol)
                if price is None:
                    continue

                position = get_position(symbol)
                if signal.get("buy") and not position:
                    if has_open_order(symbol):
                        continue
                    if has_hit_day_trade_limit():
                        continue
                    qty = round(config["trade_amount_usd"] / price)
                    place_order(symbol, qty, side="buy")
                    track_new_position(symbol, price)
                    record_day_trade(symbol, price, datetime.now(pytz.UTC))
                    send_telegram_message(
                        f"📈 BUY *{symbol}*\nQty: {qty} @ ${price:.2f}\n"
                        f"Confidence: {signal.get('confidence', 0.5)}"
                    )
                    log_trade(symbol, "long", price, None, "pending")
                elif position:
                    current_price = get_current_price(symbol)
                    if current_price is None:
                        continue
                    entry_price = float(position.get("avg_entry_price", 0))
                    qty = float(position.get("qty", 0))
                    gain_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price else 0
                    if should_exit(symbol, current_price, TRAILING_STOP_PERCENT):
                        close_position(symbol)
                        reset_position(symbol)
                        log_trade(
                            symbol,
                            "long",
                            entry_price,
                            current_price,
                            "win" if current_price > entry_price else "loss",
                        )
                        send_telegram_message(
                            f"💸 EXIT {symbol} \nPrice: ${current_price:.2f} | Gain: {gain_pct:.2f}%"
                        )
                    else:
                        update_position(symbol, current_price)

            if datetime.now().minute == 0:
                summary = pnl_tracker.get_summary() if hasattr(pnl_tracker, "get_summary") else {}
                realized = summary.get("realized", 0)
                unrealized = summary.get("unrealized", 0)
                print(f"💰 Realized PnL: ${realized:.2f} | Unrealized: ${unrealized:.2f}")

            now_et = datetime.now(pytz.timezone("America/New_York"))
            if now_et.hour == 16 and now_et.minute == 0:
                print_eod_summary()

            time.sleep(60)

        except Exception as e:
            print(f"⚠️ Top-level error: {e}")
            send_telegram_message(f"⚠️ Bot error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    try:
        account = get_account() or {}
        status = account.get("status", "unknown")
        print(f"👤 Alpaca Account Status: {status}")
    except Exception:
        print("👤 Alpaca Account Status: unavailable")
    run_bot()
