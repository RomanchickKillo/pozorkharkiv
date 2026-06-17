import asyncio
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, PreCheckoutQuery, \
    LabeledPrice
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "8395537898:AAECE1LFhXi0LrDeREVoMJfwLaUw0oniUvc"
ADMIN_ID = 5938341230  # Твой цифровой Telegram ID
CHANNEL_ID = "@pozorkharkiv"  # Username канала ИЛИ его цифровой ID
USERS_FILE = "/data/users.txt"  # Файл, где будут храниться ID пользователей
POSTS_FILE = "/data/posts.txt"  # Файл, где хранится связь постов в канале с авторами
# =============================================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()


class Form(StatesGroup):
    photo = State()
    text = State()


class AdminForm(StatesGroup):
    reject_reason = State()


# Новые состояния для функции поиска автора
class AuthorCheckForm(StatesGroup):
    waiting_for_post = State()
    waiting_for_payment = State()


# --- ФУНКЦИИ БАЗЫ ДАННЫХ (ФАЙЛЫ) ---
def add_user(user_id: int):
    """Добавляет пользователя в текстовый файл, если его там еще нет."""
    users = get_users()
    if user_id not in users:
        with open(USERS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{user_id}\n")


def get_users() -> set:
    """Возвращает множество (set) со всеми ID пользователей."""
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return set(int(line.strip()) for line in f if line.strip().isdigit())


def add_post_mapping(channel_msg_id: int, user_id: int, username: str):
    """Запоминает, какой пользователь создал пост с определенным ID в канале."""
    with open(POSTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{channel_msg_id}:{user_id}:{username}\n")


def get_post_mapping(channel_msg_id: int):
    """Ищет автора по ID сообщения из канала."""
    if not os.path.exists(POSTS_FILE):
        return None
    with open(POSTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(":")
            if len(parts) >= 3:
                msg_id, u_id, uname = parts[0], parts[1], parts[2]
                if int(msg_id) == channel_msg_id:
                    return {"user_id": int(u_id), "username": uname}
    return None


# --- ГЛАВНОЕ МЕНЮ СТАРТА ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    add_user(message.from_user.id)
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Предложить пост", callback_data="menu_rules")],
        [InlineKeyboardButton(text="🔍 Узнать автора поста", callback_data="menu_find_author")]
    ])
    await message.answer(
        "Привет! 👋 Добро пожаловать в бот канала <b>«ПОЗОР ХАРЬКОВА»</b>.\n\n"
        "Выберите нужный пункт меню ниже:",
        reply_markup=kb
    )


# --- ПОЛИТИКА И ПРАВИЛА (ЕСЛИ ВЫБРАЛИ ПРЕДЛОЖИТЬ) ---
@dp.callback_query(F.data == "menu_rules")
async def process_menu_rules(callback: CallbackQuery, state: FSMContext):
    text = (
        "📜 <b>Условия конфиденциальности и Правила</b>\n\n"
        "Перед тем как предложить пост, пожалуйста, ознакомьтесь с нашими условиями конфиденциальности и правилами на сайте:\n"
        "🔗 https://pozorkharkiv.netlify.app/\n\n"
        "Также обращаем ваше внимание, что в боте действует платная услуга <b>«Узнать, кто отправил пост»</b>. Её стоимость составляет <b>100 звёзд (Telegram Stars)</b>.\n\n"
        "<i>Пожалуйста, ознакомьтесь с информацией на сайте. После этого нажмите кнопку ниже для продолжения.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я согласен(а)", callback_data="agree")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)


# --- КОМАНДА РАССЫЛКИ (ТОЛЬКО ДЛЯ АДМИНА) ---
@dp.message(Command("rasilka"))
async def cmd_rasilka(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("⚠️ <b>Ошибка!</b> Использование команды:\n<code>/rasilka Текст вашего сообщения</code>")
        return

    text_to_send = parts[1]
    users = get_users()

    if not users:
        await message.answer("В базе пока нет ни одного пользователя.")
        return

    await message.answer(f"⏳ Начинаю рассылку для <b>{len(users)}</b> пользователей...")

    success = 0
    failed = 0

    for user_id in users:
        try:
            await bot.send_message(user_id, text_to_send)
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await message.answer(f"✅ <b>Рассылка успешно завершена!</b>\n\nДоставлено: {success}\nНе доставлено: {failed}")


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
    await message.answer("Пожалуйста, отправь только <b>ОДНУ фотографию</b> 🖼")


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

    bot_link = '<a href="https://t.me/pozorkharkivbot">ПОЗОР ХАРЬКОВА | Бот для предлоги</a>'
    caption_text = f"👀 <b>Вот так будет выглядеть ваш post:</b>\n\n❗Вам пришло уведомление:\n{data['text']}\n\n{bot_link}"
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

    # Передаем ID и юзернейм автора в callback кнопки (чтобы админ при публикации занес их в базу)
    uname_clean = user.username if user.username else "None"

    kb_admin = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ОПУБЛИКОВАТЬ В КАНАЛ", callback_data=f"adm_pub:{user.id}:{uname_clean}")],
        [InlineKeyboardButton(text="❌ ОТКАЗАТЬ", callback_data=f"adm_rej:{user.id}")]
    ])

    bot_link = '<a href="https://t.me/pozorkharkivbot">ПОЗОР ХАРЬКОВА | Бот для предлоги</a>'
    final_caption = f"❗Вам пришло уведомление:\n{data['text']}\n\n{bot_link}"

    await bot.send_message(ADMIN_ID, f"🚨 <b>Новая предложка от {username}!</b>")
    await bot.send_photo(ADMIN_ID, photo=data['photo'], caption=final_caption, reply_markup=kb_admin)

    kb_user = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Отправить еще пост", callback_data="send_more")]
    ])

    await callback.message.delete()
    await callback.message.answer("✅ Ваша анкета успешно отправлена администратору на проверку! Спасибо.",
                                  reply_markup=kb_user)
    await state.clear()


# --- КНОПКА "ОТПРАВИТЬ ЕЩЕ" ---
@dp.callback_query(F.data == "send_more")
async def process_send_more(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("Приложи фотографию <b>(ТОЛЬКО ОДНУ ФОТОГРАФИЮ)</b> для твоего нового поста.")
    await state.set_state(Form.photo)


# --- ШАГ 7: ПУЛЬТ АДМИНА (ОДОБРЕНИЕ + ЗАПИСЬ В БАЗУ ПОСТОВ) ---
@dp.callback_query(F.data.startswith("adm_pub:"))
async def admin_approve(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    # Извлекаем данные автора из кнопки
    parts = callback.data.split(":")
    user_id = int(parts[1])
    username = parts[2]

    photo_id = callback.message.photo[-1].file_id
    caption = callback.message.html_text or ""

    # Публикуем в канал и получаем данные отправленного сообщения
    sent_msg = await bot.send_photo(CHANNEL_ID, photo=photo_id, caption=caption)

    # СОХРАНЯЕМ СВЯЗЬ: ID сообщения в канале -> Кто его отправил
    add_post_mapping(sent_msg.message_id, user_id, username)

    now = datetime.now().strftime("%d.%m.%Y в %H:%M:%S")
    channel_link = '<a href="https://t.me/pozorkharkiv">ПОЗОР ХАРЬКОВА</a>'

    try:
        await bot.send_message(
            user_id,
            f"🎉 <b>Ваш пост успешно одобрен и опубликован!</b>\n"
            f"📅 Дата публикации: {now}\n\n"
            f"Посмотреть можно здесь: {channel_link}"
        )
    except Exception:
        pass

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply(
        f"✅ Пост опубликован в канале!\nСвязь сохранена в базу. Пользователь уведомлен ({now}).")


# --- ШАГ 8: ПУЛЬТ АДМИНА (ОТКЛОНЕНИЕ) ---
@dp.callback_query(F.data.startswith("adm_rej:"))
async def admin_reject_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    user_id = int(callback.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Отказать без причины", callback_data="adm_rej_no_reason")]
    ])
    prompt_msg = await callback.message.reply(
        "📝 <b>Напишите причину отклонения поста</b> следующим сообщением\nИЛИ нажмите кнопку ниже:", reply_markup=kb
    )
    await state.update_data(reject_user_id=user_id, mod_message=callback.message, prompt_msg_id=prompt_msg.message_id)
    await state.set_state(AdminForm.reject_reason)


@dp.callback_query(F.data == "adm_rej_no_reason", AdminForm.reject_reason)
async def admin_reject_no_reason(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    admin_data = await state.get_data()
    user_id = admin_data['reject_user_id']
    mod_message = admin_data['mod_message']
    now = datetime.now().strftime("%d.%m.%Y в %H:%M:%S")

    try:
        await bot.send_message(user_id, f"❌ <b>Ваш пост был отклонен модератором.</b>\n📅 <b>Время проверки:</b> {now}")
    except Exception:
        pass

    try:
        await mod_message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.edit_text(f"❌ Пост отклонен без причины. Пользователь уведомлен.\nВремя: {now}")
    await state.clear()


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

    if prompt_msg_id:
        try:
            await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=prompt_msg_id, reply_markup=None)
        except Exception:
            pass

    try:
        await bot.send_message(user_id,
                               f"❌ <b>Ваш пост был отклонен модератором.</b>\n📅 <b>Время проверки:</b> {now}\n💬 <b>Причина отказа:</b> {reason}")
    except Exception:
        pass

    try:
        await mod_message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await message.reply(f"❌ Пост успешно отклонен. Пользователю отправлена причина.\nВремя: {now}")
    await state.clear()


# ================= ФУНКЦИЯ УЗНАТЬ АВТОРА (ПЛАТНАЯ) =================

# Выбрали пункт поиска автора
@dp.callback_query(F.data == "menu_find_author")
async def find_author_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🔍 <b>Поиск автора поста</b>\n\n"
        "Перешлите (forward) сообщение из канала <b>@pozorkharkiv</b> прямо сюда, чтобы я его автоматически проанализировал."
    )
    await state.set_state(AuthorCheckForm.waiting_for_post)


# Пользователь переслал сообщение
@dp.message(AuthorCheckForm.waiting_for_post)
async def process_forwarded_post(message: Message, state: FSMContext):
    if not message.forward_from_chat:
        await message.answer(
            "⚠️ Пожалуйста, именно <b>перешлите (forward)</b> пост из канала, а не просто скопируйте его текст.")
        return

    # Проверяем, что переслали именно из твоего канала
    channel_username = CHANNEL_ID.replace("@", "").lower()
    forwarded_username = (message.forward_from_chat.username or "").lower()

    if forwarded_username != channel_username:
        await message.answer(f"⚠️ Этот пост пришел не из канала {CHANNEL_ID}. Перешлите пост из правильного канала.")
        return

    msg_id = message.forward_from_message_id
    if not msg_id:
        await message.answer("⚠️ Не удалось распознать ID сообщения. Попробуйте еще раз.")
        return

    # Ищем пост в базе файлов
    mapping = get_post_mapping(msg_id)
    if not mapping:
        await message.answer(
            "❌ К сожалению, этот пост не был найден в базе нашей предложки (возможно, он был опубликован админом напрямую).")
        await state.clear()
        return

    # Если нашли создателя
    author_username = mapping["username"]
    if author_username == "None":
        author_text = f"Пользователь скрыл ник (ID: {mapping['user_id']})"
    else:
        author_text = f"@{author_username}"

    # Сохраняем имя автора в память текущего пользователя, чтобы выдать после оплаты
    await state.update_data(found_author=author_text)

    # Создаем ссылку на оплату в 100 Звезд (Telegram Stars)
    invoice_link = await bot.create_invoice_link(
        title="Узнать автора поста",
        description=f"Успешно найден создатель поста №{msg_id}! Оплатите услугу, чтобы раскрыть его.",
        payload=f"check_author_pay:{message.from_user.id}",
        provider_token="",  # Для Telegram Stars всегда оставляется пустым
        currency="XTR",  # Код валюты Telegram Stars
        prices=[LabeledPrice(label="Stars", amount=100)]
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Оплатить 100 звезд", url=invoice_link)]
    ])

    await message.answer(
        "✅ <b>Успешно найден создатель!</b>\n\n"
        "Чтобы бот автоматически прислал вам его контакты, пожалуйста, оплатите 100 звезд ниже:",
        reply_markup=kb
    )
    await state.set_state(AuthorCheckForm.waiting_for_payment)


# Обязательное подтверждение готовности принять платеж от Telegram
@dp.pre_checkout_query()
async def on_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


# Обработка успешного платежа звезд
@dp.message(AuthorCheckForm.waiting_for_payment, F.successful_payment)
async def got_payment(message: Message, state: FSMContext):
    data = await state.get_data()
    author_text = data.get("found_author", "Неизвестно")

    # Текст по твоему ТЗ
    await message.answer(
        f"Оплата прошла успешно! Создатель вашего поста: {author_text}"
    )
    await state.clear()


# ================= ЗАПУСК БОТА =================
async def main():
    logging.basicConfig(level=logging.INFO)
    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())