from config import config
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_main_menu(is_admin: bool = False, has_subscription: bool = False):
    keyboard = [
        [InlineKeyboardButton("💎 Купить подписку", callback_data="buy_subscription")],
    ]

    if has_subscription:
        keyboard.append(
            [InlineKeyboardButton("🚀 Получить конфиги", callback_data="get_configs")]
        )
        keyboard.append(
            [InlineKeyboardButton("📱 Мои конфиги", callback_data="my_configs")]
        )

    keyboard.append(
        [InlineKeyboardButton("💳 Управление картой", callback_data="manage_card")]
    )

    keyboard.append(
        [InlineKeyboardButton("📖 Инструкции", callback_data="instructions")]
    )
    keyboard.append([InlineKeyboardButton("❓ Помощь", callback_data="help")])

    if is_admin:
        pass

    return InlineKeyboardMarkup(keyboard)


def get_manage_card_keyboard(card_type: str = "", card_last4: str = "", has_card: bool = True):
    label = f"🗑 Отвязать карту {card_type} *{card_last4}" if has_card else "🗑 Отвязать карту"
    keyboard = [
        [InlineKeyboardButton(label, callback_data="detach_card")],
        [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_detach_card_confirm_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, отвязать", callback_data="detach_card_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="manage_card"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_subscription_plans_keyboard():
    keyboard = []
    for plan_id, plan in config.SUBSCRIPTION_PLANS.items():
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"💎 {plan['name']} — {plan['price']}₽",
                    callback_data=f"select_plan_{plan_id}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


def get_payment_keyboard(payment_url: str):
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", url=payment_url)],
        [InlineKeyboardButton("🔄 Проверить оплату", callback_data="check_payment")],
        [InlineKeyboardButton("◀️ Назад", callback_data="buy_subscription")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_instructions_keyboard():
    keyboard = [
        [InlineKeyboardButton("📱 iPhone / iPad", callback_data="instr_ios")],
        [InlineKeyboardButton("🤖 Android", callback_data="instr_android")],
        [InlineKeyboardButton("💻 Windows", callback_data="instr_windows")],
        [InlineKeyboardButton("🍎 macOS", callback_data="instr_macos")],
        [InlineKeyboardButton("🌐 Linux", callback_data="instr_linux")],
        [InlineKeyboardButton("📡 Keenetic (роутер)", callback_data="instr_keenetic")],
        [InlineKeyboardButton("📟 Другие роутеры", callback_data="instr_routers")],
        [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_help_keyboard():
    keyboard = []
    if config.SUPPORT_LINK:
        keyboard.append(
            [InlineKeyboardButton("👨‍💻 Техподдержка", url=config.SUPPORT_LINK)]
        )
    if config.CHANNEL_LINK:
        keyboard.append([InlineKeyboardButton("📢 Наш канал", url=config.CHANNEL_LINK)])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


def get_back_button(callback_data="main_menu"):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("◀️ Назад", callback_data=callback_data)]]
    )


def get_users_list_keyboard(users: list, page: int, total_pages: int):
    keyboard = []
    for u in users:
        name = u.get("username") or u.get("first_name") or str(u["user_id"])
        has_sub = bool(u.get("sub_expires"))
        icon = "✅" if has_sub else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{icon} {name} (id: {u['user_id']})",
                callback_data=f"admin_user_{u['user_id']}",
            )
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"admin_users_page_{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"admin_users_page_{page + 1}"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)


def get_user_details_keyboard(user_id: int, has_sub: bool):
    keyboard = [
        [InlineKeyboardButton("🎁 Выдать подписку", callback_data=f"admin_give_sub_select_{user_id}")],
    ]
    if has_sub:
        keyboard.append([
            InlineKeyboardButton("🚫 Отозвать подписку", callback_data=f"admin_revoke_sub_{user_id}")
        ])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_users_page_0")])
    return InlineKeyboardMarkup(keyboard)


def get_give_sub_plan_keyboard(user_id: int):
    keyboard = []
    for plan_id, plan in config.SUBSCRIPTION_PLANS.items():
        keyboard.append([
            InlineKeyboardButton(
                f"🎁 {plan['name']} ({plan['days']} дней)",
                callback_data=f"admin_give_sub_confirm_{plan_id}_{user_id}",
            )
        ])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data=f"admin_user_{user_id}")])
    return InlineKeyboardMarkup(keyboard)


def get_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [
            InlineKeyboardButton(
                "👥 Управление пользователями", callback_data="admin_users"
            )
        ],
        [
            InlineKeyboardButton(
                "🎁 Выдать подписку (бесплатно)", callback_data="admin_give_sub"
            )
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)
