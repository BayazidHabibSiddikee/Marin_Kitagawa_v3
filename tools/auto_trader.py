#!/usr/bin/env python3
"""
Auto Trading Bot — Math-based Profit/Loss Targeting + New Crypto Alerts
Features:
  - Auto buy then auto sell at +2% / +5% profit OR stop-loss at -2% / -5%
  - Monitors price every few seconds
  - Detects newly listed coins on Binance and notifies via Telegram
  - All activity reported to your Telegram
"""

import os
import asyncio
import logging
import time
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters,
)

# ─────────────────────────────────────────────
#  CONFIG (from .env)
# ─────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

TELEGRAM_BOT_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USER_ID        = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
BINANCE_API_KEY         = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET      = os.getenv("BINANCE_API_SECRET", "")
USE_TESTNET             = os.getenv("USE_TESTNET", "false").lower() == "true"

# How often to check prices (seconds)
PRICE_CHECK_INTERVAL    = 5

# How often to check for new coins (seconds)
NEW_COIN_CHECK_INTERVAL = 60

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  BINANCE CLIENT
# ─────────────────────────────────────────────
def get_client() -> Client:
    return Client(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=USE_TESTNET)

# ─────────────────────────────────────────────
#  ACTIVE TRADES STORE
#  { symbol: { buy_price, quantity, take_profit_pct, stop_loss_pct, order_id } }
# ─────────────────────────────────────────────
active_trades: dict = {}

# Known symbols for new-coin detection
known_symbols: set = set()

# ─────────────────────────────────────────────
#  CONVERSATION STATES
# ─────────────────────────────────────────────
(
    MAIN_MENU,
    ENTER_SYMBOL,
    ENTER_QUANTITY,
    ENTER_TAKE_PROFIT,
    ENTER_STOP_LOSS,
    CONFIRM_TRADE,
) = range(6)

# ─────────────────────────────────────────────
#  SECURITY
# ─────────────────────────────────────────────
def restricted(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        uid = update.effective_user.id
        if TELEGRAM_USER_ID != 0 and uid != TELEGRAM_USER_ID:
            await update.effective_message.reply_text("⛔ Unauthorized.")
            return ConversationHandler.END
        return await func(update, context, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def fmt(v) -> str:
    return f"{float(v):,.6f}".rstrip("0").rstrip(".")

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def calc_targets(buy_price: float, tp_pct: float, sl_pct: float):
    take_profit = round(buy_price * (1 + tp_pct / 100), 8)
    stop_loss   = round(buy_price * (1 - sl_pct / 100), 8)
    return take_profit, stop_loss

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Auto Trade",    callback_data="start_trade")],
        [InlineKeyboardButton("📊 Active Trades",       callback_data="active_trades")],
        [InlineKeyboardButton("🛑 Stop a Trade",        callback_data="stop_trade")],
        [InlineKeyboardButton("💰 Balance",             callback_data="balance")],
        [InlineKeyboardButton("🔔 New Coin Alerts: ON", callback_data="toggle_alerts")],
    ])

# ─────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────
@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    env = "🧪 TESTNET" if USE_TESTNET else "🔴 LIVE"
    if "alerts_enabled" not in context.bot_data:
        context.bot_data["alerts_enabled"] = True

    await update.message.reply_text(
        f"⚡ *Auto Trader Bot* ({env})\n\n"
        f"This bot watches prices and auto-sells when your profit/loss target is hit.\n\n"
        f"Choose an action:",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )
    return MAIN_MENU

# ─────────────────────────────────────────────
#  BALANCE
# ─────────────────────────────────────────────
@restricted
async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("⏳ Fetching balance...")
    try:
        client = get_client()
        balances = [
            b for b in client.get_account()["balances"]
            if float(b["free"]) > 0 or float(b["locked"]) > 0
        ]
        lines = ["💼 *Balances:*\n"] + [
            f"• *{b['asset']}*  Free: `{fmt(b['free'])}`  Locked: `{fmt(b['locked'])}`"
            for b in balances
        ] if balances else ["No non-zero balances found."]
        text = "\n".join(lines)
    except BinanceAPIException as e:
        text = f"❌ {e.message}"
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    return MAIN_MENU

# ─────────────────────────────────────────────
#  ACTIVE TRADES VIEW
# ─────────────────────────────────────────────
@restricted
async def view_active_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not active_trades:
        text = "📊 No active trades running."
    else:
        lines = ["📊 *Active Trades:*\n"]
        for sym, t in active_trades.items():
            tp, sl = calc_targets(t["buy_price"], t["take_profit_pct"], t["stop_loss_pct"])
            try:
                price = float(get_client().get_symbol_ticker(symbol=sym)["price"])
                pnl_pct = ((price - t["buy_price"]) / t["buy_price"]) * 100
                pnl_str = f"{pnl_pct:+.2f}%"
            except Exception:
                pnl_str = "N/A"
            lines.append(
                f"*{sym}*\n"
                f"  Buy: `{fmt(t['buy_price'])}` | Qty: `{t['quantity']}`\n"
                f"  🎯 Take Profit: `{fmt(tp)}` (+{t['take_profit_pct']}%)\n"
                f"  🛑 Stop Loss:   `{fmt(sl)}` (-{t['stop_loss_pct']}%)\n"
                f"  📈 Current PnL: `{pnl_str}`\n"
            )
        text = "\n".join(lines)
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    return MAIN_MENU

# ─────────────────────────────────────────────
#  STOP A TRADE
# ─────────────────────────────────────────────
@restricted
async def stop_trade_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not active_trades:
        await q.edit_message_text("No active trades to stop.", reply_markup=main_menu_keyboard())
        return MAIN_MENU
    buttons = [
        [InlineKeyboardButton(f"🛑 Stop {sym}", callback_data=f"stop_{sym}")]
        for sym in active_trades
    ]
    buttons.append([InlineKeyboardButton("« Back", callback_data="back")])
    await q.edit_message_text("Choose trade to stop:", reply_markup=InlineKeyboardMarkup(buttons))
    return MAIN_MENU

@restricted
async def stop_specific_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    sym = q.data.replace("stop_", "")
    if sym in active_trades:
        del active_trades[sym]
        await q.edit_message_text(f"🛑 Stopped monitoring *{sym}*.", parse_mode="Markdown",
                                  reply_markup=main_menu_keyboard())
    else:
        await q.edit_message_text("Trade not found.", reply_markup=main_menu_keyboard())
    return MAIN_MENU

# ─────────────────────────────────────────────
#  TOGGLE NEW COIN ALERTS
# ─────────────────────────────────────────────
@restricted
async def toggle_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.bot_data["alerts_enabled"] = not context.bot_data.get("alerts_enabled", True)
    status = "ON ✅" if context.bot_data["alerts_enabled"] else "OFF ❌"
    await q.edit_message_text(f"🔔 New coin alerts turned *{status}*", parse_mode="Markdown",
                              reply_markup=main_menu_keyboard())
    return MAIN_MENU

# ─────────────────────────────────────────────
#  START AUTO TRADE FLOW
# ─────────────────────────────────────────────
@restricted
async def begin_trade_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "🚀 *New Auto Trade Setup*\n\nStep 1/4 — Enter the trading pair:\n"
        "Example: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`",
        parse_mode="Markdown",
    )
    return ENTER_SYMBOL

@restricted
async def receive_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = update.message.text.strip().upper()
    # Validate symbol exists
    try:
        price = float(get_client().get_symbol_ticker(symbol=symbol)["price"])
        context.user_data["symbol"]    = symbol
        context.user_data["cur_price"] = price
        await update.message.reply_text(
            f"✅ *{symbol}* — Current price: `{fmt(price)}`\n\n"
            f"Step 2/4 — Enter quantity to buy:\nExample: `0.01`",
            parse_mode="Markdown",
        )
        return ENTER_QUANTITY
    except BinanceAPIException:
        await update.message.reply_text(f"❌ Symbol `{symbol}` not found. Try again:",
                                        parse_mode="Markdown")
        return ENTER_SYMBOL

@restricted
async def receive_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        qty = float(update.message.text.strip())
        assert qty > 0
        context.user_data["quantity"] = qty
    except (ValueError, AssertionError):
        await update.message.reply_text("⚠️ Invalid. Enter a positive number:")
        return ENTER_QUANTITY

    await update.message.reply_text(
        "Step 3/4 — Take Profit %\n\n"
        "Enter profit % to auto-sell at. Examples:\n"
        "`2` = sell when +2% profit\n"
        "`5` = sell when +5% profit",
        parse_mode="Markdown",
    )
    return ENTER_TAKE_PROFIT

@restricted
async def receive_take_profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        tp = float(update.message.text.strip().replace("%", ""))
        assert 0 < tp <= 100
        context.user_data["take_profit_pct"] = tp
    except (ValueError, AssertionError):
        await update.message.reply_text("⚠️ Invalid. Enter a number like `2` or `5`:")
        return ENTER_TAKE_PROFIT

    await update.message.reply_text(
        "Step 4/4 — Stop Loss %\n\n"
        "Enter loss % to auto-sell at to cut losses. Examples:\n"
        "`2` = sell when -2% loss\n"
        "`5` = sell when -5% loss",
        parse_mode="Markdown",
    )
    return ENTER_STOP_LOSS

@restricted
async def receive_stop_loss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sl = float(update.message.text.strip().replace("%", ""))
        assert 0 < sl <= 100
        context.user_data["stop_loss_pct"] = sl
    except (ValueError, AssertionError):
        await update.message.reply_text("⚠️ Invalid. Enter a number like `2` or `5`:")
        return ENTER_STOP_LOSS

    sym   = context.user_data["symbol"]
    qty   = context.user_data["quantity"]
    tp    = context.user_data["take_profit_pct"]
    sl    = context.user_data["stop_loss_pct"]
    price = context.user_data["cur_price"]

    tp_price = round(price * (1 + tp / 100), 8)
    sl_price = round(price * (1 - sl / 100), 8)
    cost     = round(price * qty, 4)

    await update.message.reply_text(
        f"📋 *Order Summary*\n\n"
        f"Pair:         `{sym}`\n"
        f"Quantity:     `{qty}`\n"
        f"Buy at:       `{fmt(price)}` (market)\n"
        f"Est. Cost:    `~{cost} USDT`\n\n"
        f"🎯 Take Profit: `{fmt(tp_price)}` (+{tp}%)\n"
        f"🛑 Stop Loss:   `{fmt(sl_price)}` (-{sl}%)\n\n"
        f"Confirm trade?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Buy Now", callback_data="confirm_yes"),
             InlineKeyboardButton("❌ Cancel",  callback_data="confirm_no")],
        ]),
    )
    return CONFIRM_TRADE

@restricted
async def confirm_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "confirm_no":
        context.user_data.clear()
        await q.edit_message_text("❌ Trade cancelled.", reply_markup=main_menu_keyboard())
        return MAIN_MENU

    sym = context.user_data["symbol"]
    qty = context.user_data["quantity"]
    tp  = context.user_data["take_profit_pct"]
    sl  = context.user_data["stop_loss_pct"]

    await q.edit_message_text(f"⏳ Placing market buy for *{sym}*...", parse_mode="Markdown")

    try:
        client = get_client()
        order  = client.order_market_buy(symbol=sym, quantity=qty)

        # Get actual fill price
        fills     = order.get("fills", [])
        buy_price = (
            sum(float(f["price"]) * float(f["qty"]) for f in fills)
            / sum(float(f["qty"]) for f in fills)
            if fills else float(get_client().get_symbol_ticker(symbol=sym)["price"])
        )

        tp_price, sl_price = calc_targets(buy_price, tp, sl)

        active_trades[sym] = {
            "buy_price":       buy_price,
            "quantity":        qty,
            "take_profit_pct": tp,
            "stop_loss_pct":   sl,
            "order_id":        order.get("orderId"),
            "started_at":      now_str(),
        }

        await q.edit_message_text(
            f"✅ *Bought {sym}!*\n\n"
            f"Fill price:     `{fmt(buy_price)}`\n"
            f"Quantity:       `{qty}`\n"
            f"🎯 Auto-sell at: `{fmt(tp_price)}` (+{tp}%)\n"
            f"🛑 Auto-sell at: `{fmt(sl_price)}` (-{sl}%)\n\n"
            f"_Bot is now watching the price..._",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    except BinanceAPIException as e:
        await q.edit_message_text(f"❌ Buy failed: {e.message}", reply_markup=main_menu_keyboard())

    context.user_data.clear()
    return MAIN_MENU

# ─────────────────────────────────────────────
#  BACKGROUND: PRICE MONITOR
# ─────────────────────────────────────────────
async def price_monitor_loop(bot: Bot):
    """Runs in background — checks prices and auto-sells when targets hit."""
    logger.info("Price monitor started.")
    while True:
        await asyncio.sleep(PRICE_CHECK_INTERVAL)
        if not active_trades:
            continue

        client = get_client()
        for sym in list(active_trades.keys()):
            trade = active_trades[sym]
            try:
                price     = float(client.get_symbol_ticker(symbol=sym)["price"])
                buy_price = trade["buy_price"]
                qty       = trade["quantity"]
                tp_pct    = trade["take_profit_pct"]
                sl_pct    = trade["stop_loss_pct"]
                tp_price, sl_price = calc_targets(buy_price, tp_pct, sl_pct)
                pnl_pct   = ((price - buy_price) / buy_price) * 100

                hit_tp = price >= tp_price
                hit_sl = price <= sl_price

                if hit_tp or hit_sl:
                    reason     = "🎯 TAKE PROFIT" if hit_tp else "🛑 STOP LOSS"
                    pnl_emoji  = "🟢" if hit_tp else "🔴"
                    logger.info(f"{reason} triggered for {sym} at {price}")

                    # Execute sell
                    try:
                        sell_order = client.order_market_sell(symbol=sym, quantity=qty)
                        fills      = sell_order.get("fills", [])
                        sell_price = (
                            sum(float(f["price"]) * float(f["qty"]) for f in fills)
                            / sum(float(f["qty"]) for f in fills)
                            if fills else price
                        )
                        profit_usdt = round((sell_price - buy_price) * qty, 4)

                        await bot.send_message(
                            chat_id=TELEGRAM_USER_ID,
                            text=(
                                f"{reason} HIT!\n\n"
                                f"Pair:       `{sym}`\n"
                                f"Buy:        `{fmt(buy_price)}`\n"
                                f"Sell:       `{fmt(sell_price)}`\n"
                                f"Quantity:   `{qty}`\n"
                                f"{pnl_emoji} PnL: `{pnl_pct:+.2f}%` (`{profit_usdt:+.4f} USDT`)\n"
                                f"Time: `{now_str()}`"
                            ),
                            parse_mode="Markdown",
                        )
                        del active_trades[sym]

                    except BinanceAPIException as e:
                        logger.error(f"Sell error for {sym}: {e.message}")
                        await bot.send_message(
                            chat_id=TELEGRAM_USER_ID,
                            text=f"⚠️ Target hit for *{sym}* but sell failed: {e.message}",
                            parse_mode="Markdown",
                        )

                else:
                    # Periodic update every ~5 minutes (60 checks × 5s)
                    trade["_check_count"] = trade.get("_check_count", 0) + 1
                    if trade["_check_count"] % 60 == 0:
                        await bot.send_message(
                            chat_id=TELEGRAM_USER_ID,
                            text=(
                                f"📊 *{sym}* update\n"
                                f"Price: `{fmt(price)}`  |  PnL: `{pnl_pct:+.2f}%`\n"
                                f"🎯 TP: `{fmt(tp_price)}`  🛑 SL: `{fmt(sl_price)}`"
                            ),
                            parse_mode="Markdown",
                        )

            except Exception as e:
                logger.error(f"Price check error for {sym}: {e}")

# ─────────────────────────────────────────────
#  BACKGROUND: NEW COIN DETECTOR
# ─────────────────────────────────────────────
async def new_coin_detector_loop(bot: Bot, bot_data: dict):
    """Runs in background — detects newly listed coins on Binance."""
    global known_symbols
    logger.info("New coin detector started.")

    client = get_client()
    info   = client.get_exchange_info()
    known_symbols = {s["symbol"] for s in info["symbols"] if s["status"] == "TRADING"}
    logger.info(f"Loaded {len(known_symbols)} existing symbols.")

    while True:
        await asyncio.sleep(NEW_COIN_CHECK_INTERVAL)
        if not bot_data.get("alerts_enabled", True):
            continue
        try:
            client     = get_client()
            info       = client.get_exchange_info()
            current    = {s["symbol"] for s in info["symbols"] if s["status"] == "TRADING"}
            new_ones   = current - known_symbols

            for sym in new_ones:
                logger.info(f"NEW COIN DETECTED: {sym}")
                try:
                    price = fmt(client.get_symbol_ticker(symbol=sym)["price"])
                except Exception:
                    price = "N/A"

                await bot.send_message(
                    chat_id=TELEGRAM_USER_ID,
                    text=(
                        f"🆕 *NEW COIN LISTED!*\n\n"
                        f"Symbol: `{sym}`\n"
                        f"Price:  `{price}`\n"
                        f"Time:   `{now_str()}`\n\n"
                        f"⚡ Open Binance to trade it now!"
                    ),
                    parse_mode="Markdown",
                )

            known_symbols = current

        except Exception as e:
            logger.error(f"New coin detector error: {e}")

# ─────────────────────────────────────────────
#  /cancel
# ─────────────────────────────────────────────
@restricted
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.", reply_markup=main_menu_keyboard())
    return MAIN_MENU

@restricted
async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Choose an action:", reply_markup=main_menu_keyboard())
    return MAIN_MENU

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(show_balance,        pattern="^balance$"),
                CallbackQueryHandler(view_active_trades,  pattern="^active_trades$"),
                CallbackQueryHandler(stop_trade_menu,     pattern="^stop_trade$"),
                CallbackQueryHandler(toggle_alerts,       pattern="^toggle_alerts$"),
                CallbackQueryHandler(begin_trade_setup,   pattern="^start_trade$"),
                CallbackQueryHandler(stop_specific_trade, pattern="^stop_.+$"),
                CallbackQueryHandler(back_to_menu,        pattern="^back$"),
            ],
            ENTER_SYMBOL:      [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_symbol)],
            ENTER_QUANTITY:    [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_quantity)],
            ENTER_TAKE_PROFIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_take_profit)],
            ENTER_STOP_LOSS:   [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_stop_loss)],
            CONFIRM_TRADE:     [CallbackQueryHandler(confirm_trade, pattern="^confirm_(yes|no)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)

    # Start background tasks after app initializes
    async def post_init(application: Application):
        application.bot_data["alerts_enabled"] = True
        asyncio.create_task(price_monitor_loop(application.bot))
        asyncio.create_task(new_coin_detector_loop(application.bot, application.bot_data))

    app.post_init = post_init

    env = "TESTNET" if USE_TESTNET else "LIVE"
    logger.info(f"Auto Trader Bot started [{env}]. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
