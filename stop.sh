#!/bin/bash

# Скрипт для остановки бота и вебхук сервера

echo "🛑 Остановка системы VPN бота..."

# Останавливаем вебхук сервер
if [ -f "webhook.pid" ]; then
    PID=$(cat webhook.pid)
    
    if kill -0 $PID 2>/dev/null; then
        echo "🛑 Остановка вебхук сервера (PID: $PID)..."
        kill $PID
        sleep 2
        
        if kill -0 $PID 2>/dev/null; then
            echo "⚠️  Вебхук сервер не остановился, принудительная остановка..."
            kill -9 $PID
        fi
        
        echo "✅ Вебхук сервер остановлен"
    else
        echo "ℹ️  Вебхук сервер с PID $PID не найден"
    fi
    
    rm webhook.pid
else
    echo "ℹ️  Файл webhook.pid не найден"
fi

# Останавливаем Telegram бота
if [ -f "bot.pid" ]; then
    PID=$(cat bot.pid)
    
    if kill -0 $PID 2>/dev/null; then
        echo "🛑 Остановка Telegram бота (PID: $PID)..."
        kill $PID
        sleep 2
        
        if kill -0 $PID 2>/dev/null; then
            echo "⚠️  Telegram бот не остановился, принудительная остановка..."
            kill -9 $PID
        fi
        
        echo "✅ Telegram бот остановлен"
    else
        echo "ℹ️  Telegram бот с PID $PID не найден"
    fi
    
    rm bot.pid
else
    echo "ℹ️  Файл bot.pid не найден"
fi

# Также останавливаем процессы по имени (на всякий случай)
pkill -f "python bot/webhook_service.py" 2>/dev/null && echo "✅ Остановлены процессы webhook_service.py"
pkill -f "python bot/bot.py" 2>/dev/null && echo "✅ Остановлены процессы bot.py"

echo "✅ Система полностью остановлена!"
