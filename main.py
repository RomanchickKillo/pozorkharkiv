import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "8395537898:AAECE1LFhXi0LrDeREVoMJfwLaUw0oniUvc"
ADMIN_ID = 5938341230  # Твой цифровой Telegram ID (узнать можно в @getmyid_bot)
CHANNEL_ID = "@pozorkharkiv"  # Username канала ИЛИ его цифровой ID (бот должен быть админом в канале!)
# =============================================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()


class Form(StatesGroup):
    photo = State()
    text = State()


class AdminForm(StatesGroup):
    reject_reason = State()


# --- СТАРТ И ПОЛИТИКА ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "📜 <b>Политика конфиденциальности и Правила</b>\n\n"
        "Используя этого бота для отправки материалов в канал <b>«ПОЗОР ХАРЬКОВА»</b>, вы соглашаетесь с правилами:\n"
        "1. Бот собирает фото и текст только для публикации. Мы гарантируем вашу анонимность.\n"
        "2. Вы подтверждаете, что имеете право отправлять эти материалы.\n"
        "3. <b>ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ:</b> Администрация канала не несет ответственности за достоверность информации и любой моральный или прямой ущерб.\n\n"
        "<i>Нажимая кнопку ниже, вы подтверждаете свое согласие.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я согласен(на)", callback_data="agree")]
    ])
    await message.answer(text, reply_markup=kb)


# --- ШАГ 1: ЗАПРОС ФОТО ---
@dp.callback_query(F.data == "agree")
async def process_agree(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Привет! 👋 Это бот предложки.\n\nПриложи фотографию <b>(ТОЛЬКО ОДНУ ФОТОГРАФИЮ)</b> для твоего поста.")
    await state.set_state(Form.photo)


# --- ШАГ 2: ПОЛУЧЕНИЕ ФОТО ---
@dp.message(Form.photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo=photo_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Верно", callback_data="photo_ok"),
         InlineKeyboardButton(text="❌ Не верно", callback_data="photo_bad")]
    ])
    await message.answer_photo(photo_id, caption="Фото успешно загружено! Всё верно?", reply_markup=kb)


@dp.message(Form.photo)
async def process_not_photo(message: Message):
    await message.answer("Пожалуйста, отправь только <b>ОДНУ фотографию</b> 🖼 (документы и видео пока не принимаем).")


# --- ШАГ 3: ОБРАБОТКА КНОПОК ФОТО ---
@dp.callback_query(F.data == "photo_bad")
async def photo_bad(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("Отправь другую фотографию:")
    await state.set_state(Form.photo)


@dp.callback_query(F.data == "photo_ok")
async def photo_ok(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("Напишите описание под ваше фото снизу (одним сообщением):")
    await state.set_state(Form.text)


# --- ШАГ 4: ПОЛУЧЕНИЕ ТЕКСТА И ПРЕДПРОСМОТР ---
@dp.message(Form.text, F.text)
async def process_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    data = await state.get_data()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Все верно, отправить", callback_data="post_ok")],
        [InlineKeyboardButton(text="✏️ Не верно (изменить)", callback_data="post_bad")]
    ])

    caption_text = f"👀 <b>Вот так будет выглядеть ваш пост:</b>\n\n❗Вам пришло уведомление:\n{data['text']}"
    await message.answer_photo(photo=data['photo'], caption=caption_text, reply_markup=kb)


@dp.message(Form.text)
async def process_not_text(message: Message):
    await message.answer("Пожалуйста, отправь текстовое описание.")


# --- ШАГ 5: МЕНЮ ИЗМЕНЕНИЙ ---
@dp.callback_query(F.data == "post_bad")
async def post_bad(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Изменить фото", callback_data="change_photo"),
         InlineKeyboardButton(text="📝 Изменить описание", callback_data="change_text")]
    ])
    await callback.message.edit_caption(caption="Что желаете изменить?", reply_markup=kb)


@dp.callback_query(F.data == "change_photo")
async def change_photo(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("Отправь новую фотографию:")
    await state.set_state(Form.photo)


@dp.callback_query(F.data == "change_text")
async def change_text(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("Отправь новый текст:")
    await state.set_state(Form.text)


# --- ШАГ 6: ОТПРАВКА АДМИНУ ---
@dp.callback_query(F.data == "post_ok")
async def post_ok(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = callback.from_user
    username = f"@{user.username}" if user.username else f"ID: {user.id}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ОПУБЛИКОВАТЬ В КАНАЛ", callback_data=f"adm_pub:{user.id}")],
        [InlineKeyboardButton(text="❌ ОТКАЗАТЬ", callback_data=f"adm_rej:{user.id}")]
    ])

    final_caption = f"❗Вам пришло уведомление:\n{data['text']}"

    await bot.send_message(ADMIN_ID, f"🚨 <b>Новая предложка от {username}!</b>")
    await bot.send_photo(ADMIN_ID, photo=data['photo'], caption=final_caption, reply_markup=kb)

    await callback.message.delete()
    await callback.message.answer("✅ Ваша анкета успешно отправлена администратору на проверку! Спасибо.")
    await state.clear()


# --- ШАГ 7: ПУЛЬТ АДМИНА (ОДОБРЕНИЕ) ---
@dp.callback_query(F.data.startswith("adm_pub:"))
async def admin_approve(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    user_id = int(callback.data.split(":")[1])
    photo_id = callback.message.photo[-1].file_id
    caption = callback.message.caption or ""

    await bot.send_photo(CHANNEL_ID, photo=photo_id, caption=caption)
    now = datetime.now().strftime("%d.%m.%Y в %H:%M:%S")

    try:
        await bot.send_message(user_id, f"🎉 <b>Ваш пост успешно одобрен и опубликован!</b>\n📅 Дата публикации: {now}")
    except Exception:
        pass

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply(f"✅ Пост опубликован в канале!\nПользователь уведомлен ({now}).")


# --- ШАГ 8: ПУЛЬТ АДМИНА (НАЧАЛО ОТКЛОНЕНИЯ) ---
@dp.callback_query(F.data.startswith("adm_rej:"))
async def admin_reject_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    user_id = int(callback.data.split(":")[1])

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Отказать без причины", callback_data="adm_rej_no_reason")]
    ])

    # Сохраняем сообщение с вопросом о причине, чтобы потом убрать кнопку
    prompt_msg = await callback.message.reply(
        "📝 <b>Напишите причину отклонения поста</b> следующим сообщением\nИЛИ нажмите кнопку ниже:",
        reply_markup=kb
    )

    await state.update_data(
        reject_user_id=user_id,
        mod_message=callback.message,
        prompt_msg_id=prompt_msg.message_id
    )
    await state.set_state(AdminForm.reject_reason)


# --- ШАГ 8.5: ОТКАЗ БЕЗ ПРИЧИНЫ ---
@dp.callback_query(F.data == "adm_rej_no_reason", AdminForm.reject_reason)
async def admin_reject_no_reason(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    admin_data = await state.get_data()
    user_id = admin_data['reject_user_id']
    mod_message = admin_data['mod_message']

    now = datetime.now().strftime("%d.%m.%Y в %H:%M:%S")

    # Уведомление пользователю (БЕЗ ПРИЧИНЫ)
    try:
        reject_text = (
            f"❌ <b>Ваш пост был отклонен модератором.</b>\n"
            f"📅 <b>Время проверки:</b> {now}"
        )
        await bot.send_message(user_id, reject_text)
    except Exception:
        pass

    # Убираем кнопки у сообщения с предложкой
    try:
        await mod_message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.edit_text(f"❌ Пост отклонен без указания причины. Пользователь уведомлен.\nВремя: {now}")
    await state.clear()


# --- ШАГ 9: ПУЛЬТ АДМИНА (ПОЛУЧЕНИЕ ПРИЧИНЫ И ФИНАЛ ОТКАЗА) ---
@dp.message(AdminForm.reject_reason, F.text)
async def admin_reject_final(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    admin_data = await state.get_data()
    user_id = admin_data['reject_user_id']
    mod_message = admin_data['mod_message']
    prompt_msg_id = admin_data.get('prompt_msg_id')
    reason = message.text

    now = datetime.now().strftime("%d.%m.%Y в %H:%M:%S")

    # Прячем кнопку "Отказать без причины" из предыдущего сообщения (чтобы не мозолила глаза)
    if prompt_msg_id:
        try:
            await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=prompt_msg_id, reply_markup=None)
        except Exception:
            pass

    # Уведомление пользователю (С ПРИЧИНОЙ)
    try:
        reject_text = (
            f"❌ <b>Ваш пост был отклонен модератором.</b>\n"
            f"📅 <b>Время проверки:</b> {now}\n"
            f"💬 <b>Причина отказа:</b> {reason}"
        )
        await bot.send_message(user_id, reject_text)
    except Exception:
        pass

    try:
        await mod_message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await message.reply(f"❌ Пост успешно отклонен. Пользователю отправлена причина.\nВремя: {now}")
    await state.clear()


# ================= ЗАПУСК БОТА =================
async def main():
    logging.basicConfig(level=logging.INFO)
    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())