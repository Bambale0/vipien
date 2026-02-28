#!/bin/bash

# Скрипт для запуска VPN бота с интегрированным вебхук сервером
# Вебхук сервер теперь запускается внутри процесса бота для отправки уведомлений

cd /opt/wg-bot

echo "🚀 Запуск системы VPN бота..."

# Проверяем, установлено ли виртуальное окружение
if [ ! -d "venv" ]; then
    echo "❌ Ошибка: виртуальное окружение не найдено. Создайте его:"
    echo "   python3 -m venv venv"
    echo "   source venv/bin/activate"
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Активируем виртуальное окружение
source venv/bin/activate

# Останавливаем предыдущие процессы
if [ -f "bot.pid" ]; then
    echo "🛑 Останавливаем предыдущий процесс бота..."
    ./stop.sh
    sleep 2
fi

# Проверяем зависимости
echo "🔍 Проверка зависимостей..."
python -c "import yookassa, aiohttp, telegram" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️ Не все зависимости установлены. Устанавливаем..."
    pip install -q -r requirements.txt
fi

echo ""
echo "✅ Конфигурация:"
echo "   - Webhook сервер будет запущен на порту 8080"
echo "   - URL для ЮKassa: https://vpn.chillcreative.ru/webhook/yookassa"
echo "   - Поддерживаемые события: payment.succeeded, payment.canceled, payment.waiting_for_capture, refund.succeeded"
echo ""

# Запускаем бота с интегрированным вебхук сервером
echo "🤖 Запуск Telegram бота с вебхук сервером..."
python bot/bot.py &
BOT_PID=$!
echo $BOT_PID > bot.pid

# Ждем запуска сервисов
sleep 3

# Проверяем, что процесс запустился
if ps -p $BOT_PID > /dev/null; then
    echo ""
    echo "✅ Система успешно запущена!"
    echo "📊 Bot PID: $BOT_PID"
    echo "🌐 Webhook URL: https://vpn.chillcreative.ru/webhook/yookassa"
    echo "🩺 Health Check: http://localhost:8080/health"
    echo ""
    echo "📋 Логи: tail -f /opt/wg-bot/logs/bot.log (если настроено)"
    echo "🛑 Для остановки: ./stop.sh"
else
    echo "❌ Ошибка: не удалось запустить бота"
    exit 1
fi
