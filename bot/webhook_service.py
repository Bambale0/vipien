#!/usr/bin/env python3
"""
Сервис для запуска вебхук сервера ЮKassa

Этот скрипт запускает вебхук сервер на порту 8080 для обработки
платежных уведомлений от ЮKassa.

Может работать в двух режимах:
1. Standalone - только webhook сервер (без уведомлений в Telegram)
2. Integrated - запускается из bot.py вместе с ботом
"""

import logging
import os
import sys

# Добавляем путь к проекту
sys.path.insert(0, "/opt/wg-bot")

from webhook_handler import set_telegram_app, webhook_handler

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def run_standalone(host="0.0.0.0", port=8080):
    """
    Запускает вебхук сервер в standalone режиме.

    В этом режиме webhook обрабатывает платежи, но не отправляет
    уведомления в Telegram (так как бот запущен отдельно).
    """
    logger.info("🚀 Запуск вебхук сервера ЮKassa (standalone режим)")
    logger.info(
        f"📍 Вебхуки будут доступны по адресу: http://{host}:{port}/webhook/yookassa"
    )
    logger.info("⚠️ Уведомления в Telegram не будут отправляться в standalone режиме")

    try:
        webhook_handler.run(host=host, port=port)
    except KeyboardInterrupt:
        logger.info("🛑 Вебхук сервер остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска вебхук сервера: {e}")
        sys.exit(1)


def main():
    """Запуск вебхук сервера в standalone режиме"""
    import argparse

    parser = argparse.ArgumentParser(description="YooKassa Webhook Server")
    parser.add_argument("--host", default="0.0.0.0", help="Хост для прослушивания")
    parser.add_argument("--port", type=int, default=8080, help="Порт для прослушивания")
    parser.add_argument(
        "--standalone", action="store_true", help="Запуск в standalone режиме"
    )

    args = parser.parse_args()

    run_standalone(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
