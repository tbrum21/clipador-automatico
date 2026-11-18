"""Aprovacao via Telegram: previa do corte com botoes Aprovar / Rejeitar."""
import shutil
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

from . import config as C
from . import db


async def send_preview(bot, clip_id: int, preview: Path, caption: str):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Aprovar", callback_data=f"ok:{clip_id}"),
        InlineKeyboardButton("❌ Rejeitar", callback_data=f"no:{clip_id}"),
    ]])
    with open(preview, "rb") as f:
        await bot.send_video(chat_id=C.TELEGRAM_CHAT_ID, video=f, caption=caption[:1000],
                             reply_markup=kb, supports_streaming=True,
                             read_timeout=180, write_timeout=180, connect_timeout=30)


async def _on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if str(q.message.chat_id) != str(C.TELEGRAM_CHAT_ID):
        return
    action, cid = q.data.split(":")
    clip = db.get_clip(int(cid))
    if not clip:
        return
    if action == "ok":
        dest = shutil.copy2(clip["path"], C.APPROVED_DIR / Path(clip["path"]).name)
        db.set_status(int(cid), "aprovado")
        await q.edit_message_caption(caption=f"✅ APROVADO\n{clip['title']}\n\nArquivo final:\n{dest}")
    else:
        db.set_status(int(cid), "rejeitado")
        await q.edit_message_caption(caption=f"❌ Rejeitado: {clip['title']}")


async def _status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) == str(C.TELEGRAM_CHAT_ID):
        await update.message.reply_text(f"Cortes: {db.counts() or 'nenhum ainda'}")


def build_app():
    app = ApplicationBuilder().token(C.TELEGRAM_TOKEN).build()
    app.add_handler(CallbackQueryHandler(_on_button))
    app.add_handler(CommandHandler("status", _status))
    return app
