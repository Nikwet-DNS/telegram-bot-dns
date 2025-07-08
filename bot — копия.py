import logging
import os
import json
import asyncio
import pytz
from pytz import timezone
from datetime import datetime, time
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommandScopeDefault,
    BotCommandScopeChat
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler
)
import dateparser
import nest_asyncio

# Добавляем импорт конфигурации
from config import TOKEN, ADMIN_IDS

# Применяем nest_asyncio для Jupyter Notebook и подобных сред
nest_asyncio.apply()

DATA_FILE = "data.json"
CHAT_IDS_FILE = "chat_ids.json"

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальные переменные
promotions = {}
chat_ids = {}

# Вспомогательные функции
def check_file_permissions():
    if not os.access(CHAT_IDS_FILE, os.R_OK):
        logger.error(f"Нет прав на чтение файла {CHAT_IDS_FILE}")
        return False
    return True

def custom_serializer(obj):
    """Кастомный сериализатор для JSON"""
    if isinstance(obj, set):
        return list(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def save_data(data):
    """Сохранение данных в файл"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=custom_serializer)
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных: {e}")

def load_chat_ids():
    if not os.path.exists(CHAT_IDS_FILE):
        logger.error(f"Файл {CHAT_IDS_FILE} не найден")
        return {}
    
    try:
        with open(CHAT_IDS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except UnicodeDecodeError:
        try:
            with open(CHAT_IDS_FILE, 'r', encoding='cp1251') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка при чтении файла chat_ids: {e}")
            return {}
    except Exception as e:
        logger.error(f"Другая ошибка при загрузке chat_ids: {e}")
        return {}

def load_data():
    """Загрузка данных"""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except UnicodeDecodeError:
        try:
            with open(DATA_FILE, 'r', encoding='cp1251') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Не удалось прочитать файл даже в cp1251: {e}")
            return {}
    except Exception as e:
        logger.error(f"Другая ошибка при чтении {DATA_FILE}: {e}")
        return {}

def save_chat_ids(chat_ids_data):
    """Сохранение ID чатов"""
    try:
        with open(CHAT_IDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(chat_ids_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка при сохранении ID чатов: {e}")

def check_and_create_files():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        logger.info(f"Создан файл {DATA_FILE}")
    
    if not os.path.exists(CHAT_IDS_FILE):
        with open(CHAT_IDS_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)  # Создаем пустой словарь
        logger.info(f"Создан файл {CHAT_IDS_FILE}")
    
    if not os.path.exists('photos'):
        os.makedirs('photos')
        logger.info("Создана директория photos")

def load_initial_data():
    """Загрузка начальных данных"""
    check_and_create_files()
    return load_data(), load_chat_ids()

def is_promotion_active(promotion):
    try:
        start = datetime.fromisoformat(promotion['start_date']).date()
        end = datetime.fromisoformat(promotion['end_date']).date()
        now = datetime.now().date()
        result = start <= now <= end
        logger.info(f"Проверка активности акции '{promotion['name']}': {result}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при проверке активности акции: {e}")
        return False

def split_text_with_link(text, max_length=1024):
    """Разделение текста с сохранением ссылки"""
    if not text:
        return []
    
    link_start = text.rfind("http")
    if link_start == -1:
        return [text[i:i + max_length] for i in range(0, len(text), max_length)]
    
    main_text = text[:link_start].strip()
    link = text[link_start:].strip()
    
    if len(text) <= max_length:
        return [text]
    
    parts = [main_text[i:i + max_length] for i in range(0, len(main_text), max_length)]
    parts.append(link)
    return parts

def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    """Построение меню кнопок"""
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu

# Загрузка начальных данных
promotions, chat_ids = load_initial_data()

# Состояния для ConversationHandler
SHOP_SELECTION, PROMO_NAME, PROMO_DATES, PROMO_DESC, PROMO_PHOTO, PROMO_LINK, PROMO_SHOPS = range(7)
EDIT_PROMO_SELECTION, EDIT_SHOP_SELECTION = range(2)
SELECT_PROMO_FOR_SENDING, SELECT_SHOPS_FOR_SENDING = range(10, 12)

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    chat_id = str(update.effective_chat.id)
    if chat_id not in chat_ids:
        await update.message.reply_text("Привет! Пожалуйста, укажите название магазина:")
        return "WAITING_FOR_STORE_NAME"
    await update.message.reply_text(f"Привет, {chat_ids[chat_id]}! Используйте команду /promotions для просмотра акций.")
    return ConversationHandler.END

async def handle_store_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка названия магазина"""
    chat_id = str(update.effective_chat.id)
    store_name = update.message.text.strip()
    if not store_name:
        await update.message.reply_text("Название магазина не может быть пустым. Попробуйте снова.")
        return "WAITING_FOR_STORE_NAME"
    
    chat_ids[chat_id] = store_name
    save_chat_ids(chat_ids)
    
    logger.info(f"Сохранен чат: {chat_id} - {store_name}")
    await update.message.reply_text(
        f"Спасибо! Вы зарегистрированы как {store_name}. Используйте команду /promotions для просмотра акций."
    )
    return ConversationHandler.END

async def view_promotions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр акций"""
    chat_id = str(update.effective_chat.id)
    all_promotions = load_data()
    logger.info(f"Всего загружено акций: {len(all_promotions)}")
    
    active_promotions = {
        pid: p
        for pid, p in all_promotions.items()
        if is_promotion_active(p) and chat_id in p.get("shops", [])
    }
    
    logger.info(f"Активных акций для чата {chat_id}: {len(active_promotions)}")
    
    if not active_promotions:
        await update.message.reply_text("Нет актуальных акций.")
        return
    
    keyboard = [
        [InlineKeyboardButton(p["name"], callback_data=f"promo_{pid}")]
        for pid, p in active_promotions.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите акцию:", reply_markup=reply_markup)

async def handle_promotion_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора акции"""
    query = update.callback_query
    await query.answer()
    
    try:
        await query.message.delete()
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения: {str(e)}")
    
    promo_id = query.data.split("_")[1]
    promotion = promotions.get(promo_id)
    
    if not promotion:
        await query.message.reply_text("Акция не найдена.")
        return
    
    message = f"""
<b>Акция:</b> {promotion['name']}
<b>Даты проведения:</b> {promotion['start_date']} — {promotion['end_date']}
<b>Описание:</b> {promotion['description']}
<b>Ссылка:</b> {promotion['link']}
""".strip()
    
    try:
        photo_path = promotion["photo"]
        chat_id = query.message.chat_id
        parts = split_text_with_link(message)
        
        with open(photo_path, "rb") as photo:
            await context.bot.send_photo(
                chat_id=chat_id, 
                photo=photo, 
                caption=parts[0], 
                parse_mode="HTML"
            )
        
        for part in parts[1:]:
            await context.bot.send_message(chat_id=chat_id, text=part, parse_mode="HTML")
    
    except Exception as e:
        logger.error(f"Ошибка при отправке фото: {str(e)}")
        await context.bot.send_message(
            chat_id=query.message.chat_id, 
            text="Не удалось отправить фото акции"
        )

# Обработчики для добавления акций
async def add_promotion_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления акции"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Только администратор может добавлять акции.")
        return ConversationHandler.END

    context.user_data["add_promotion"] = {"selected_shops": set()}
    await update.message.reply_text("Введите название акции:")
    return PROMO_NAME

async def handle_add_promotion_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка названия акции"""
    context.user_data["add_promotion"]["name"] = update.message.text
    await update.message.reply_text(
        "Введите даты начала и окончания акции через тире (например: 03.06.2025 - 31.07.2025):"
    )
    return PROMO_DATES

async def handle_add_promotion_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка дат акции"""
    try:
        dates_text = update.message.text.strip()
        parts = [p.strip() for p in dates_text.split("-")]
        if len(parts) != 2:
            raise ValueError("Неверный формат даты. Используйте формат: '03.06.2025 - 31.07.2025'")
        
        start_date = dateparser.parse(parts[0])
        end_date = dateparser.parse(parts[1])

        if not start_date or not end_date:
            raise ValueError("Не удалось распознать даты.")

        context.user_data["add_promotion"]["start_date"] = start_date.date().isoformat()
        context.user_data["add_promotion"]["end_date"] = end_date.date().isoformat()

        await update.message.reply_text("Введите описание акции:")
        return PROMO_DESC

    except Exception as e:
        logger.error(f"Ошибка при обработке дат: {e}")
        await update.message.reply_text(
            "Формат даты неверен. Введите даты в формате: '03.06.2025 - 31.07.2025'"
        )
        return PROMO_DATES

async def handle_add_promotion_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка описания акции"""
    context.user_data["add_promotion"]["description"] = update.message.text
    await update.message.reply_text("Отправьте изображение акции:")
    return PROMO_PHOTO

async def handle_add_promotion_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото акции"""
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте изображение.")
        return PROMO_PHOTO

    photo_file = await update.message.photo[-1].get_file()
    photo_path = f"photos/{update.message.photo[-1].file_id}.jpg"
    await photo_file.download_to_drive(photo_path)

    context.user_data["add_promotion"]["photo"] = photo_path
    await update.message.reply_text("Введите ссылку на акцию:")
    return PROMO_LINK

async def handle_add_promotion_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ссылки акции"""
    link = update.message.text.strip()
    if not link.startswith(('http://', 'https://')):
        await update.message.reply_text("Ссылка должна начинаться с http:// или https://")
        return PROMO_LINK
    
    context.user_data["add_promotion"]["link"] = link

    # Выбор магазинов
    buttons = []
    for cid, name in chat_ids.items():
        buttons.append([InlineKeyboardButton(name, callback_data=f"sendshop_{cid}")])

    buttons.append([
        InlineKeyboardButton("📢 Отправить во все", callback_data="sendshops_all"),
        InlineKeyboardButton("✅ Готово", callback_data="sendshops_done")
    ])
    return PROMO_SHOPS

async def handle_shop_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора магазинов"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "shops_done":
        selected = context.user_data["add_promotion"]["selected_shops"]
        if not selected:
            await query.message.edit_text("Вы не выбрали ни одного магазина.")
            return PROMO_SHOPS
        
        # Завершаем добавление
        promo_id = str(len(promotions) + 1)
        promo = context.user_data["add_promotion"]
        promo["shops"] = list(selected)
        promotions[promo_id] = promo
        save_data(promotions)
        await query.message.edit_text("✅ Акция успешно добавлена!")
        await notify_about_new_promotion(context, promo)
        return ConversationHandler.END
    
    # Добавление/удаление магазина
    shop_id = data.split("_")[1]
    selected_shops = context.user_data["add_promotion"]["selected_shops"]
    
    if shop_id in selected_shops:
        selected_shops.remove(shop_id)
    else:
        selected_shops.add(shop_id)
    
    # Обновляем интерфейс
    buttons = []
    for cid, name in chat_ids.items():
        mark = "✅ " if cid in selected_shops else ""
        buttons.append([InlineKeyboardButton(f"{mark}{name}", callback_data=f"shop_{cid}")])
    buttons.append([InlineKeyboardButton("✅ Готово", callback_data="shops_done")])
    
    try:
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.warning(f"Ошибка при обновлении клавиатуры: {e}")
    return PROMO_SHOPS

async def cancel_add_promotion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена добавления акции"""
    await update.message.reply_text("Добавление акции отменено.")
    return ConversationHandler.END

# Обработчики для удаления акций
async def delete_promotion_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало удаления акции"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Только администратор может удалять акции.")
        return
    
    keyboard = []
    for pid, promo in promotions.items():
        keyboard.append(
            InlineKeyboardButton(
                promo["name"], 
                callback_data=f"delete_{pid}"
            )
        )
    
    if not keyboard:
        await update.message.reply_text("Нет акций для удаления.")
        return
    
    reply_markup = InlineKeyboardMarkup(build_menu(keyboard, n_cols=1))
    await update.message.reply_text("Выберите акцию для удаления:", reply_markup=reply_markup)

async def handle_delete_promotion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора акции для удаления"""
    query = update.callback_query
    await query.answer()
    
    promo_id = query.data.split("_")[1]
    promotion = promotions.get(promo_id)
    
    if not promotion:
        await query.edit_message_text("Акция не найдена.")
        return
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑 Удалить", callback_data=f"confirm_delete_{promo_id}"),
            InlineKeyboardButton("Отмена", callback_data="cancel_delete")
        ]
    ])
    
    await query.edit_message_text(
        f"Вы уверены, что хотите удалить акцию '{promotion['name']}'?",
        reply_markup=keyboard
    )

async def confirm_delete_promotion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления акции"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith("confirm_delete"):
        promo_id = data.split("_")[2]
        
        if promo_id in promotions:
            # Удаляем файл с фото
            photo_path = promotions[promo_id].get("photo")
            if photo_path and os.path.exists(photo_path):
                try:
                    os.remove(photo_path)
                except Exception as e:
                    logger.error(f"Ошибка при удалении фото: {e}")
            
            # Удаляем акцию из базы
            del promotions[promo_id]
            save_data(promotions)
            
            await query.edit_message_text("Акция успешно удалена.")
        else:
            await query.edit_message_text("Акция уже удалена.")
    elif data == "cancel_delete":
        await query.edit_message_text("Удаление отменено.")

async def start_manual_promo_sending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Только администратор может рассылать акции.")
        return ConversationHandler.END

    if not promotions:
        await update.message.reply_text("Нет доступных акций для рассылки.")
        return ConversationHandler.END

    context.user_data["promo_sending"] = {}

    keyboard = [
        [InlineKeyboardButton(promo["name"], callback_data=f"sendpromo_{pid}")]
        for pid, promo in promotions.items()
    ]
    await update.message.reply_text(
        "Выберите акцию для ручной рассылки:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_PROMO_FOR_SENDING

# Обработчики для редактирования акций
async def edit_promotion_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало редактирования акции"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Только администратор может редактировать акции.")
        return ConversationHandler.END

    keyboard = []
    for pid, promo in promotions.items():
        keyboard.append(
            InlineKeyboardButton(
                promo["name"], 
                callback_data=f"edit_{pid}"
            )
        )
    
    if not keyboard:
        await update.message.reply_text("Нет акций для редактирования.")
        return ConversationHandler.END

    reply_markup = InlineKeyboardMarkup(build_menu(keyboard, n_cols=1))
    await update.message.reply_text("Выберите акцию для редактирования:", reply_markup=reply_markup)
    return EDIT_PROMO_SELECTION


async def handle_select_promo_for_sending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    promo_id = query.data.split("_")[1]
    if promo_id not in promotions:
        await query.edit_message_text("Акция не найдена.")
        return ConversationHandler.END

    context.user_data["promo_sending"] = {
        "promo_id": promo_id,
        "selected_shops": set()
    }

    buttons = []
    for cid, name in chat_ids.items():
        buttons.append([InlineKeyboardButton(name, callback_data=f"sendshop_{cid}")])

    buttons.append([
        InlineKeyboardButton("📢 Отправить во все", callback_data="sendshops_all"),
        InlineKeyboardButton("✅ Готово", callback_data="sendshops_done")
    ])

    await query.edit_message_text(
        "Выберите магазины, куда отправить акцию:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return SELECT_SHOPS_FOR_SENDING

async def handle_shop_selection_for_sending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    promo_id = context.user_data["promo_sending"]["promo_id"]
    selected = context.user_data["promo_sending"]["selected_shops"]

    if data == "sendshops_done":
        if not selected:
            await query.edit_message_text("Не выбрано ни одного магазина.")
            return SELECT_SHOPS_FOR_SENDING

        # Отправка акции в выбранные магазины
        promo = promotions[promo_id]
        for cid in selected:
            try:
                with open(promo["photo"], "rb") as photo:
                    await context.bot.send_photo(
                        chat_id=cid,
                        photo=photo,
                        caption=f"📣 Акция: {promo['name']}\n📅 Даты: {promo['start_date']} — {promo['end_date']}",
                        parse_mode="HTML"
                    )
            except Exception as e:
                logger.error(f"Ошибка при отправке в {cid}: {e}")

        await query.edit_message_text("✅ Акция успешно отправлена выбранным магазинам.")
        return ConversationHandler.END

    elif data == "sendshops_all":
        # Выбираем все магазины и сразу отправляем
        promo = promotions[promo_id]
        for cid in chat_ids.keys():
            try:
                with open(promo["photo"], "rb") as photo:
                    await context.bot.send_photo(
                        chat_id=int(cid),  # 👈 приведение к int
                        photo=photo,
                        caption=f"📣 Акция: {promo['name']}\n📅 Даты: {promo['start_date']} — {promo['end_date']}",
                        parse_mode="HTML"
                    )
            except Exception as e:
                logger.error(f"Ошибка при отправке в {cid}: {e}")

        await query.edit_message_text("✅ Акция успешно отправлена во все магазины.")
        return ConversationHandler.END

    else:
        # Обработка выбора конкретного магазина
        shop_id = data.split("_")[1]
        if shop_id in selected:
            selected.remove(shop_id)
        else:
            selected.add(shop_id)

    # Обновляем интерфейс
    buttons = []
    for cid, name in chat_ids.items():
        mark = "✅ " if cid in selected else ""
        buttons.append([InlineKeyboardButton(f"{mark}{name}", callback_data=f"sendshop_{cid}")])

    buttons.append([InlineKeyboardButton("📢 Отправить во все", callback_data="sendshops_all")])
    buttons.append([InlineKeyboardButton("✅ Готово", callback_data="sendshops_done")])

    try:
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Ошибка при обновлении клавиатуры: {e}")

    return SELECT_SHOPS_FOR_SENDING

async def handle_edit_promotion_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора акции для редактирования"""
    query = update.callback_query
    await query.answer()
    promo_id = query.data.split("_")[1]
    promotion = promotions.get(promo_id)
    
    if not promotion:
        await query.edit_message_text("Акция не найдена.")
        return ConversationHandler.END

    context.user_data["edit_promotion"] = {"promo_id": promo_id}
    current_shops = "\n".join([chat_ids.get(cid, "Неизвестный магазин") for cid in promotion.get("shops", [])])
    
    buttons = []
    for cid, name in chat_ids.items():
        mark = "✅ " if cid in promotion.get("shops", []) else ""
        buttons.append([InlineKeyboardButton(f"{mark}{name}", callback_data=f"edit_shop_{cid}")])
    buttons.append([InlineKeyboardButton("✅ Готово", callback_data="edit_shops_done")])

    await query.edit_message_text(
        f"Текущие магазины для акции '{promotion['name']}':\n{current_shops}\n\n"
        "Выберите магазины для изменения:"
    )
    await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
    return EDIT_SHOP_SELECTION

async def handle_edit_shop_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка изменения списка магазинов"""
    query = update.callback_query
    await query.answer()
    data = query.data

    promo_id = context.user_data["edit_promotion"]["promo_id"]
    promotion = promotions[promo_id]

    if data == "edit_shops_done":
        await query.edit_message_text("✅ Список магазинов успешно обновлен!")
        save_data(promotions)
        return ConversationHandler.END

    shop_id = data.split("_")[2]
    shops = promotion.setdefault("shops", [])
    
    if shop_id in shops:
        shops.remove(shop_id)
    else:
        shops.append(shop_id)

    buttons = []
    for cid, name in chat_ids.items():
        mark = "✅ " if cid in promotion.get("shops", []) else ""
        buttons.append([InlineKeyboardButton(f"{mark}{name}", callback_data=f"edit_shop_{cid}")])
    buttons.append([InlineKeyboardButton("✅ Готово", callback_data="edit_shops_done")])

    try:
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.warning(f"Ошибка при обновлении клавиатуры: {e}")

    return EDIT_SHOP_SELECTION

async def cancel_edit_promotion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена редактирования акции"""
    await update.message.reply_text("Редактирование отменено.")
    return ConversationHandler.END

# Уведомления
async def notify_about_new_promotion(context: ContextTypes.DEFAULT_TYPE, promotion):
    """Уведомление о новой акции"""
    for chat_id in promotion.get("shops", []):
        try:
            with open(promotion["photo"], "rb") as photo:
                await context.bot.send_photo(
                    chat_id=chat_id, 
                    photo=photo, 
                    caption = (
                        f"📣 Новая акция: {promotion['name']}\n"
                        f"📅 Даты проведения: {promotion['start_date']} — {promotion['end_date']}"
                    ),
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.warning(f"Ошибка отправки в чат {chat_id}: {e}")

async def notify_about_active_promotions(context: ContextTypes.DEFAULT_TYPE):
    # Логируем текущее время в московском часовом поясе
    moscow_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(moscow_tz)
    logger.info(f"Запуск рассылки актуальных акций в {now.strftime('%Y-%m-%d %H:%M:%S')} по московскому времени.")

    # Остальной код функции остаётся без изменений
    active_promotions = {pid: p for pid, p in promotions.items() if is_promotion_active(p)}
    logger.info(f"Найдено активных акций: {len(active_promotions)}")

    for promo_id, promo in active_promotions.items():
        logger.info(f"Обработка акции '{promo['name']}' (ID: {promo_id})")
        shops = promo.get("shops", [])
        logger.info(f"Акция связана с магазинами: {shops}")

        for chat_id in shops:
            try:
                logger.info(f"Отправка акции в чат {chat_id}...")
                with open(promo["photo"], "rb") as photo:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption = (
                            f"⏰ Напоминаем об акции: {promo['name']}\n"
                            f"📅 Даты проведения: {promo['start_date']} — {promo['end_date']}"
                        ),
                        parse_mode="HTML",
                    )
                logger.info(f"Акция успешно отправлена в чат {chat_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки в чат {chat_id}: {e}")
    
    logger.info("Завершение рассылки актуальных акций.")

async def notify_about_expiring_promotions(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Проверка акций на завершение через 3 дня...")
    
    # Получаем текущую дату
    now = datetime.now().date()
    
    for promo_id, promo in promotions.items():
        try:
            end_date = datetime.fromisoformat(promo["end_date"]).date()
            days_left = (end_date - now).days
            
            # Если до окончания акции осталось 3 дня
            if days_left == 3:
                logger.info(f"Акция '{promo['name']}' завершается через 3 дня.")
                
                # Отправляем уведомление в каждый связанный чат
                for chat_id in promo.get("shops", []):
                    try:
                        with open(promo["photo"], "rb") as photo:
                            await context.bot.send_photo(
                                chat_id=chat_id,
                                photo=photo,
                                caption=(
                                    f"⚠️ Внимание! Акция '{promo['name']}' завершается через 3 дня!\n"
                                    f"📅 Последний день: {promo['end_date']}"
                                ),
                                parse_mode="HTML",
                            )
                        logger.info(f"Уведомление об окончании акции отправлено в чат {chat_id}.")
                    except Exception as e:
                        logger.error(f"Ошибка отправки в чат {chat_id}: {e}")
        except Exception as e:
            logger.error(f"Ошибка при проверке акции {promo_id}: {e}")

async def notify_admin_about_expired_promotions(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Проверка завершившихся акций...")
    
    # Получаем текущую дату
    today = datetime.now().date()
    
    for promo_id, promo in promotions.copy().items():
        try:
            end_date = datetime.fromisoformat(promo["end_date"]).date()
            
            # Если акция завершилась сегодня
            if end_date == today:
                logger.info(f"Акция '{promo['name']}' завершилась сегодня.")
                
                # Отправляем уведомление администратору
                message = (
                    f"❌ Акция '{promo['name']}' завершилась.\n"
                    f"📅 Дата окончания: {promo['end_date']}"
                )
                await context.bot.send_message(chat_id=ADMIN_IDS, text=message)
                logger.info(f"Уведомление об окончании акции отправлено администратору.")
        except Exception as e:
            logger.error(f"Ошибка при проверке акции {promo_id}: {e}")

# Обработчик ошибок
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error("Exception while handling an update:", exc_info=context.error)

async def main():
    # Добавляем проверку существования токена
    if not TOKEN:
        logger.error("Токен не определен в config.py!")
        return
    
    if not ADMIN_IDS:
        logger.error("ID администратора не определен в config.py!")
        return
    
    application = Application.builder().token(TOKEN).build()
    
    # Регистрация обработчиков ошибок
    application.add_error_handler(error_handler)

    # Установка команд бота
    await application.bot.set_my_commands([
        ("start", "Запустить бота"),
        ("promotions", "Посмотреть акции"),
    ], scope=BotCommandScopeDefault())

    # Установка команд для администраторов
    for admin_id in ADMIN_IDS:
        try:
            await application.bot.set_my_commands([
                ("start", "Запустить бота"),
                ("promotions", "Посмотреть акции"),
                ("add_promotion", "Добавить акцию"),
                ("delete_promotion", "Удалить акцию"),
                ("edit_promotion", "Редактировать акцию"),
                ("send_promo", "Отправить акцию вручную"),
            ], scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:
            logger.error(f"Ошибка при установке команд для админа {admin_id}: {e}")

    manual_send_handler = ConversationHandler(
        entry_points=[CommandHandler("send_promo", start_manual_promo_sending)],
        states={
            SELECT_PROMO_FOR_SENDING: [
                CallbackQueryHandler(handle_select_promo_for_sending, pattern=r"^sendpromo_")
            ],
            SELECT_SHOPS_FOR_SENDING: [
                CallbackQueryHandler(handle_shop_selection_for_sending, pattern=r"^(sendshop_|sendshops_done|sendshops_all)")
            ]
        },
        fallbacks=[]
    )
    application.add_handler(manual_send_handler)
    # Обработчики команд
    application.add_handler(CommandHandler("promotions", view_promotions))
    application.add_handler(CommandHandler("delete_promotion", delete_promotion_start))
    
    # Обработчики callback-запросов
    application.add_handler(CallbackQueryHandler(handle_promotion_selection, pattern=r"^promo_"))
    application.add_handler(CallbackQueryHandler(handle_delete_promotion, pattern=r"^delete_"))
    application.add_handler(CallbackQueryHandler(confirm_delete_promotion, pattern=r"^(confirm_delete_|cancel_delete)"))
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add_promotion", add_promotion_start)],
        states={
            PROMO_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_promotion_name)],
            PROMO_DATES: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_promotion_dates)],
            PROMO_PHOTO: [MessageHandler(filters.PHOTO, handle_add_promotion_photo)],
            PROMO_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_promotion_link)],
            PROMO_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_promotion_description)],
            PROMO_SHOPS: [CallbackQueryHandler(handle_shop_selection, pattern=r"^(shop_|shops_done)")]
        },
        fallbacks=[CommandHandler("cancel", cancel_add_promotion)]
    )
    application.add_handler(conv_handler)
    
    # ConversationHandler для регистрации магазинов
    store_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            "WAITING_FOR_STORE_NAME": [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_store_name)]
        },
        fallbacks=[CommandHandler("cancel", cancel_add_promotion)]
    )
    application.add_handler(store_conv_handler)
    
    # ConversationHandler для редактирования акций
    edit_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("edit_promotion", edit_promotion_start)],
        states={
            EDIT_PROMO_SELECTION: [CallbackQueryHandler(handle_edit_promotion_selection, pattern=r"^edit_")],
            EDIT_SHOP_SELECTION: [CallbackQueryHandler(handle_edit_shop_selection, pattern=r"^(edit_shop_|edit_shops_done)")]
        },
        fallbacks=[CommandHandler("cancel", cancel_edit_promotion)]
    )
    application.add_handler(edit_conv_handler)
    
    # Получаем планировщик
    job_queue = application.job_queue

    # Устанавливаем время для рассылки в московском часовом поясе
    moscow_tz = pytz.timezone("Europe/Moscow")
    scheduled_time = time(hour=10, minute=0, tzinfo=moscow_tz)
    # Добавляем задачу в планировщик
    job_queue.run_daily(
        notify_about_active_promotions,
        time=scheduled_time,
        days=(0, 1, 2, 3, 4, 5, 6)  # Каждый день
    )

    # Уведомление администратора о завершении акций
    job_queue.run_daily(
        notify_admin_about_expired_promotions,
        time=time(hour=0, minute=0, tzinfo=timezone("Europe/Moscow")),
        days=(0, 1, 2, 3, 4, 5, 6)
    )
    logger.info("Планировщик уведомлений настроен на 10:00 по московскому времени.")

    # Запуск бота
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())