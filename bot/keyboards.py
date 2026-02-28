from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import config

def get_main_menu(is_admin: bool = False, has_subscription: bool = False):
    keyboard = [
        [InlineKeyboardButton("💎 Купить подписку", callback_data='buy_subscription')],
    ]
    
    if has_subscription:
        keyboard.append([InlineKeyboardButton("🚀 Получить конфиги", callback_data='get_configs')])
        keyboard.append([InlineKeyboardButton("📱 Мои конфиги", callback_data='my_configs')])
    
    keyboard.append([InlineKeyboardButton("📖 Инструкции", callback_data='instructions')])
    keyboard.append([InlineKeyboardButton("❓ Помощь", callback_data='help')])
    
    if is_admin:
        pass
    
    return InlineKeyboardMarkup(keyboard)

def get_subscription_plans_keyboard():
    keyboard = []
    for plan_id, plan in config.SUBSCRIPTION_PLANS.items():
        keyboard.append([
            InlineKeyboardButton(
                f"💎 {plan['name']} — {plan['price']}₽", 
                callback_data=f"select_plan_{plan_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='main_menu')])
    return InlineKeyboardMarkup(keyboard)

def get_payment_keyboard(payment_url: str):
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", url=payment_url)],
        [InlineKeyboardButton("🔄 Проверить оплату", callback_data='check_payment')],
        [InlineKeyboardButton("◀️ Назад", callback_data='buy_subscription')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_instructions_keyboard():
    keyboard = [
        [InlineKeyboardButton("📱 iPhone / iPad", callback_data='instr_ios')],
        [InlineKeyboardButton("🤖 Android", callback_data='instr_android')],
        [InlineKeyboardButton("💻 Windows", callback_data='instr_windows')],
        [InlineKeyboardButton("🍎 macOS", callback_data='instr_macos')],
        [InlineKeyboardButton("🌐 Linux", callback_data='instr_linux')],
        [InlineKeyboardButton("📡 Keenetic (роутер)", callback_data='instr_keenetic')],
        [InlineKeyboardButton("📟 Другие роутеры", callback_data='instr_routers')],
        [InlineKeyboardButton("◀️ Назад", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_help_keyboard():
    keyboard = []
    if config.SUPPORT_LINK:
        keyboard.append([InlineKeyboardButton("👨‍💻 Техподдержка", url=config.SUPPORT_LINK)])
    if config.CHANNEL_LINK:
        keyboard.append([InlineKeyboardButton("📢 Наш канал", url=config.CHANNEL_LINK)])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='main_menu')])
    return InlineKeyboardMarkup(keyboard)

def get_back_button(callback_data='main_menu'):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад", callback_data=callback_data)]
    ])

def get_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')],
        [InlineKeyboardButton("👥 Управление пользователями", callback_data='admin_users')],
        [InlineKeyboardButton("🎁 Выдать подписку (бесплатно)", callback_data='admin_give_sub')],
        [InlineKeyboardButton("◀️ Назад", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)