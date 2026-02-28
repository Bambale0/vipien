import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    # ЮKassa
    YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID')
    YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY')
    YOOKASSA_TEST_MODE = os.getenv('YOOKASSA_TEST_MODE', 'true').lower() == 'true'
    
    # Админы
    ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
    
    # Ссылки
    SUPPORT_LINK = os.getenv('SUPPORT_LINK', 'https://t.me/support')
    CHANNEL_LINK = os.getenv('CHANNEL_LINK', '')
    
    # WireGuard (AmneziaWG)
    WG_INTERFACE = os.getenv('WG_INTERFACE', 'wg0')
    WG_CONFIG_PATH = os.getenv('WG_CONFIG_PATH', '/etc/amnezia/amneziawg/wg0.conf')
    WG_ENDPOINT = os.getenv('WG_ENDPOINT', '89.125.51.145:51820')
    WG_DNS = os.getenv('WG_DNS', '94.140.14.14,94.140.15.15')
    
    # AmneziaWG masking parameters
    WG_JC = 6
    WG_JMIN = 10
    WG_JMAX = 50
    WG_S1 = 28
    WG_S2 = 75
    WG_H1 = 1153214260
    WG_H2 = 397682404
    WG_H3 = 1017619285
    WG_H4 = 451273032
    WG_SERVER_PUBLIC_KEY = '6ZWuWzq45gK0RokEYA/2ijhCXU0ArmlZY4kq543xv1E='
    
    # IP range for clients
    WG_CLIENT_NETWORK = '10.8.1.0/24'
    
    # База данных
    DB_PATH = 'wg_bot.db'
    
    # Webhook настройки
    WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', '0.0.0.0')
    WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '8080'))
    WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/webhook/yookassa')
    WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://vpn.chillcreative.ru/webhook/yookassa')
    
    # Тарифы подписок (в рублях)
    SUBSCRIPTION_PLANS = {
        'month': {
            'id': 'month',
            'name': '1 месяц',
            'price': 1000,
            'days': 30,
            'description': 'Подписка на 1 месяц'
        },
        'half_year': {
            'id': 'half_year',
            'name': '6 месяцев',
            'price': 5000,
            'days': 180,
            'description': 'Подписка на 6 месяцев (-17%)'
        },
        'year': {
            'id': 'year',
            'name': '12 месяцев',
            'price': 9000,
            'days': 365,
            'description': 'Подписка на 12 месяцев (-25%)'
        }
    }
    
    # Лимиты
    MAX_CONFIGS_PER_USER = 3
    ADMIN_MAX_CONFIGS = 999

config = Config()