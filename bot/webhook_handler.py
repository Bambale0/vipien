import asyncio
import ipaddress
import json
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime
from uuid import UUID

import aiosqlite
import requests
from aiohttp import web
from config import config
from database import db
from yookassa import Configuration, Webhook

# Настройка логирования
logger = logging.getLogger(__name__)

# Настройка ЮKassa
Configuration.account_id = config.YOOKASSA_SHOP_ID
Configuration.secret_key = config.YOOKASSA_SECRET_KEY

# Разрешенные IP-адреса ЮKassa (согласно документации)
YOOKASSA_IP_RANGES = [
    ipaddress.ip_network("185.71.76.0/27"),
    ipaddress.ip_network("185.71.77.0/27"),
    ipaddress.ip_network("77.75.153.0/25"),
    ipaddress.ip_network("77.75.154.128/25"),
    ipaddress.ip_network("2a02:5180::/32"),
]
# Отдельные IP-адреса
YOOKASSA_IPS = [
    ipaddress.ip_address("77.75.156.11"),
    ipaddress.ip_address("77.75.156.35"),
]

# Telegram Bot Application (будет установлен извне)
telegram_app = None


def set_telegram_app(app):
    """Устанавливает экземпляр Telegram приложения для отправки уведомлений"""
    global telegram_app
    telegram_app = app
    logger.info("Telegram app set for webhook notifications")


def is_yookassa_ip(ip_str: str) -> bool:
    """Проверяет, принадлежит ли IP-адрес к разрешенным сетям ЮKassa"""
    try:
        ip = ipaddress.ip_address(ip_str)

        # Проверяем отдельные IP
        if ip in YOOKASSA_IPS:
            return True

        # Проверяем сети
        for network in YOOKASSA_IP_RANGES:
            if ip in network:
                return True

        return False
    except ValueError:
        return False


def _amount_matches(provider_amount, payload_amount) -> bool:
    """Compare authoritative YooKassa money values with the webhook."""
    try:
        verified = Decimal(str(provider_amount["value"]))
        received = Decimal(str(payload_amount["value"]))
        return (
            verified.is_finite() and received.is_finite()
            and verified == received
            and str(provider_amount["currency"]).upper() ==
            str(payload_amount["currency"]).upper()
        )
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return False


async def _verify_provider_notification(event_type: str, event_object: dict) -> bool:
    """Validate every financial callback by an independent bounded HTTPS GET.

    Do not trust forwarded IP or webhook JSON alone. The installed YooKassa
    SDK's Payment.find_one currently stalls on this host; use requests with
    explicit connect/read timeouts and TLS certificate validation instead.
    """
    if not isinstance(event_object, dict):
        return False
    expected = {
        "payment.succeeded": "succeeded",
        "payment.canceled": "canceled",
        "payment.waiting_for_capture": "waiting_for_capture",
        "refund.succeeded": "succeeded",
    }.get(event_type)
    if not expected:
        return False

    ref_id = str(event_object.get("id") or "")
    try:
        UUID(ref_id)
    except (ValueError, TypeError):
        return False
    is_refund = event_type.startswith("refund.")
    resource = "refunds" if is_refund else "payments"
    url = f"https://api.yookassa.ru/v3/{resource}/{ref_id}"
    credentials = (config.YOOKASSA_SHOP_ID, config.YOOKASSA_SECRET_KEY)
    if not all(credentials):
        raise RuntimeError("YooKassa credentials missing")

    # One bounded retry absorbs transient TLS connect/read timeouts without
    # extending beyond Nginx's 30-second webhook proxy timeout.
    for attempt in range(2):
        try:
            response = await asyncio.to_thread(
                requests.get, url, auth=credentials, timeout=(4, 6)
            )
            break
        except requests.exceptions.Timeout:
            if attempt:
                raise
            await asyncio.sleep(0.2)
    if response.status_code == 404:
        return False
    response.raise_for_status()
    remote = response.json()
    if not isinstance(remote, dict):
        return False
    if str(remote.get("id") or "") != ref_id:
        return False
    if str(remote.get("status") or "").lower() != expected:
        return False
    if event_type == "payment.succeeded" and remote.get("paid") is not True:
        return False
    if not _amount_matches(remote.get("amount") or {},
                           event_object.get("amount") or {}):
        return False
    if is_refund and str(remote.get("payment_id") or "") != str(
        event_object.get("payment_id") or ""
    ):
        return False
    claimed_method = event_object.get("payment_method") or {}
    if not isinstance(claimed_method, dict):
        return False
    if claimed_method.get("id"):
        verified_method = remote.get("payment_method") or {}
        if (
            not isinstance(verified_method, dict)
            or str(verified_method.get("id") or "") != str(claimed_method["id"])
            or bool(claimed_method.get("saved")) != bool(
                verified_method.get("saved")
            )
        ):
            return False
    return True


class WebhookHandler:
    def __init__(self):
        self.app = web.Application()
        self.setup_routes()

    def setup_routes(self):
        """Настройка маршрутов для вебхуков"""
        self.app.router.add_post("/webhook/yookassa", self.handle_yookassa_webhook)
        self.app.router.add_get("/health", self.health_check)

    async def health_check(self, request):
        """Проверка работоспособности сервера"""
        return web.json_response({"status": "ok", "service": "yookassa-webhook"})

    async def handle_yookassa_webhook(self, request):
        """
        Обработка вебхука от ЮKassa

        Вебхуки приходят на URL: https://vpn.chillcreative.ru/webhook/yookassa

        Согласно документации ЮKassa:
        - Необходимо вернуть HTTP 200 для подтверждения получения
        - ЮKassa будет повторять уведомления в течение 24 часов при ошибках
        """
        try:
            # Проверяем IP-адрес отправителя (опциональная защита)
            peer_ip = request.headers.get("X-Forwarded-For", request.remote)
            if peer_ip:
                # Берем первый IP если их несколько (X-Forwarded-For может содержать цепочку)
                peer_ip = peer_ip.split(",")[0].strip()
                logger.info(f"Webhook received from IP: {peer_ip}")

                # Раскомментируйте для строгой проверки IP:
                # if not is_yookassa_ip(peer_ip):
                #     logger.warning(f"Webhook from unauthorized IP: {peer_ip}")
                #     return web.Response(status=403, text="Forbidden")

            # Получаем данные вебхука
            payload = await request.json()

            logger.debug(
                f"Webhook payload: {json.dumps(payload, indent=2, ensure_ascii=False)}"
            )

            # Проверяем тип уведомления
            notification_type = payload.get("type")
            if notification_type != "notification":
                logger.warning(f"Invalid notification type: {notification_type}")
                return web.Response(status=400, text="Invalid notification type")

            # Обрабатываем тип события
            event_type = payload.get("event")
            event_object = payload.get("object", {})

            logger.info(f"Received webhook event: {event_type}")

            state_changing_events = {
                "payment.succeeded", "payment.canceled",
                "payment.waiting_for_capture", "refund.succeeded",
            }
            if event_type in state_changing_events:
                try:
                    authentic = await _verify_provider_notification(
                        event_type, event_object
                    )
                except Exception as exc:
                    logger.warning(
                        "YooKassa independent verification unavailable: %s",
                        type(exc).__name__,
                    )
                    return web.Response(status=503, text="Provider verification unavailable")
                if not authentic:
                    logger.warning("Rejected unverified YooKassa notification")
                    return web.Response(status=403, text="Unverified notification")

            # Обработка событий платежей
            if event_type == "payment.succeeded":
                await self.handle_payment_succeeded(payload)
            elif event_type == "payment.canceled":
                await self.handle_payment_canceled(payload)
            elif event_type == "payment.waiting_for_capture":
                await self.handle_payment_waiting_for_capture(payload)
            # Обработка событий возвратов
            elif event_type == "refund.succeeded":
                await self.handle_refund_succeeded(payload)
            # Обработка событий способов оплаты
            elif event_type == "payment_method.active":
                logger.info(f"Payment method activated: {event_object.get('id')}")
            else:
                logger.info(f"Unhandled event type: {event_type}")

            # ВАЖНО: Возвращаем HTTP 200 для подтверждения получения
            # ЮKassa игнорирует тело ответа, важен только статус код
            return web.Response(status=200, text="OK")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in webhook: {e}")
            return web.Response(status=400, text="Invalid JSON")
        except Exception as e:
            logger.error(f"Error processing webhook: {e}", exc_info=True)
            # При ошибке ЮKassa будет повторять уведомление
            return web.Response(status=500, text="Internal Server Error")

    async def handle_payment_succeeded(self, payload):
        """
        Обработка успешного платежа (payment.succeeded)

        Активирует подписку пользователя и отправляет уведомление в Telegram
        """
        try:
            payment = payload.get("object", {})
            payment_id = payment.get("id")
            amount = payment.get("amount", {}).get("value")
            currency = payment.get("amount", {}).get("currency", "RUB")

            # Получаем metadata из платежа
            metadata = payment.get("metadata", {})
            metadata_user_id = metadata.get("user_id")

            logger.info(f"Payment succeeded: {payment_id}, amount: {amount} {currency}")

            # Получаем информацию о платеже из БД
            async with aiosqlite.connect(db.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT * FROM payments WHERE payment_id = ?", (payment_id,)
                ) as cursor:
                    payment_data = await cursor.fetchone()

            if not payment_data:
                logger.warning(f"Payment {payment_id} not found in database")
                # Пытаемся найти по metadata если есть
                if metadata_user_id:
                    logger.info(
                        f"Trying to find payment by metadata user_id: {metadata_user_id}"
                    )
                return

            user_id = payment_data["user_id"]
            subscription_id = payment_data["subscription_id"]
            plan_id = payment_data["plan_id"]

            # Independent of the remote check, never settle a payment with an
            # amount that differs from the recorded order, even by 1 kopeck.
            try:
                expected_amount = Decimal(str(payment_data["amount"]))
                received_amount = Decimal(str(amount))
            except (TypeError, InvalidOperation) as exc:
                raise ValueError("Invalid payment amount") from exc
            if (
                not expected_amount.is_finite()
                or not received_amount.is_finite()
                or received_amount != expected_amount
                or str(currency).upper() != "RUB"
            ):
                raise ValueError("YooKassa amount/currency does not match local order")

            # One SQLite write transaction makes repeated notifications
            # idempotent and the payment/subscription transition atomic.
            async with aiosqlite.connect(db.db_path) as conn:
                await conn.execute("BEGIN IMMEDIATE")
                cursor = await conn.execute(
                    """UPDATE payments
                       SET status = 'succeeded', paid_at = CURRENT_TIMESTAMP
                       WHERE payment_id = ?
                         AND status IN ('pending', 'waiting_for_capture', 'canceled')
                    """,
                    (payment_id,),
                )
                if cursor.rowcount != 1:
                    await conn.rollback()
                    logger.info("YooKassa duplicate or terminal payment ignored")
                    return
                await conn.execute(
                    'UPDATE subscriptions SET status = "active" WHERE id = ?',
                    (subscription_id,),
                )
                await conn.commit()

            logger.info(f"Subscription {subscription_id} activated for user {user_id}")

            # Сохраняем токен карты если он был сохранён (save_payment_method=true)
            pm = payment.get("payment_method", {})
            if pm.get("saved") and pm.get("id"):
                card = pm.get("card", {})
                card_type = card.get("card_type", "")
                card_last4 = card.get("last4", "")
                await db.save_payment_method(user_id, pm["id"], card_type, card_last4)
                logger.info(f"Saved payment method {pm['id']} for user {user_id}")

            # Отправляем уведомление пользователю в Telegram
            saved_card = bool(pm.get("saved") and pm.get("id"))
            await self._notify_payment_success(
                user_id, amount, currency, plan_id, subscription_id, saved_card
            )

        except Exception as e:
            logger.error(f"Error handling payment succeeded: {e}", exc_info=True)
            raise  # Передаем ошибку дальше для возврата 500

    async def handle_payment_canceled(self, payload):
        """
        Обработка отмененного платежа (payment.canceled)
        """
        try:
            payment = payload.get("object", {})
            payment_id = payment.get("id")
            cancellation_details = payment.get("cancellation_details", {})
            reason = cancellation_details.get("reason", "unknown")
            party = cancellation_details.get("party", "unknown")

            logger.info(
                f"Payment canceled: {payment_id}, reason: {reason}, party: {party}"
            )

            # Получаем информацию о платеже из БД
            async with aiosqlite.connect(db.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT * FROM payments WHERE payment_id = ?", (payment_id,)
                ) as cursor:
                    payment_data = await cursor.fetchone()

            # Обновляем статус платежа
            async with aiosqlite.connect(db.db_path) as conn:
                await conn.execute(
                    """UPDATE payments SET status = 'canceled'
                       WHERE payment_id = ? AND status IN ('pending', 'waiting_for_capture')""",
                    (payment_id,),
                )
                await conn.commit()

            # Уведомляем пользователя об отмене
            if payment_data:
                user_id = payment_data["user_id"]
                await self._notify_payment_canceled(user_id, reason)

        except Exception as e:
            logger.error(f"Error handling payment canceled: {e}", exc_info=True)
            raise

    async def handle_payment_waiting_for_capture(self, payload):
        """
        Обработка платежа, ожидающего подтверждения (payment.waiting_for_capture)

        Для двухстадийных платежей - требуется подтверждение списания
        """
        try:
            payment = payload.get("object", {})
            payment_id = payment.get("id")
            amount = payment.get("amount", {}).get("value")

            logger.info(f"Payment waiting for capture: {payment_id}, amount: {amount}")

            # Обновляем статус платежа
            async with aiosqlite.connect(db.db_path) as conn:
                await conn.execute(
                    """UPDATE payments SET status = 'waiting_for_capture'
                       WHERE payment_id = ? AND status = 'pending'""",
                    (payment_id,),
                )
                await conn.commit()

            # Для автоматического списания (если capture=True при создании)
            # ЮKassa автоматически подтвердит платеж и пришлет payment.succeeded
            # Для двухстадийных платежей здесь нужно вызвать Payment.capture()

        except Exception as e:
            logger.error(
                f"Error handling payment waiting for capture: {e}", exc_info=True
            )
            raise

    async def handle_refund_succeeded(self, payload):
        """
        Обработка успешного возврата (refund.succeeded)
        """
        try:
            refund = payload.get("object", {})
            refund_id = refund.get("id")
            payment_id = refund.get("payment_id")
            amount = refund.get("amount", {}).get("value")

            logger.info(
                f"Refund succeeded: {refund_id} for payment {payment_id}, amount: {amount}"
            )

            # Обновляем статус платежа в БД
            async with aiosqlite.connect(db.db_path) as conn:
                await conn.execute(
                    'UPDATE payments SET status = "refunded" WHERE payment_id = ?',
                    (payment_id,),
                )
                await conn.commit()

        except Exception as e:
            logger.error(f"Error handling refund succeeded: {e}", exc_info=True)

    async def _notify_payment_success(
        self,
        user_id: int,
        amount: str,
        currency: str,
        plan_id: str,
        subscription_id: int,
        saved_card: bool = False,
    ):
        """Отправляет уведомление пользователю об успешной оплате"""
        if not telegram_app:
            logger.warning("Telegram app not set, cannot send notification")
            return

        try:
            # Получаем информацию о подписке
            async with aiosqlite.connect(db.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT * FROM subscriptions WHERE id = ?", (subscription_id,)
                ) as cursor:
                    sub_data = await cursor.fetchone()

            plan_name = config.SUBSCRIPTION_PLANS.get(plan_id, {}).get("name", plan_id)

            text = f"""
✅ <b>Оплата успешно завершена!</b>

💳 Сумма: <b>{amount} {currency}</b>
📦 Тариф: <b>{plan_name}</b>
"""

            if sub_data:
                expires = sub_data["expires_at"]
                if isinstance(expires, str):
                    expires = expires[:10]
                else:
                    expires = expires.strftime("%d.%m.%Y")
                text += f"📅 Подписка активна до: <b>{expires}</b>\n\n"

            text += "🎉 Теперь вы можете получить конфигурации VPN!\n\n"
            if saved_card:
                text += "💳 Карта сохранена — следующее списание пройдёт автоматически.\n\n"
            text += "Нажмите '🔐 Получить конфиги' в главном меню."

            await telegram_app.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="HTML",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": "🔐 Получить конфиги",
                                "callback_data": "get_configs",
                            },
                            {"text": "🏠 Главное меню", "callback_data": "main_menu"},
                        ]
                    ]
                },
            )
            logger.info(f"Payment success notification sent to user {user_id}")

        except Exception as e:
            logger.error(
                f"Error sending payment success notification to {user_id}: {e}"
            )

    async def _notify_payment_canceled(self, user_id: int, reason: str):
        """Отправляет уведомление пользователю об отмене платежа"""
        if not telegram_app:
            logger.warning("Telegram app not set, cannot send notification")
            return

        try:
            # Карта причин отмены
            reason_map = {
                "3d_secure_failed": "Ошибка 3D-Secure",
                "call_issuer": "Звоните в банк",
                "canceled_by_merchant": "Отменено продавцом",
                "canceled_by_user": "Отменено пользователем",
                "card_expired": "Срок действия карты истек",
                "country_forbidden": "Запрещена оплата из этой страны",
                "fraud_suspected": "Подозрение в мошенничестве",
                "general_decline": "Общий отказ",
                "identification_required": "Требуется идентификация",
                "insufficient_funds": "Недостаточно средств",
                "invalid_card_number": "Неверный номер карты",
                "invalid_csc": "Неверный CVV/CVC",
                "issuer_unavailable": "Банк недоступен",
                "payment_method_limit_exceeded": "Превышен лимит платежного метода",
                "payment_method_restricted": "Платежный метод ограничен",
                "permission_revoked": "Разрешение отозвано",
                "unsupported_mobile_operator": "Неподдерживаемый оператор",
            }

            reason_text = reason_map.get(reason, f"Причина: {reason}")

            text = f"""
❌ <b>Платеж отменен</b>

{reason_text}

Вы можете попробовать снова, выбрав другой способ оплаты.
"""

            await telegram_app.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="HTML",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": "💎 Купить подписку",
                                "callback_data": "buy_subscription",
                            },
                            {"text": "🏠 Главное меню", "callback_data": "main_menu"},
                        ]
                    ]
                },
            )
            logger.info(f"Payment canceled notification sent to user {user_id}")

        except Exception as e:
            logger.error(
                f"Error sending payment canceled notification to {user_id}: {e}"
            )

    def run(self, host=None, port=None, handle_signals=True):
        """Запуск вебхук сервера"""
        import asyncio

        host = host or config.WEBHOOK_HOST
        port = port or config.WEBHOOK_PORT

        logger.info(f"Starting YooKassa webhook server on {host}:{port}")
        logger.info(f"Webhook URL: {config.WEBHOOK_URL}")

        # Когда запускаем в отдельном потоке, отключаем обработку сигналов
        if not handle_signals:
            # Создаем новый event loop для потока
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Запускаем без обработки сигналов
            runner = web.AppRunner(self.app)
            loop.run_until_complete(runner.setup())
            site = web.TCPSite(runner, host, port)
            loop.run_until_complete(site.start())
            logger.info(f"Webhook server started at http://{host}:{port}")

            # Держим сервер запущенным
            try:
                loop.run_forever()
            except KeyboardInterrupt:
                pass
            finally:
                loop.run_until_complete(runner.cleanup())
                loop.close()
        else:
            web.run_app(self.app, host=host, port=port)


# Создаем экземпляр обработчика вебхуков
webhook_handler = WebhookHandler()

if __name__ == "__main__":
    # Настройка логирования при прямом запуске
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    webhook_handler.run()
