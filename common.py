"""Telegram UI yordamchilari (faqat bot uchun): tugmalar, xabar tahrirlash, middleware."""
from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton as IB
from aiogram.types import InlineKeyboardMarkup

from config import (ADMINS, APPS, NAME_RE, RISKY, SVC_RE, TMP, TRASH, bar, esc,  # noqa: F401
                    pre, q, sh)


def B(t, d): return IB(text=t, callback_data=d)
def K(rows): return InlineKeyboardMarkup(inline_keyboard=rows)


async def edit(msg, text, reply_markup=None):
    """Xabarni tahrirlaydi; o'zgarmagan bo'lsa jim, tahrirlab bo'lmasa — yangi xabar yuboradi."""
    try:
        await msg.edit_text(text[:4000], reply_markup=reply_markup, disable_web_page_preview=True)
    except TelegramBadRequest as e:
        if "not modified" not in str(e).lower():
            await msg.answer(text[:4000], reply_markup=reply_markup)


class AdminOnly(BaseMiddleware):
    """Bitta joyda: admin bo'lmaganlarning hamma xabar va tugmalari e'tiborsiz qoldiriladi."""
    async def __call__(self, handler, event, data):
        e = event.message or event.callback_query
        if e and e.from_user and e.from_user.id in ADMINS:
            return await handler(event, data)


class AutoAnswer(BaseMiddleware):
    """Tugma bosilishi bilanoq javob beradi — «soat» aylanib turmaydi, bot tez seziladi."""
    async def __call__(self, handler, event, data):
        try:
            await event.answer()
        except Exception:
            pass
        return await handler(event, data)
