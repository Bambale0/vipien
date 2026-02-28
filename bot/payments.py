from yookassa import Configuration, Payment
import uuid
from config import config

# Настройка ЮKassa
Configuration.account_id = config.YOOKASSA_SHOP_ID
Configuration.secret_key = config.YOOKASSA_SECRET_KEY

class PaymentManager:
    def __init__(self):
        self.test_mode = config.YOOKASSA_TEST_MODE
    
    async def create_payment(self, user_id: int, amount: int, description: str) -> dict:
        """Создает платеж в ЮKassa"""
        idempotence_key = str(uuid.uuid4())
        
        payment = Payment.create({
            "amount": {
                "value": f"{amount}.00",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{config.BOT_TOKEN.split(':')[0]}"  # Возврат в бот
            },
            "capture": True,
            "description": description,
            "metadata": {
                "user_id": str(user_id),
                "telegram": "true"
            },
            "test": self.test_mode
        }, idempotence_key)
        
        return {
            'payment_id': payment.id,
            'confirmation_url': payment.confirmation.confirmation_url,
            'status': payment.status
        }
    
    async def check_payment(self, payment_id: str) -> dict:
        """Проверяет статус платежа"""
        payment = Payment.find_one(payment_id)
        return {
            'status': payment.status,
            'paid': payment.paid,
            'amount': payment.amount.value if payment.paid else None
        }

payment_manager = PaymentManager()