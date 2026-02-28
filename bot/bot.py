import logging
import asyncio
import threading
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from config import config
from database import db
from wg_manager import wg_manager
from payments import payment_manager
import keyboards
from instructions import get_instruction_text, get_all_instructions_text
from webhook_handler import webhook_handler, set_telegram_app

# Настройка логирования
import os
os.makedirs('logs', exist_ok=True)

# Создаем форматтер
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Настройка корневого логгера
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Обработчик для файла
file_handler = logging.FileHandler('logs/bot.log', encoding='utf-8')
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

# Обработчик для консоли
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)


def run_webhook_server():
    """Запускает webhook сервер в отдельном потоке"""
    try:
        logger.info("Starting webhook server in background thread...")
        # handle_signals=False - отключаем обработку сигналов для работы в потоке
        webhook_handler.run(host='0.0.0.0', port=8080, handle_signals=False)
    except Exception as e:
        logger.error(f"Webhook server error: {e}")

# Проверка админа
def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Создаем пользователя в БД
    await db.create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    sub = await db.get_active_subscription(user.id)
    
    welcome_text = f"""
👋 Привет, {user.first_name}!

🛡️ <b>WireGuard VPN Bot</b>

💎 <b>Тарифы подписки:</b>
• 1 месяц — <b>1000₽</b>
• 6 месяцев — <b>5000₽</b> (экономия 1000₽)
• 12 месяцев — <b>9000₽</b> (экономия 3000₽)

📱 <b>Что включено:</b>
• До 3 устройств одновременно
• Безлимитный трафик
• Высокая скорость
• Поддержка 24/7

{'✅ У вас активная подписка!' if sub else '❌ Подписка не активна'}
"""
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=keyboards.get_main_menu(is_admin(user.id), bool(sub)),
        parse_mode='HTML'
    )

# Обработка кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if data == 'main_menu':
        await show_main_menu(query, user_id)
    
    elif data == 'buy_subscription':
        await show_subscription_plans(query)
    
    elif data.startswith('select_plan_'):
        plan_id = data.replace('select_plan_', '')
        await process_plan_selection(query, user_id, plan_id, context)
    
    elif data == 'get_configs':
        await handle_get_configs(query, user_id, context)
    
    elif data == 'my_configs':
        await show_my_configs(query, user_id)
    
    elif data == 'instructions':
        await show_instructions_menu(query)
    
    elif data.startswith('instr_'):
        device = data.replace('instr_', '')
        await show_instruction(query, device)
    
    elif data == 'help':
        await show_help(query)
    
    elif data == 'check_payment':
        await check_payment_status(query, user_id, context)
    
    elif data.startswith('admin_'):
        if not is_admin(user_id):
            await query.edit_message_text("⛔ Доступ запрещен")
            return
        await handle_admin(query, data, user_id)

async def show_main_menu(query, user_id: int):
    sub = await db.get_active_subscription(user_id)
    configs_count = await db.get_configs_count(user_id)
    
    sub_text = ""
    if sub:
        expires = sub['expires_at'][:10] if isinstance(sub['expires_at'], str) else sub['expires_at'].strftime('%d.%m.%Y')
        sub_text = f"\n✅ Подписка активна до: <b>{expires}</b>"
    else:
        sub_text = "\n❌ Нет активной подписки"
    
    text = f"""
🏠 <b>Главное меню</b>

📊 Конфигов создано: <b>{configs_count}/3</b>{sub_text}
"""
    await query.edit_message_text(
        text,
        reply_markup=keyboards.get_main_menu(is_admin(user_id), bool(sub)),
        parse_mode='HTML'
    )

async def show_subscription_plans(query):
    text = """
💎 <b>Выберите тариф подписки:</b>

🗓 <b>1 месяц — 1000₽</b>
   Доступ на 30 дней

🗓 <b>6 месяцев — 5000₽</b>
   Доступ на 180 дней
   💰 Экономия 1000₽ (17%)

🗓 <b>12 месяцев — 9000₽</b>
   Доступ на 365 дней  
   💰 Экономия 3000₽ (25%)

<b>Все тарифы включают:</b>
✓ До 3 устройств
✓ Безлимитный трафик
✓ Поддержка 24/7
"""
    await query.edit_message_text(
        text,
        reply_markup=keyboards.get_subscription_plans_keyboard(),
        parse_mode='HTML'
    )

async def process_plan_selection(query, user_id: int, plan_id: str, context: ContextTypes.DEFAULT_TYPE):
    plan = config.SUBSCRIPTION_PLANS.get(plan_id)
    if not plan:
        await query.answer("Ошибка: тариф не найден")
        return
    
    # Создаем подписку в БД (пока неактивную)
    sub_id = await db.create_subscription(user_id, plan_id, plan['price'], plan['days'])
    
    # Создаем платеж в ЮKassa
    payment = await payment_manager.create_payment(
        user_id=user_id,
        amount=plan['price'],
        description=f"Подписка {plan['name']} для пользователя {user_id}"
    )
    
    # Сохраняем в БД
    await db.create_payment(user_id, sub_id, payment['payment_id'], plan['price'], plan_id)
    
    # Сохраняем в контексте для проверки
    context.user_data['pending_payment_id'] = payment['payment_id']
    context.user_data['pending_sub_id'] = sub_id
    
    text = f"""
💳 <b>Оплата подписки</b>

📦 Товар: Подписка {plan['name']}
💰 Стоимость: <b>{plan['price']}₽</b>
📅 Срок: {plan['days']} дней

Нажмите кнопку ниже для оплаты через ЮKassa (карта, СБП, ЮMoney)
"""
    await query.edit_message_text(
        text,
        reply_markup=keyboards.get_payment_keyboard(payment['confirmation_url']),
        parse_mode='HTML'
    )

async def handle_get_configs(query, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем подписку
    sub = await db.get_active_subscription(user_id)
    
    if not is_admin(user_id) and not sub:
        await query.edit_message_text(
            "❌ У вас нет активной подписки.\nСначала оформите подписку в разделе 'Купить подписку'.",
            reply_markup=keyboards.get_back_button()
        )
        return
    
    # Проверяем лимит конфигов
    configs_count = await db.get_configs_count(user_id)
    if configs_count >= config.MAX_CONFIGS_PER_USER:
        # Получаем старые конфиги для удаления пиров с сервера
        old_configs = await db.get_user_configs(user_id)
        
        # Удаляем пиров с сервера AmneziaWG
        for cfg in old_configs:
            try:
                # Удаляем пира с сервера
                import subprocess
                subprocess.run([
                    'sudo', 'awg', 'set', 'wg0',
                    'peer', cfg['public_key'], 'remove'
                ], check=False, capture_output=True)
                logger.info(f"Removed peer {cfg['public_key'][:8]}... from server")
            except Exception as e:
                logger.error(f"Error removing peer from server: {e}")
        
        # Удаляем старые конфиги из базы
        await db.delete_user_configs(user_id)
        
        # Удаляем файлы конфигов
        import os
        import glob
        for conf_file in glob.glob(f"wg_configs/user_{user_id}_*.conf"):
            try:
                os.remove(conf_file)
            except:
                pass
        for png_file in glob.glob(f"wg_configs/user_{user_id}_*.png"):
            try:
                os.remove(png_file)
            except:
                pass
    
    await generate_configs(query, user_id, context)

async def generate_configs(query, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    await query.edit_message_text("⏳ Генерирую новые конфигурации с маскировкой трафика...")
    
    for i in range(1, 4):  # 3 конфига
        try:
            config_data = wg_manager.generate_config(user_id, i)
            
            await db.add_config(
                user_id=user_id,
                config_name=config_data['config_name'],
                private_key=config_data['private_key'],
                public_key=config_data['public_key'],
                preshared_key=config_data['preshared_key'],
                address=config_data['address']
            )
            
            # Отправляем файл
            with open(config_data['config_path'], 'rb') as f:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=f,
                    filename=f"wg_config_{i}.conf",
                    caption=f"🔐 Конфигурация #{i} (с маскировкой AmneziaWG)\n📱 Имя: {config_data['config_name']}\n🌐 IP: {config_data['address']}\n🔧 Порт: 51820"
                )
            
            # QR код
            try:
                qr_path = wg_manager.generate_qr(config_data['config_path'])
                if qr_path.endswith('.png'):
                    with open(qr_path, 'rb') as f:
                        await context.bot.send_photo(
                            chat_id=user_id,
                            photo=f,
                            caption=f"📱 QR-код для конфига #{i}"
                        )
            except Exception as e:
                logger.error(f"QR error: {e}")
                
        except Exception as e:
            logger.error(f"Config error: {e}")
            await query.message.reply_text(f"❌ Ошибка при генерации конфига #{i}")
    
    # Инструкции
    instructions = """
✅ <b>Ваши новые конфигурации готовы!</b>

<b>⚠️ ВАЖНО:</b> Старые конфиги удалены! Используйте только новые файлы.

<b>Ключевые изменения:</b>
• Используется порт <b>51820</b> (стандартный WireGuard)
• Добавлена маскировка трафика AmneziaWG
• Улучшена стабильность соединения

<b>Как подключиться:</b>
1️⃣ Установите приложение WireGuard или AmneziaVPN
2️⃣ Импортируйте файл .conf или отсканируйте QR-код
3️⃣ Включите VPN

<b>Рекомендуемые приложения:</b>
• Android/iOS: AmneziaVPN (лучшая совместимость)
• Windows/Mac: WireGuard с официального сайта
• Linux: wireguard-tools через пакетный менеджер

<b>📖 Нужна помощь с настройкой?</b> 
Нажмите "Инструкции" в главном меню — там есть гайды для всех устройств!
"""
    await context.bot.send_message(
        chat_id=user_id,
        text=instructions,
        parse_mode='HTML',
        reply_markup=keyboards.get_back_button()
    )

async def show_my_configs(query, user_id: int):
    configs = await db.get_user_configs(user_id)
    sub = await db.get_active_subscription(user_id)
    
    if not configs:
        await query.edit_message_text(
            "❌ У вас пока нет конфигураций.\nНажмите 'Получить конфиги' для создания.",
            reply_markup=keyboards.get_back_button()
        )
        return
    
    text = "📱 <b>Ваши конфигурации:</b>\n\n"
    for i, cfg in enumerate(configs, 1):
        text += f"{i}. <code>{cfg['config_name']}</code>\n"
        text += f"   🌐 IP: <code>{cfg['address']}</code>\n"
        text += f"   📅 Создан: {cfg['created_at'][:10]}\n\n"
    
    if sub:
        expires = sub['expires_at'][:10] if isinstance(sub['expires_at'], str) else sub['expires_at'].strftime('%d.%m.%Y')
        text += f"\n✅ Подписка активна до: {expires}"
    
    await query.edit_message_text(
        text, 
        reply_markup=keyboards.get_back_button(), 
        parse_mode='HTML'
    )

async def show_instructions_menu(query):
    text = """
📖 <b>Инструкции по настройке</b>

Выберите ваше устройство для получения подробной инструкции:

📱 <b>Мобильные:</b> iOS, Android
💻 <b>Компьютеры:</b> Windows, macOS, Linux  
📡 <b>Роутеры:</b> Keenetic, OpenWrt, другие

<b>💡 Совет:</b> На роутере VPN будет работать для всех устройств дома автоматически!
"""
    await query.edit_message_text(
        text,
        reply_markup=keyboards.get_instructions_keyboard(),
        parse_mode='HTML'
    )

async def show_instruction(query, device: str):
    text = get_instruction_text(device)
    await query.edit_message_text(
        text,
        reply_markup=keyboards.get_back_button('instructions'),
        parse_mode='HTML'
    )

async def show_help(query):
    text = f"""
❓ <b>Помощь и поддержка</b>

<b>Частые вопросы:</b>

<b>Q: Сколько устройств можно подключить?</b>
A: До 3 устройств одновременно на одну подписку.

<b>Q: Можно ли использовать на роутере?</b>
A: Да! Keenetic, OpenWrt, Padavan и другие поддерживаются.

<b>Q: Что делать если подписка закончилась?</b>
A: Конфиги перестанут работать. Оформите новую подписку.

<b>Q: Можно ли продлить подписку заранее?</b>
A: Да, новая подписка добавится к оставшимся дням.

<b>Q: Почему низкая скорость?</b>
A: Проверьте ближайший сервер, попробуйте другой конфиг.

<b>📖 Детальные инструкции:</b> Нажмите "Инструкции" в меню

<b>👨‍💻 Не нашли ответ?</b> Напишите в поддержку!
"""
    await query.edit_message_text(
        text,
        reply_markup=keyboards.get_help_keyboard(),
        parse_mode='HTML'
    )

async def check_payment_status(query, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    payment_id = context.user_data.get('pending_payment_id')
    
    if not payment_id:
        await query.answer("Нет активных платежей")
        return
    
    try:
        status = await payment_manager.check_payment(payment_id)
        
        if status['status'] == 'succeeded':
            # Подтверждаем в БД
            await db.confirm_payment(payment_id)
            await query.edit_message_text(
                "✅ <b>Оплата прошла успешно!</b>\n\nПодписка активирована. Теперь вы можете получить конфиги.",
                reply_markup=keyboards.get_back_button(),
                parse_mode='HTML'
            )
        else:
            await query.answer("⏳ Оплата еще не поступила. Попробуйте позже.", show_alert=True)
            
    except Exception as e:
        logger.error(f"Payment check error: {e}")
        await query.answer("Ошибка проверки платежа", show_alert=True)

async def handle_admin(query, data: str, user_id: int):
    if data == 'admin_panel':
        await query.edit_message_text(
            "🔐 <b>Админ панель</b>",
            reply_markup=keyboards.get_admin_keyboard(),
            parse_mode='HTML'
        )
    
    elif data == 'admin_stats':
        stats = await db.get_subscription_stats()
        text = f"""
📊 <b>Статистика бота</b>

👥 Всего пользователей: <b>{stats['total_users']}</b>
💎 Активных подписок: <b>{stats['active_subscriptions']}</b>
💰 Общая выручка: <b>{stats['total_revenue']}₽</b>
"""
        await query.edit_message_text(text, reply_markup=keyboards.get_admin_keyboard())

def main():
    # Инициализация базы данных
    asyncio.get_event_loop().run_until_complete(db.init())
    
    # Создание приложения
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Передаем приложение в webhook handler для отправки уведомлений
    set_telegram_app(application)
    
    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запускаем webhook сервер в отдельном потоке
    webhook_thread = threading.Thread(target=run_webhook_server, daemon=True)
    webhook_thread.start()
    logger.info("Webhook server thread started")
    
    # Запуск бота
    logger.info("Starting Telegram bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
