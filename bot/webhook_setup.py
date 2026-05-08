import json

import requests
from config import config
from yookassa import Configuration

# Настройка ЮKassa
Configuration.account_id = config.YOOKASSA_SHOP_ID
Configuration.secret_key = config.YOOKASSA_SECRET_KEY


def setup_webhook():
    """
    Настройка вебхука в ЮKassa

    Вебхуки будут приходить на:
    https://vpn.chillcreative.ru/webhook/yookassa
    """

    webhook_url = "https://vpn.chillcreative.ru/webhook/yookassa"

    # События, на которые будем получать вебхуки
    events = ["payment.succeeded", "payment.canceled", "payment.waiting_for_capture"]

    try:
        # Создаем вебхук
        from yookassa import Webhook

        webhook = Webhook.create({"event": events, "url": webhook_url})

        print(f"✅ Вебхук успешно создан!")
        print(f"ID вебхука: {webhook.id}")
        print(f"URL: {webhook.url}")
        print(f"События: {webhook.event}")

        return webhook

    except Exception as e:
        print(f"❌ Ошибка создания вебхука: {e}")
        return None


def list_webhooks():
    """Просмотр существующих вебхуков"""
    try:
        from yookassa import Webhook

        webhooks = Webhook.list()

        print("📋 Существующие вебхуки:")
        for webhook in webhooks:
            print(f"ID: {webhook.id}")
            print(f"URL: {webhook.url}")
            print(f"События: {webhook.event}")
            print(f"Статус: {webhook.status}")
            print("-" * 40)

        return webhooks

    except Exception as e:
        print(f"❌ Ошибка получения вебхуков: {e}")
        return None


def delete_webhook(webhook_id):
    """Удаление вебхука"""
    try:
        from yookassa import Webhook

        result = Webhook.remove(webhook_id)

        if result:
            print(f"✅ Вебхук {webhook_id} успешно удален")
        else:
            print(f"❌ Не удалось удалить вебхук {webhook_id}")

    except Exception as e:
        print(f"❌ Ошибка удаления вебхука: {e}")


if __name__ == "__main__":
    print("🔧 Настройка вебхуков ЮKassa")
    print("=" * 50)

    # Просмотр существующих вебхуков
    print("\n1. Просмотр существующих вебхуков:")
    list_webhooks()

    # Создание нового вебхука
    print("\n2. Создание вебхука:")
    setup_webhook()

    # Повторный просмотр
    print("\n3. Проверка созданных вебхуков:")
    list_webhooks()

    print("\n✅ Настройка вебхуков завершена!")
    print(f"Вебхуки будут приходить на: {config.WG_ENDPOINT}/webhook/yookassa")
