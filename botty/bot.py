import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# ── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN = "8189141997:AAGjIB39qSjJt-k9FNouJ_5W6mUaPs9-jYg"
ADMIN_ID  = 8769146517          # Your Telegram user ID (integer)

WALLETS = {
    "BTC":  "bc1ql4jxdu8s67ape5sm9pn850g3qj3f6qzepyasem",
    "USDT": "0xb97f0FD482C6dAA750529Bc40dCE158201376f2d",
    "SOL":  "6i5nCQxvAQr5zu3z3zKaL3SKcQ5FRfEwSM9sVXbqXPmv",
}

PLANS = {
    "basic": {
        "name":  "Basic Bot Plan",
        "price": "$2,000",
        "desc":  "Runs on 2 trading pairs simultaneously.",
    },
    "premium": {
        "name":  "Premium Bot Plan",
        "price": "$5,000",
        "desc":  "Runs on up to 6 trading pairs simultaneously.",
    },
}

DB_PATH = "orders.db"

# ── STATES ────────────────────────────────────────────────────────────────────
SELECT_PLAN, SELECT_CRYPTO, AWAIT_TXID = range(3)

# ── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── DATABASE ──────────────────────────────────────────────────────────────────
def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ref         TEXT    NOT NULL,
            user_id     INTEGER NOT NULL,
            username    TEXT,
            full_name   TEXT,
            plan        TEXT    NOT NULL,
            price       TEXT    NOT NULL,
            crypto      TEXT    NOT NULL,
            txid        TEXT    NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'pending',
            created_at  TEXT    NOT NULL
        )
    """)
    con.commit()
    con.close()


def save_order(ref, user_id, username, full_name, plan, price, crypto, txid):
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """INSERT INTO orders
           (ref, user_id, username, full_name, plan, price, crypto, txid, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (ref, user_id, username, full_name, plan, price, crypto, txid,
         datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")),
    )
    con.commit()
    con.close()


def get_all_orders():
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT ref, full_name, username, plan, price, crypto, txid, status, created_at "
        "FROM orders ORDER BY id DESC"
    ).fetchall()
    con.close()
    return rows


def update_order_status(ref, status):
    con = sqlite3.connect(DB_PATH)
    con.execute("UPDATE orders SET status = ? WHERE ref = ?", (status, ref))
    con.commit()
    con.close()


def get_order_by_ref(ref):
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT ref, full_name, username, plan, price, crypto, txid, status, created_at, user_id "
        "FROM orders WHERE ref = ?", (ref,)
    ).fetchone()
    con.close()
    return row


def make_ref(user_id):
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"ORD-{stamp}-{str(user_id)[-4:]}"


# ── HELPERS ───────────────────────────────────────────────────────────────────
def plan_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🥉 Basic Bot Plan — $2,000",   callback_data="plan_basic")],
        [InlineKeyboardButton("🥇 Premium Bot Plan — $5,000", callback_data="plan_premium")],
    ])

def crypto_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("₿  Bitcoin (BTC)",  callback_data="crypto_BTC")],
        [InlineKeyboardButton("💵 Tether (USDT)",  callback_data="crypto_USDT")],
        [InlineKeyboardButton("◎  Solana (SOL)",   callback_data="crypto_SOL")],
    ])

def status_keyboard(ref):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Mark Delivered", callback_data=f"status_delivered_{ref}"),
            InlineKeyboardButton("❌ Mark Rejected",  callback_data=f"status_rejected_{ref}"),
        ]
    ])

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID


# ── CONVERSATION HANDLERS ─────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user.first_name
    text = (
        f"👋 Welcome, {user}!\n\n"
        "I'm the official sales bot. Choose a plan below to get started.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🥉 *Basic Bot Plan — $2,000*\n"
        "   • Active on 2 trading pairs at a time\n\n"
        "🥇 *Premium Bot Plan — $5,000*\n"
        "   • Active on up to 6 trading pairs at once\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 Select your plan:"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=plan_keyboard())
    return SELECT_PLAN


async def select_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    plan_key = query.data.replace("plan_", "")
    plan = PLANS[plan_key]
    ctx.user_data["plan"] = plan_key

    text = (
        f"✅ You selected: *{plan['name']}* ({plan['price']})\n\n"
        "Now choose your preferred cryptocurrency for payment:\n\n"
        "₿  Bitcoin (BTC)\n"
        "💵 Tether (USDT)\n"
        "◎  Solana (SOL)"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=crypto_keyboard())
    return SELECT_CRYPTO


async def select_crypto(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    crypto = query.data.replace("crypto_", "")
    ctx.user_data["crypto"] = crypto
    wallet = WALLETS[crypto]

    plan_key = ctx.user_data["plan"]
    plan = PLANS[plan_key]

    ref = make_ref(query.from_user.id)
    ctx.user_data["ref"] = ref

    text = (
        f"📋 *Order Summary*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Ref:     `{ref}`\n"
        f"Plan:    {plan['name']}\n"
        f"Amount:  {plan['price']}\n"
        f"Crypto:  {crypto}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Send *exactly {plan['price']}* worth of {crypto} to the address below:\n\n"
        f"`{wallet}`\n\n"
        f"_(Tap the address to copy it)_\n\n"
        f"Once sent, paste your *Transaction ID / Hash* here and I'll notify the team to process your order."
    )
    await query.edit_message_text(text, parse_mode="Markdown")
    return AWAIT_TXID


async def receive_txid(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    txid = update.message.text.strip()
    user = update.effective_user
    plan_key = ctx.user_data.get("plan", "N/A")
    crypto   = ctx.user_data.get("crypto", "N/A")
    ref      = ctx.user_data.get("ref", make_ref(user.id))
    plan     = PLANS.get(plan_key, {})

    save_order(
        ref       = ref,
        user_id   = user.id,
        username  = user.username or "",
        full_name = user.full_name,
        plan      = plan.get("name", plan_key),
        price     = plan.get("price", "N/A"),
        crypto    = crypto,
        txid      = txid,
    )

    await update.message.reply_text(
        f"⏳ *Processing...*\n\n"
        f"We've received your transaction. Our team will verify payment and reach out shortly.\n\n"
        f"Your order reference: `{ref}`\n\n"
        f"Thank you for your purchase! 🙏",
        parse_mode="Markdown",
    )

    admin_msg = (
        f"🔔 *New Order Received!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🗂  Ref:     `{ref}`\n"
        f"👤 User:    {user.full_name} (@{user.username or 'N/A'})\n"
        f"🆔 User ID: `{user.id}`\n"
        f"📦 Plan:    {plan.get('name', plan_key)}\n"
        f"💰 Amount:  {plan.get('price', 'N/A')}\n"
        f"🪙 Crypto:  {crypto}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 TX ID:\n`{txid}`"
    )
    await ctx.bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_msg,
        parse_mode="Markdown",
        reply_markup=status_keyboard(ref),
    )

    return ConversationHandler.END


# ── ADMIN: STATUS BUTTON CALLBACKS ────────────────────────────────────────────
async def handle_status_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not is_admin(update):
        await query.answer("⛔ Unauthorised.", show_alert=True)
        return

    parts  = query.data.split("_", 2)
    action = parts[1]   # "delivered" or "rejected"
    ref    = parts[2]

    update_order_status(ref, action)
    order = get_order_by_ref(ref)

    emoji = "✅" if action == "delivered" else "❌"
    await query.answer(f"{emoji} Order marked as {action}.")
    await query.edit_message_text(
        query.message.text + f"\n\n{emoji} *Marked as {action}.*",
        parse_mode="Markdown",
    )

    if order:
        customer_id = order[9]
        customer_msg = (
            f"{emoji} *Order Update — `{ref}`*\n\n"
            + (
                "Your payment has been verified and your product is on its way! "
                "We'll be in touch shortly. Thank you 🙏"
                if action == "delivered" else
                "Unfortunately we could not verify your transaction. "
                "Please contact support or type /start to try again."
            )
        )
        try:
            await ctx.bot.send_message(
                chat_id=customer_id,
                text=customer_msg,
                parse_mode="Markdown",
            )
        except Exception:
            pass


# ── ADMIN: /orders COMMAND ────────────────────────────────────────────────────
async def orders_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ This command is for admins only.")
        return

    rows = get_all_orders()

    if not rows:
        await update.message.reply_text("📭 No orders yet.")
        return

    STATUS_EMOJI = {"pending": "⏳", "delivered": "✅", "rejected": "❌"}

    await update.message.reply_text(
        f"📦 *All Orders ({len(rows)} total)*\n━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
    )

    chunks = [rows[i:i+5] for i in range(0, len(rows), 5)]
    for chunk in chunks:
        msg = ""
        for row in chunk:
            ref, full_name, username, plan, price, crypto, txid, status, created_at = row
            emoji = STATUS_EMOJI.get(status, "❓")
            msg += (
                f"\n{emoji} *{ref}*\n"
                f"   👤 {full_name} (@{username or 'N/A'})\n"
                f"   📦 {plan} — {price} ({crypto})\n"
                f"   🔗 `{txid[:30]}{'…' if len(txid) > 30 else ''}`\n"
                f"   🕐 {created_at}  |  Status: *{status}*\n"
            )
        await update.message.reply_text(msg.strip(), parse_mode="Markdown")


# ── ADMIN: /orderstats COMMAND ────────────────────────────────────────────────
async def orderstats_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ This command is for admins only.")
        return

    rows = get_all_orders()
    total     = len(rows)
    pending   = sum(1 for r in rows if r[7] == "pending")
    delivered = sum(1 for r in rows if r[7] == "delivered")
    rejected  = sum(1 for r in rows if r[7] == "rejected")
    basic_count   = sum(1 for r in rows if "Basic" in r[3])
    premium_count = sum(1 for r in rows if "Premium" in r[3])

    text = (
        f"📊 *Order Statistics*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Orders:    {total}\n"
        f"⏳ Pending:      {pending}\n"
        f"✅ Delivered:    {delivered}\n"
        f"❌ Rejected:     {rejected}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🥉 Basic Plan:   {basic_count}\n"
        f"🥇 Premium Plan: {premium_count}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ── GENERIC HANDLERS ──────────────────────────────────────────────────────────
async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Session cancelled. Type /start to begin again.")
    return ConversationHandler.END


async def fallback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "I'm waiting for your Transaction ID. Please paste it here, or type /cancel to start over."
    )
    return AWAIT_TXID


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_PLAN:   [CallbackQueryHandler(select_plan,   pattern="^plan_")],
            SELECT_CRYPTO: [CallbackQueryHandler(select_crypto, pattern="^crypto_")],
            AWAIT_TXID:    [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_txid)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.TEXT & ~filters.COMMAND, fallback),
        ],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("orders",     orders_command))
    app.add_handler(CommandHandler("orderstats", orderstats_command))
    app.add_handler(CallbackQueryHandler(handle_status_update, pattern="^status_"))

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
