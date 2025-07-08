
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime

def format_pace(pace):
    return f"{pace:.2f} км/ч"

def build_month_keyboard():
    keyboard = []
    current_month = datetime.now().month
    for month in range(1, 13):
        label = datetime(2025, month, 1).strftime('%B')
        if month == current_month:
            keyboard.append([InlineKeyboardButton(f"✅ {label}", callback_data=str(month))])
        else:
            keyboard.append([InlineKeyboardButton(label, callback_data=str(month))])
    return InlineKeyboardMarkup(keyboard)
