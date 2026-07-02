import uuid

from config import config
from yookassa import Configuration, Payment

# Настройка ЮKassa
Configuration.account_id = config.YOOKASSA_SHOP_ID
Configuration.secret_key = config.YOOKASSA_SECRET_KEY


class PaymentManager:
    def __init__(self):
        self.test_mode = config.YOOKASSA_TEST_MODE

    async def create_payment(self, user_id: int, amount: int, description: str) -> dict:
        """Создает разовый платеж в ЮKassa"""
        idempotence_key = str(uuid.uuid4())

        bot_username = config.BOT_USERNAME or config.BOT_TOKEN.split(":")[0]

        payment_payload = {
            "amount": {"value": f"{amount}.00", "currency": "RUB"},
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{bot_username}",
            },
            "capture": True,
            "description": description,
            "metadata": {"user_id": str(user_id), "telegram": "true"},
            "test": self.test_mode,
        }

        if config.YOOKASSA_SAVE_PAYMENT_METHOD:
            payment_payload["save_payment_method"] = True

        payment = Payment.create(payment_payload, idempotence_key)

        return {
            "payment_id": payment.id,
            "confirmation_url": payment.confirmation.confirmation_url,
            "status": payment.status,
        }

    async def create_recurring_payment(
        self, user_id: int, amount: int, description: str, payment_method_id: str
    ) -> dict:
        """Создает рекуррентный платеж по сохранённому токену карты"""
        idempotence_key = str(uuid.uuid4())

        payment = Payment.create(
            {
                "amount": {"value": f"{amount}.00", "currency": "RUB"},
                "capture": True,
                "payment_method_id": payment_method_id,
                "description": description,
                "metadata": {
                    "user_id": str(user_id),
                    "telegram": "true",
                    "recurring": "true",
                },
                "test": self.test_mode,
            },
            idempotence_key,
        )

        return {
            "payment_id": payment.id,
            "status": payment.status,
        }

    async def check_payment(self, payment_id: str) -> dict:
        """Проверяет статус платежа"""
        payment = Payment.find_one(payment_id)
        return {
            "status": payment.status,
            "paid": payment.paid,
            "amount": payment.amount.value if payment.paid else None,
        }


payment_manager = PaymentManager()
